import asyncio
import json
import logging
from typing import Annotated, Optional, AsyncGenerator

from config import settings
from fastapi import APIRouter, Depends
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from database import get_session
from dependencies.schemas import User
from dependencies.dependency import UserRoles, RoleChecker

logger = logging.getLogger(__name__)
router = APIRouter()

model = init_chat_model(
    "google_genai:gemini-3.5-flash-lite",
    google_api_key=settings.GOOGLE_API_KEY,
)

embeddings_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    google_api_key=settings.GOOGLE_API_KEY,
    output_dimensionality=768,
)


@tool
def hybrid_transaction_search(query_text: str) -> str:
    """
    Search transactions using semantic vector similarity and trigram
    fuzzy matching. Returns only the most relevant transactions.
    """
    try:
        query_vector = embeddings_model.embed_query(query_text)
        vector_str = "[" + ",".join(map(str, query_vector)) + "]"

        db_generator = get_session()
        db = next(db_generator)

        try:
            sql = text(
                """
                WITH vector_candidates AS (
                    SELECT id, 
                        (1 - (embedding <=> :vector)) AS vec_score
                    FROM transactions
                    WHERE description IS NOT NULL
                    ORDER BY embedding <=> :vector
                    LIMIT 50
                ),
                text_candidates AS (
                    SELECT id, 
                        similarity(description, :query_str) AS txt_score
                    FROM transactions
                    WHERE description IS NOT NULL
                    AND description % :query_str  
                    ORDER BY similarity(description, :query_str) DESC
                    LIMIT 50
                ),
                combined AS (
                    SELECT COALESCE(v.id, t.id) AS id
                    FROM vector_candidates v
                    FULL OUTER JOIN text_candidates t ON v.id = t.id
                )
                SELECT 
                    t.id,
                    t.from_user_id,
                    t.to_user_id,
                    t.amount,
                    t.date,
                    t.description
                FROM combined c
                JOIN transactions t ON c.id = t.id
                LEFT JOIN vector_candidates v ON c.id = v.id
                LEFT JOIN text_candidates tc ON c.id = tc.id
                ORDER BY (
                    0.7 * COALESCE(v.vec_score, 0) + 
                    0.3 * COALESCE(tc.txt_score, 0)
                ) DESC
                LIMIT 20;
                """
            )
            result = db.execute(
                sql,
                {
                    "vector": vector_str,
                    "query_str": query_text.strip(),
                },
            )

            rows = result.mappings().all()

            if not rows:
                return "No matching transactions found."

            return json.dumps(
                [dict(row) for row in rows],
                default=str,
            )

        finally:
            db.close()

    except Exception:
        logger.exception("Hybrid transaction search failed")
        return "Transaction search failed."


tools = [hybrid_transaction_search]
model_with_tools = model.bind_tools(tools)


SYSTEM_PROMPT = """
You are an expert financial data analyst.

Use `hybrid_transaction_search` whenever the user asks about transactions.

The search tool can find transactions based on:
- descriptions
- merchants
- concepts
- keywords
- typos
- semantic meaning

When answering:
- Do not invent transactions.
- Base transaction-related answers only on tool results.
- Keep responses concise.
- Perform calculations carefully.
- Output only plain text.
- Do not output JSON.
- Do not output Python dictionaries.
- Do not output code blocks.
"""


async def call_model(state: MessagesState):
    """
    Async model invocation so the FastAPI event loop isn't blocked
    by a synchronous LLM request.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *[
            message
            for message in state["messages"]
            if not isinstance(message, SystemMessage)
        ],
    ]

    response = await model_with_tools.ainvoke(messages)

    return {
        "messages": [response]
    }


def should_continue(state: MessagesState):
    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"

    return END


workflow = StateGraph(MessagesState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

compiled_graph = workflow.compile(
    checkpointer=MemorySaver()
)


class DescriptionRequest(BaseModel):
    prompt: str
    thread_id: Optional[str] = "default_thread"


@router.post("/description")
async def stream_user_descriptions(
    request: DescriptionRequest,
    current_user: Annotated[
        User,
        Depends(RoleChecker([UserRoles.PREMIUM]))
    ],
) -> EventSourceResponse:

    async def event_generator() -> AsyncGenerator[dict, None]:
        total_input_tokens = 0
        total_output_tokens = 0
        
        # Track processed message IDs to avoid double-counting chunks from the same AIMessage stream
        processed_message_ids = set()

        try:
            config = {
                "configurable": {
                    "thread_id": request.thread_id,
                },
                "recursion_limit": 8,
            }

            input_state = {
                "messages": [
                    HumanMessage(content=request.prompt)
                ]
            }

            async for chunk, metadata in compiled_graph.astream(
                input_state,
                config=config,
                stream_mode="messages",
            ):
                node_name = metadata.get("langgraph_node")

                if node_name == "agent":
                    content = getattr(chunk, "content", "")
                    token_text = ""

                    if isinstance(content, str):
                        token_text = content

                    elif isinstance(content, list):
                        parts = []

                        for block in content:
                            if isinstance(block, str):
                                parts.append(block)

                            elif isinstance(block, dict):
                                text_value = block.get("text")

                                if isinstance(text_value, str):
                                    parts.append(text_value)

                        token_text = "".join(parts)

                    # 1. Yield tokens if present
                    if token_text:
                        yield {
                            "event": "token",
                            "data": json.dumps({
                                "token": token_text
                            }),
                        }

                    # 2. Extract and aggregate usage metadata independently of token text
                    usage = getattr(chunk, "usage_metadata", None)
                    message_id = getattr(chunk, "id", None)

                    if usage:
                        if message_id:
                            if message_id not in processed_message_ids:
                                processed_message_ids.add(message_id)
                                total_input_tokens += usage.get("input_tokens", 0)
                                total_output_tokens += usage.get("output_tokens", 0)
                        else:
                            # Fallback if ID isn't present on the chunk
                            total_input_tokens = usage.get("input_tokens", 0)
                            total_output_tokens = usage.get("output_tokens", 0)

                elif node_name == "tools":
                    yield {
                        "event": "status",
                        "data": json.dumps({
                            "message": "Searching transactions..."
                        }),
                    }

            # Send final aggregated usage event before closing the stream
            yield {
                "event": "usage",
                "data": json.dumps({
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "total_tokens": total_input_tokens + total_output_tokens
                }),
            }

            yield {
                "event": "close",
                "data": json.dumps({
                    "status": "done"
                }),
            }

        except Exception as e:
            logger.exception(
                "Description streaming failed: %s",
                str(e),
            )

            yield {
                "event": "error",
                "data": json.dumps({
                    "detail": "An internal error occurred during streaming."
                }),
            }

    return EventSourceResponse(event_generator())
# import json
# import logging
# import time
# from typing import Annotated, Optional, AsyncGenerator
# from config import settings
# from fastapi import APIRouter, Depends, HTTPException
# from langchain_core.messages import SystemMessage, HumanMessage
# from langchain_core.tools import tool
# from langchain.chat_models import init_chat_model
# from pydantic import BaseModel, Field
# import psycopg
# from dependencies.schemas import User
# from dependencies.dependency import UserRoles, RoleChecker
# from langgraph.graph import StateGraph, MessagesState, START, END
# from langgraph.prebuilt import ToolNode
# from langgraph.checkpoint.memory import MemorySaver
# from database import get_session
# from sqlalchemy import text
# from sse_starlette.sse import EventSourceResponse
# from langchain_google_genai import GoogleGenerativeAIEmbeddings

# logger = logging.getLogger(__name__)
# router = APIRouter()

# model = init_chat_model(
#     "google_genai:gemini-3.5-flash-lite", google_api_key=settings.GOOGLE_API_KEY
# )
# embeddings_model = GoogleGenerativeAIEmbeddings(
#     model="gemini-embedding-001", 
#     google_api_key=settings.GOOGLE_API_KEY,
#     output_dimensionality=768
# )

# @tool
# def hybrid_transaction_search(
#     query_text: str, 
# ) -> str:
#     """
#     Performs an advanced hybrid search combining semantic vector distance with 
#     PostgreSQL trigram fuzzy matching to seamlessly catch typos, slang, and variations.
#     """
#     try:
#         query_vector = embeddings_model.embed_query(query_text)
#         vector_str = "[" + ",".join(map(str, query_vector)) + "]"
        
#         db_generator = get_session()
#         db = next(db_generator)
#         try:
#             params = {
#                 "vector": vector_str, 
#                 "query_str": query_text.strip(),
#             }

#             sql = text(f"""
#                 SELECT id, from_user_id, to_user_id, amount, date, description, 
#                        (embedding <=> :vector) as semantic_distance,
#                        similarity(description, :query_str) as typo_similarity
#                 FROM transactions
#                 ORDER BY (embedding <=> :vector) - (similarity(description, :query_str) * 0.5) ASC
#             """)
            
#             result = db.execute(sql, params)
#             rows = result.fetchall()
            
#             if not rows:
#                 return "No matching transactions found matching the search criteria."
            
#             columns = result.keys()
#             formatted_results = [dict(zip(columns, row)) for row in rows]
#             return str(formatted_results)
#         finally:
#             db.close()
#     except Exception as e:
#         logger.error(f"Hybrid search error: {e}")
#         return "Hybrid search failed due to an error."

# @tool
# def get_database_schema() -> str:
#     """Inspects the PostgreSQL database dynamically to extract table names and columns."""
#     try:
#         connection_url = settings.DATABASE_URL.get_secret_value()
#         with psycopg.connect(connection_url) as conn:
#             with conn.cursor() as cursor:
#                 cursor.execute("""
#                     SELECT table_name, column_name, data_type 
#                     FROM information_schema.columns 
#                     WHERE table_schema = 'public'
#                     ORDER BY table_name, ordinal_position;
#                 """)
#                 rows = cursor.fetchall()

#                 if not rows:
#                     return "No tables found in the database schema."

#                 schema_dict = {}
#                 for table_name, column_name, data_type in rows:
#                     if table_name not in schema_dict:
#                         schema_dict[table_name] = []
#                     schema_dict[table_name].append(f"{column_name} ({data_type})")

#                 schema_summary = []
#                 for table, cols in schema_dict.items():
#                     schema_summary.append(f"- Table `{table}`: " + ", ".join(cols))

#                 return "\n".join(schema_summary)
#     except Exception as e:
#         logger.error(f"Schema retrieval error: {e}")
#         return "Could not retrieve schema due to an internal error."

# tools = [get_database_schema, hybrid_transaction_search]
# model_with_tools = model.bind_tools(tools)

# _CACHED_SCHEMA = None
# _LAST_SCHEMA_FETCH = 0
# SCHEMA_CACHE_TTL = 300

# def get_cached_schema() -> str:
#     global _CACHED_SCHEMA, _LAST_SCHEMA_FETCH
#     if _CACHED_SCHEMA and (time.time() - _LAST_SCHEMA_FETCH < SCHEMA_CACHE_TTL):
#         return _CACHED_SCHEMA
    
#     schema_string = get_database_schema.invoke({})
#     _CACHED_SCHEMA = schema_string
#     _LAST_SCHEMA_FETCH = time.time()
#     return schema_string

# def call_model(state: MessagesState):
#     messages = state["messages"]
#     live_schema = get_cached_schema()
    
#     system_instruction = SystemMessage(content=(
#         "You are an expert financial data analyst. "
#         "Your job is to handle user queries by using `hybrid_transaction_search` for all "
#         "transaction lookups, filtering by concepts, descriptions, keywords, user IDs, or amounts.\n\n"
#         f"DATABASE SCHEMA:\n{live_schema}\n\n"
#         "CRITICAL RULES:\n"
#         "- Output ONLY plain text sentences for your final response.\n"
#         "- Do NOT output JSON wrappers, code blocks, or dictionary syntax.\n"
#         "- Keep your response direct and brief."
#     ))
    
#     filtered_messages = [m for m in messages if not isinstance(m, SystemMessage)]
#     messages_for_llm = [system_instruction] + filtered_messages
        
#     response = model_with_tools.invoke(messages_for_llm)
#     return {"messages": [response]}

# def should_continue(state: MessagesState):
#     last_message = state["messages"][-1]
#     if last_message.tool_calls:
#         return "tools"
#     return END

# workflow = StateGraph(MessagesState)
# workflow.add_node("agent", call_model)
# workflow.add_node("tools", ToolNode(tools=tools))

# workflow.add_edge(START, "agent")
# workflow.add_conditional_edges("agent", should_continue)
# workflow.add_edge("tools", "agent") 

# compiled_graph = workflow.compile(checkpointer=MemorySaver())

# class DescriptionRequest(BaseModel):
#     prompt: str
#     thread_id: Optional[str] = "default_thread"

# @router.post("/description")
# async def stream_user_descriptions(
#     request: DescriptionRequest,
#     current_user: Annotated[User, Depends(RoleChecker([UserRoles.PREMIUM]))],
# ) -> EventSourceResponse:
#     """
#     Streams AI tokens and database execution statuses via Server-Sent Events (SSE).
#     """
#     async def event_generator() -> AsyncGenerator[dict, None]:
#         try:
#             config = {
#                 "configurable": {"thread_id": request.thread_id},
#                 "recursion_limit": 16
#             }
#             input_state = {
#                 "messages": [HumanMessage(content=request.prompt)]
#             }

#             async for chunk, metadata in compiled_graph.astream(
#                 input_state, config=config, stream_mode="messages"
#             ):
#                 node_name = metadata.get("langgraph_node")

#                 if node_name == "agent":
#                     token_text = getattr(chunk, "content", "")
#                     if token_text:
#                         yield {
#                             "event": "token",
#                             "data": json.dumps({"token": token_text})
#                         }
#                 elif node_name == "tools":
#                     yield {
#                         "event": "status",
#                         "data": json.dumps({"message": "Executing database search..."})
#                     }

#             yield {
#                 "event": "close", 
#                 "data": json.dumps({"status": "done"})
#             }

#         except Exception as e:
#             logger.error(f"Streaming error in description route: {str(e)}", exc_info=True)
#             yield {
#                 "event": "error",
#                 "data": json.dumps({"detail": "An internal error occurred during streaming."})
#             }

#     return EventSourceResponse(event_generator())