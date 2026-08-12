import logging
import time
from typing import Annotated, Optional
from config import settings
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
import psycopg
from dependencies.schemas import User
from dependencies.dependency import UserRoles, RoleChecker
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from database import get_session
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import json

logger = logging.getLogger(__name__)
router = APIRouter()

model = init_chat_model(
    "google_genai:gemini-3.5-flash", google_api_key=settings.GOOGLE_API_KEY
)
embeddings_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001", 
    google_api_key=settings.GOOGLE_API_KEY,
    output_dimensionality=768
)

@tool
def hybrid_transaction_search(
    query_text: str, 
    user_id: Optional[int] = Field(default=None, description="Filter results for a specific user ID if requested"),
    min_amount: Optional[float] = Field(default=None, description="Filter results where transaction amount is >= this value"),
    limit: int = Field(default=10, description="Maximum number of rows to return")
) -> str:
    """
    Performs an advanced hybrid search combining semantic vector distance with 
    PostgreSQL trigram fuzzy matching to seamlessly catch typos, slang, and variations.
    """
    try:
        query_vector = embeddings_model.embed_query(query_text)
        vector_str = "[" + ",".join(map(str, query_vector)) + "]"
        
        db_generator = get_session()
        db = next(db_generator)
        try:
            db.execute(text("SET hnsw.ef_search = 64;"))

            where_clauses = ["embedding IS NOT NULL"]
            params = {
                "vector": vector_str, 
                "query_str": query_text.strip(),
                "limit_val": limit
            }

            if user_id is not None:
                where_clauses.append("(from_user_id = :uid OR to_user_id = :uid)")
                params["uid"] = user_id

            if min_amount is not None:
                where_clauses.append("amount >= :min_amt")
                params["min_amt"] = min_amount

            where_sql = " AND ".join(where_clauses)

            sql = text(f"""
                SELECT id, from_user_id, to_user_id, amount, date, description, 
                       (embedding <=> :vector) as semantic_distance,
                       similarity(description, :query_str) as typo_similarity
                FROM transactions
                WHERE {where_sql}
                ORDER BY (embedding <=> :vector) - (similarity(description, :query_str) * 0.5) ASC
                LIMIT :limit_val;
            """)
            
            result = db.execute(sql, params)
            rows = result.fetchall()
            
            if not rows:
                return "No matching transactions found matching the search criteria."
            
            columns = result.keys()
            formatted_results = [dict(zip(columns, row)) for row in rows]
            return str(formatted_results)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Hybrid search error: {e}")
        return "Hybrid search failed due to an error."

@tool
def get_database_schema() -> str:
    """Inspects the PostgreSQL database dynamically to extract table names and columns."""
    try:
        connection_url = settings.DATABASE_URL.get_secret_value()
        with psycopg.connect(connection_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name, column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position;
                """)
                rows = cursor.fetchall()

                if not rows:
                    return "No tables found in the database schema."

                schema_dict = {}
                for table_name, column_name, data_type in rows:
                    if table_name not in schema_dict:
                        schema_dict[table_name] = []
                    schema_dict[table_name].append(f"{column_name} ({data_type})")

                schema_summary = []
                for table, cols in schema_dict.items():
                    schema_summary.append(f"- Table `{table}`: " + ", ".join(cols))

                return "\n".join(schema_summary)
    except Exception as e:
        logger.error(f"Schema retrieval error: {e}")
        return "Could not retrieve schema due to an internal error."

tools = [get_database_schema, hybrid_transaction_search]
model_with_tools = model.bind_tools(tools)

_CACHED_SCHEMA = None
_LAST_SCHEMA_FETCH = 0
SCHEMA_CACHE_TTL = 300

def get_cached_schema() -> str:
    global _CACHED_SCHEMA, _LAST_SCHEMA_FETCH
    if _CACHED_SCHEMA and (time.time() - _LAST_SCHEMA_FETCH < SCHEMA_CACHE_TTL):
        return _CACHED_SCHEMA
    
    schema_string = get_database_schema.invoke({})
    _CACHED_SCHEMA = schema_string
    _LAST_SCHEMA_FETCH = time.time()
    return schema_string

def call_model(state: MessagesState):
    messages = state["messages"]
    live_schema = get_cached_schema()
    
    system_instruction = SystemMessage(content=(
        "You are an expert financial data analyst. "
        "Your job is to handle user queries by using `hybrid_transaction_search` for all "
        "transaction lookups, filtering by concepts, descriptions, keywords, user IDs, or amounts.\n\n"
        f"DATABASE SCHEMA:\n{live_schema}\n\n"
        "CRITICAL RULES:\n"
        "- Output ONLY plain text sentences for your final response.\n"
        "- Do NOT output JSON wrappers, code blocks, or dictionary syntax.\n"
        "- Keep your response direct and brief."
    ))
    
    filtered_messages = [m for m in messages if not isinstance(m, SystemMessage)]
    messages_for_llm = [system_instruction] + filtered_messages
        
    response = model_with_tools.invoke(messages_for_llm)
    return {"messages": [response]}

def should_continue(state: MessagesState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

workflow = StateGraph(MessagesState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools=tools))

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent") 

compiled_graph = workflow.compile(checkpointer=MemorySaver())

class DescriptionRequest(BaseModel):
    prompt: str
    thread_id: Optional[str] = "default_thread"

@router.post("/description")
async def stream_user_descriptions(
    request: DescriptionRequest,
    current_user: Annotated[User, Depends(RoleChecker([UserRoles.PREMIUM]))],
):
    async def event_generator():
        try:
            config = {
                "configurable": {"thread_id": request.thread_id},
                "recursion_limit": 16
            }
            input_state = {
                "messages": [HumanMessage(content=request.prompt)]
            }

            async for chunk, metadata in compiled_graph.astream(
                input_state, config=config, stream_mode="messages"
            ):
                if metadata.get("langgraph_node") == "agent":
                    token_text = getattr(chunk, "content", "")
                    if token_text:
                        yield {
                            "event": "token",
                            "data": json.dumps({"token": token_text})
                        }
                elif metadata.get("langgraph_node") == "tools":
                    yield {
                        "event": "status",
                        "data": json.dumps({"message": "Executing database search..."})
                    }

            yield {"event": "close", "data": json.dumps({"status": "done"})}

        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            yield {
                "event": "error",
                "data": json.dumps({"detail": "An internal error occurred."})
            }

    return EventSourceResponse(event_generator())