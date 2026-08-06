import logging
import time
from typing import Annotated, Optional
from config import settings
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
from pydantic import BaseModel
import psycopg
from dependencies.schemas import User
from dependencies.dependency import UserRoles, RoleChecker
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from database import get_session
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter()

model = init_chat_model(
    "google_genai:gemini-3.5-flash-lite", google_api_key=settings.GOOGLE_API_KEY, temperature=0
)

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

@tool
def execute_sql_query(sql_query: str) -> str:
    """Executes a read-only SQL query against the PostgreSQL database and returns the results with column headers."""
    try:
        cleaned_query = sql_query.strip().lower()
        if not cleaned_query.startswith("select") and not cleaned_query.startswith("with"):
            return "Error: Only SELECT queries are allowed for security reasons."

        db_generator = get_session()
        db = next(db_generator)
        try:
            result = db.execute(text(sql_query))
            rows = result.fetchall()
            
            if not rows:
                return "The query executed successfully, but returned no rows."
            
            columns = result.keys()
            formatted_results = [dict(zip(columns, row)) for row in rows]
            
            return str(formatted_results)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"SQL execution error: {e}")
        return "SQL execution failed due to a syntax or runtime error."

tools = [get_database_schema, execute_sql_query]
model_with_tools = model.bind_tools(tools)

# In-memory schema caching to prevent slow repeated DB inspections and latency spikes
_CACHED_SCHEMA = None
_LAST_SCHEMA_FETCH = 0
SCHEMA_CACHE_TTL = 300  # 5 minutes cache

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
    
    # Fetch fresh schema instantly from memory cache
    live_schema = get_cached_schema()
    
    system_instruction = SystemMessage(content=(
        "You are an expert PostgreSQL database analyst. Your job is to take a user's natural language request, "
        "write an appropriate SQL query, use the `execute_sql_query` tool to run it, and then provide a "
        "concise, professional plain-text summary of the results.\n\n"
        f"DATABASE SCHEMA:\n{live_schema}\n\n"
        "CRITICAL RULES:\n"
        "- Output ONLY plain text sentences for your final response.\n"
        "- Do NOT output JSON wrappers, code blocks, or dictionary syntax.\n"
        "- Keep your response direct and brief."
    ))
    
    # Filter out old system instructions to avoid duplication, then inject the updated one
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
async def get_user_descriptions(
    request: DescriptionRequest,
    current_user: Annotated[User, Depends(RoleChecker([UserRoles.PREMIUM]))],
):
    try:
        config = {
            "configurable": {"thread_id": request.thread_id},
            "recursion_limit": 8
        }
        
        input_state = {
            "messages": [HumanMessage(content=request.prompt)]
        }

        final_state = compiled_graph.invoke(input_state, config=config)
        
        final_message = final_state["messages"][-1]
        response_text = final_message.text if hasattr(final_message, "text") else str(final_message.content)

        return {
            "status": "success",
            "thread_id": request.thread_id,
            "description": response_text.strip(),
        }
    except Exception as e:
        error_str = str(e)
        logger.error(f"Endpoint error: {error_str}")
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            raise HTTPException(
                status_code=429, 
                detail="AI daily request limit exceeded"
            )
        raise HTTPException(status_code=500, detail="An internal error occurred processing your request.")
# from typing import Annotated, Optional
# from config import settings
# from fastapi import APIRouter, Depends, HTTPException
# from langchain_core.messages import SystemMessage, HumanMessage
# from langchain_core.tools import tool
# from langchain.chat_models import init_chat_model
# from pydantic import BaseModel
# import psycopg
# from dependencies.schemas import User
# from dependencies.dependency import UserRoles,RoleChecker
# from langgraph.graph import StateGraph, MessagesState, START, END
# from langgraph.prebuilt import ToolNode
# from langgraph.checkpoint.memory import MemorySaver
# from database import get_session
# from sqlalchemy import text

# router = APIRouter()

# model = init_chat_model(
#     "google_genai:gemini-3.5-flash-lite", google_api_key=settings.GOOGLE_API_KEY, temperature=0
# )


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
#         return f"Could not retrieve schema: {str(e)}"

# @tool
# def execute_sql_query(sql_query: str) -> str:
#     """Executes a read-only SQL query against the PostgreSQL database and returns the results with column headers."""
#     try:
  
#         cleaned_query = sql_query.strip().lower()
#         if not cleaned_query.startswith("select") and not cleaned_query.startswith("with"):
#             return "Error: Only SELECT queries are allowed for security reasons."

#         db_generator = get_session()
#         db = next(db_generator)
#         try:
#             # Execute raw SQL using SQLAlchemy's text() construct
#             result = db.execute(text(sql_query))
#             rows = result.fetchall()
            
#             if not rows:
#                 return "The query executed successfully, but returned no rows."
            
#             columns = result.keys()
#             formatted_results = [dict(zip(columns, row)) for row in rows]
            
#             return str(formatted_results)
#         finally:
  
#             db.close()
#     except Exception as e:
#         return f"SQL execution failed: {str(e)}"

# tools = [get_database_schema, execute_sql_query]
# model_with_tools = model.bind_tools(tools)

# def call_model(state: MessagesState):
#     response = model_with_tools.invoke(state["messages"])
#     return {"messages": [response]}

# def should_continue(state: MessagesState):
#     last_message = state["messages"][-1]
#     if last_message.tool_calls:
#         return "tools"
#     return END

# tool_node = ToolNode(tools=tools)

# workflow = StateGraph(MessagesState)
# workflow.add_node("agent", call_model)
# workflow.add_node("tools", tool_node)

# workflow.add_edge(START, "agent")
# workflow.add_conditional_edges("agent", should_continue)
# workflow.add_edge("tools", "agent") 

# memory_saver = MemorySaver()

# compiled_graph = workflow.compile(checkpointer=memory_saver)

# class DescriptionRequest(BaseModel):
#     prompt: str
#     thread_id: Optional[str] = "default_thread"  # Allows clients to pass a conversation/session identifier


# @router.post("/description")
# async def get_user_descriptions(
#     request: DescriptionRequest,
#     current_user: Annotated[
#         User, Depends(RoleChecker([UserRoles.PREMIUM]))
#     ],
# ):
#     try:
#         config = {
#             "configurable": {"thread_id": request.thread_id},
#             "recursion_limit": 8
#         }
        
#         existing_state = compiled_graph.get_state(config)
#         messages = existing_state.values.get("messages", [])

    
#         if not messages:
#             live_schema = get_database_schema.invoke({})
#             system_instruction = SystemMessage(content=
#                 "You are an expert PostgreSQL database analyst. Your job is to take a user's natural language request, "
#                 "write an appropriate SQL query, use the `execute_sql_query` tool to run it, and then provide a "
#                 "concise, professional plain-text summary of the results.\n\n"
#                 f"DATABASE SCHEMA:\n{live_schema}\n\n"
#                 "CRITICAL RULES:\n"
#                 "- Output ONLY plain text sentences for your final response.\n"
#                 "- Do NOT output JSON wrappers, code blocks, or dictionary syntax.\n"
#                 "- Keep your response direct and brief."
#             )
#             initial_messages = [system_instruction, HumanMessage(content=request.prompt)]
#         else:
  
#             initial_messages = [HumanMessage(content=request.prompt)]

#         initial_state = {
#             "messages": initial_messages
#         }

#         final_state = compiled_graph.invoke(
#             initial_state, 
#             config=config
#         )
        
#         final_message = final_state["messages"][-1]
#         response_text = final_message.text if hasattr(final_message, "text") else str(final_message.content)

#         return {
#             "status": "success",
#             "thread_id": request.thread_id,
#             "description": response_text.strip(),
#         }
#     except Exception as e:
#         error_str = str(e)
#         if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
#             raise HTTPException(
#                 status_code=429, 
#                 detail="AI daily request limit exceeded"
#             )
#         raise HTTPException(status_code=500, detail=str(e))