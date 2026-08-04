from typing import Annotated
from config import settings
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
from pydantic import BaseModel
import psycopg
from schemas import User
from dependecy import UserRolesf
from models import RoleChecker

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

router = APIRouter()

model = init_chat_model(
    "google_genai:gemini-2.5-flash", google_api_key=settings.GOOGLE_API_KEY
)

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
        return f"Could not retrieve schema: {str(e)}"

@tool
def execute_sql_query(sql_query: str) -> str:
    """Executes a read-only SQL query against the PostgreSQL database and returns the results."""
    try:
        connection_url = settings.DATABASE_URL.get_secret_value()
        cleaned_query = sql_query.strip().lower()

        if not cleaned_query.startswith("select"):
            return "Error: Only SELECT queries are allowed for security reasons."

        with psycopg.connect(connection_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql_query)
                rows = cursor.fetchall()

        if not rows:
            return "The query executed successfully, but returned no rows."

        return str(rows)
    except Exception as e:
        return f"SQL execution failed: {str(e)}"
tools = [execute_sql_query]
model_with_tools = model.bind_tools(tools)

def call_model(state: MessagesState):
    """Agent node that invokes the LLM with the current message history."""
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: MessagesState):
    """Conditional edge router to decide if tools need to be called or if we can stop."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

tool_node = ToolNode(tools=tools)

workflow = StateGraph(MessagesState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent") 

compiled_graph = workflow.compile()


class DescriptionRequest(BaseModel):
    prompt: str


@router.post("/description")
async def get_user_descriptions(
    request: DescriptionRequest,
    current_user: Annotated[
        User, Depends(RoleChecker([UserRolesf.PREMIUM]))
    ],
):
    try:

        live_schema = get_database_schema()
        system_instruction = SystemMessage(content=
            "You are an expert PostgreSQL database analyst. Your job is to take a user's natural language request, "
            "write an appropriate SQL query, use the `execute_sql_query` tool to run it, and then provide a "
            "concise, professional plain-text summary of the results.\n\n"
            f"DATABASE SCHEMA:\n{live_schema}\n\n"
            "CRITICAL RULES:\n"
            "- Output ONLY plain text sentences for your final response.\n"
            "- Do NOT output JSON wrappers, code blocks, or dictionary syntax.\n"
            "- Keep your response direct and brief."
        )

        initial_state = {
            "messages": [
                system_instruction,
                HumanMessage(content=request.prompt)
            ]
        }

        final_state = compiled_graph.invoke(
            initial_state, 
            config={"recursion_limit": 8}
        )
        

        final_message = final_state["messages"][-1]

        return {
            "status": "success",
            "description": final_message.content.strip(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# from typing import Annotated
# from config import settings
# from fastapi import APIRouter, Depends, HTTPException
# from langchain_core.messages import ToolMessage
# from langchain_core.tools import tool
# from langchain.chat_models import init_chat_model
# from models import RoleChecker
# from pydantic import BaseModel
# import psycopg
# from schemas import User
# from dependecy import UserRolesf

# router = APIRouter()

# # Initialize the Gemini model
# model = init_chat_model(
#     "google_genai:gemini-2.5-flash", google_api_key=settings.GOOGLE_API_KEY
# )


# def get_database_schema() -> str:
#   """Inspects the PostgreSQL database dynamically to extract table names and columns."""
#   try:
#     connection_url = settings.DATABASE_URL.get_secret_value()
#     with psycopg.connect(connection_url) as conn:
#       with conn.cursor() as cursor:
#         # Query to fetch all tables and their columns in public schema
#         cursor.execute("""
#                     SELECT table_name, column_name, data_type 
#                     FROM information_schema.columns 
#                     WHERE table_schema = 'public'
#                     ORDER BY table_name, ordinal_position;
#                 """)
#         rows = cursor.fetchall()

#         if not rows:
#           return "No tables found in the database schema."

#         schema_dict = {}
#         for table_name, column_name, data_type in rows:
#           if table_name not in schema_dict:
#             schema_dict[table_name] = []
#           schema_dict[table_name].append(f"{column_name} ({data_type})")

#         schema_summary = []
#         for table, cols in schema_dict.items():
#           schema_summary.append(
#               f"- Table `{table}`: " + ", ".join(cols)
#           )

#         return "\n".join(schema_summary)
#   except Exception as e:
#     return f"Could not retrieve schema: {str(e)}"


# @tool
# def execute_sql_query(sql_query: str) -> str:
#   """Executes a read-only SQL query against the PostgreSQL database and returns the results."""
#   try:
#     connection_url = settings.DATABASE_URL.get_secret_value()
#     cleaned_query = sql_query.strip().lower()

#     if not cleaned_query.startswith("select"):
#       return "Error: Only SELECT queries are allowed for security reasons."

#     with psycopg.connect(connection_url) as conn:
#       with conn.cursor() as cursor:
#         cursor.execute(sql_query)
#         rows = cursor.fetchall()

#     if not rows:
#       return "The query executed successfully, but returned no rows."

#     return str(rows)
#   except Exception as e:
#     # Returning the error back to the LLM allows it to self-correct its SQL syntax!
#     return f"SQL execution failed: {str(e)}"


# class DescriptionRequest(BaseModel):
#   prompt: str


# @router.post("/description")
# async def get_user_descriptions(
#     request: DescriptionRequest,
#     current_user: Annotated[
#         User, Depends(RoleChecker([UserRolesf.PREMIUM]))
#     ],
# ):
#   try:
#     tools = [execute_sql_query]
#     model_with_tools = model.bind_tools(tools)

#     # Dynamically inject the actual database layout so the AI isn't guessing blind
#     live_schema = get_database_schema()

#     system_instruction = (
#         "You are an expert PostgreSQL database analyst. Your job is to take a user's natural language request, "
#         "write an appropriate SQL query, use the `execute_sql_query` tool to run it, and then provide a "
#         "concise, professional plain-text summary of the results.\n\n"
#         f"DATABASE SCHEMA:\n{live_schema}\n\n"
#         "CRITICAL RULES:\n"
#         "- Output ONLY plain text sentences for your final response.\n"
#         "- Do NOT output JSON wrappers, code blocks, or dictionary syntax.\n"
#         "- Keep your response direct and brief."
#     )

#     messages = [("system", system_instruction), ("user", request.prompt)]

#     # Allow up to 4 turns for multi-step execution / self-correction if a query fails
#     for _ in range(4):
#       response = model_with_tools.invoke(messages)

#       # If the model didn't request a tool call, we have our final text answer
#       if not response.tool_calls:
#         return {
#             "status": "success",
#             "description": response.content.strip(),
#         }

#       # Append model's tool-requesting message to conversation history
#       messages.append(response)

#       # Execute each requested tool and feed the output back as a ToolMessage
#       for tool_call in response.tool_calls:
#         tool_output = execute_sql_query.invoke(tool_call["args"])
#         messages.append(
#             ToolMessage(content=str(tool_output), tool_call_id=tool_call["id"])
#         )

#     raise HTTPException(
#         status_code=500, detail="Agent exceeded maximum iteration steps."
#     )

#   except Exception as e:
#     raise HTTPException(status_code=500, detail=str(e))

# from langchain.chat_models import init_chat_model
# from config import settings
# from fastapi import APIRouter, HTTPException, Depends
# from pydantic import BaseModel
# import psycopg
# from langchain_core.tools import tool
# from langchain_core.messages import ToolMessage
# from schemas import User
# from models import RoleChecker
# from dependecy import UserRolesf
# from typing import Annotated

# router = APIRouter()

# model = init_chat_model("google_genai:gemini-2.5-flash", google_api_key=settings.GOOGLE_API_KEY)

# @tool
# def execute_sql_query(sql_query: str) -> str:
#     """Executes a read-only SQL query against the PostgreSQL database and returns the results."""
#     try:
#         connection_url = settings.DATABASE_URL.get_secret_value()
#         conn = psycopg.connect(connection_url)
#         cursor = conn.cursor()
        
#         cleaned_query = sql_query.strip().lower()
#         if not cleaned_query.startswith("select"):
#             return "Error: Only SELECT queries are allowed for security reasons."
            
#         cursor.execute(sql_query)
#         rows = cursor.fetchall()
        
#         cursor.close()
#         conn.close()
        
#         if not rows:
#             return "The query executed successfully, but returned no rows."
            
#         return str(rows)
#     except Exception as e:
#         return f"SQL execution failed: {str(e)}"

# class DescriptionRequest(BaseModel):
#     prompt: str

# @router.post("/description")
# async def get_user_descriptions(request: DescriptionRequest, current_user: Annotated[User, Depends(RoleChecker([UserRolesf.PREMIUM]))]):
# #async def get_user_descriptions(request: DescriptionRequest):    
#     try:
#         tools = [execute_sql_query]
#         model_with_tools = model.bind_tools(tools)
        
#         system_instruction = (
#             "You are an expert PostgreSQL database analyst. Your job is to take a user's natural language request, "
#             "write an appropriate SQL query, use the `execute_sql_query` tool to run it, and then provide a "
#             "concise, professional plain-text summary of the results.\n\n"
#             "CRITICAL RULES:\n"
#             "- Output ONLY plain text sentences for your final response.\n"
#             "- Do NOT output JSON wrappers, code blocks, or dictionary syntax.\n"
#             "- Keep your response direct and brief."
#         )
        
#         messages = [
#             ("system", system_instruction),
#             ("user", request.prompt)
#         ]
        
#         response = model_with_tools.invoke(messages)
        
#         if response.tool_calls:
#             tool_call = response.tool_calls[0]
#             tool_call_id = tool_call["id"]
            
#             tool_output = execute_sql_query.invoke(tool_call["args"])
            
#             final_messages = messages + [
#                 response,
#                 ToolMessage(content=tool_output, tool_call_id=tool_call_id)
#             ]
#             final_response = model.invoke(final_messages)
#             description_text = final_response.content
#         else:
#             description_text = response.content

#         return {
#             "status": "success",
#             "description": description_text.strip()
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
