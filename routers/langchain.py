from langchain.chat_models import init_chat_model
from config import settings
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import psycopg
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage
from schemas import User
from models import RoleChecker
from dependecy import UserRolesf
from typing import Annotated

router = APIRouter()

model = init_chat_model("google_genai:gemini-2.5-flash", google_api_key=settings.GOOGLE_API_KEY)

@tool
def execute_sql_query(sql_query: str) -> str:
    """Executes a read-only SQL query against the PostgreSQL database and returns the results."""
    try:
        connection_url = settings.DATABASE_URL.get_secret_value()
        conn = psycopg.connect(connection_url)
        cursor = conn.cursor()
        
        cleaned_query = sql_query.strip().lower()
        if not cleaned_query.startswith("select"):
            return "Error: Only SELECT queries are allowed for security reasons."
            
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if not rows:
            return "The query executed successfully, but returned no rows."
            
        return str(rows)
    except Exception as e:
        return f"SQL execution failed: {str(e)}"

class DescriptionRequest(BaseModel):
    prompt: str

@router.post("/description")
async def get_user_descriptions(request: DescriptionRequest, current_user: Annotated[User, Depends(RoleChecker([UserRolesf.PREMIUM]))]):
#async def get_user_descriptions(request: DescriptionRequest):    
    try:
        tools = [execute_sql_query]
        model_with_tools = model.bind_tools(tools)
        
        system_instruction = (
            "You are an expert PostgreSQL database analyst. Your job is to take a user's natural language request, "
            "write an appropriate SQL query, use the `execute_sql_query` tool to run it, and then provide a "
            "concise, professional plain-text summary of the results.\n\n"
            "CRITICAL RULES:\n"
            "- Output ONLY plain text sentences for your final response.\n"
            "- Do NOT output JSON wrappers, code blocks, or dictionary syntax.\n"
            "- Keep your response direct and brief."
        )
        
        messages = [
            ("system", system_instruction),
            ("user", request.prompt)
        ]
        
        response = model_with_tools.invoke(messages)
        
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            tool_call_id = tool_call["id"]
            
            tool_output = execute_sql_query.invoke(tool_call["args"])
            
            final_messages = messages + [
                response,
                ToolMessage(content=tool_output, tool_call_id=tool_call_id)
            ]
            final_response = model.invoke(final_messages)
            description_text = final_response.content
        else:
            description_text = response.content

        return {
            "status": "success",
            "description": description_text.strip()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# from langchain.chat_models import init_chat_model
# from config import settings
# from fastapi import APIRouter, HTTPException, Query
# import psycopg
# from langchain_core.tools import tool

# router = APIRouter()

# model = init_chat_model("google_genai:gemini-2.5-flash", google_api_key=settings.GOOGLE_API_KEY)

# @tool
# def execute_sql_query(sql_query: str) -> str:
#     """Executes a read-only SQL query against the PostgreSQL database and returns the results."""
#     try:
#         connection_url = settings.DATABASE_URL.get_secret_value()
#         conn = psycopg.connect(connection_url)
#         cursor = conn.cursor()
        
#         # Safety check: Ensure it's a safe query (optional basic safeguard)
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

# @router.get("/description")
# async def get_user_descriptions(prompt: str = Query(..., description="Natural language prompt from the frontend")):
#     try:
#         # 1. Bind the tool to the model so Gemini can generate the SQL query dynamically
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
        
#         # 2. Invoke the model with the user's frontend prompt
#         messages = [
#             ("system", system_instruction),
#             ("user", prompt)
#         ]
        
#         response = model_with_tools.invoke(messages)
        
#         # 3. Check if the model wants to call the tool
#         if response.tool_calls:
#             # Execute the tool call requested by the model
#             tool_call = response.tool_calls[0]
#             tool_output = execute_sql_query.invoke(tool_call["args"])
            
#             # Send the tool output back to the model to synthesize the final plain-text response
#             final_messages = messages + [
#                 response,
#                 ("tool", tool_output)
#             ]
#             final_response = model.invoke(final_messages)
#             description_text = final_response.content
#         else:
#             # If no tool was needed, use the model's direct response
#             description_text = response.content

#         return {
#             "status": "success",
#             "description": description_text.strip()
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# from langchain.chat_models import init_chat_model
# from config import settings
# from fastapi import APIRouter, HTTPException
# import psycopg
# from langchain_core.tools import tool

# router = APIRouter()

# model = init_chat_model("google_genai:gemini-2.5-flash", google_api_key=settings.GOOGLE_API_KEY)

# @tool
# def fetch_users_from_db(limit: int = 100) -> str:
#     """Queries the PostgreSQL database to fetch raw user records and profiles for analysis."""
#     try:
#         connection_url = settings.DATABASE_URL.get_secret_value()
#         conn = psycopg.connect(connection_url)
#         cursor = conn.cursor()
#         cursor.execute("SELECT id, username, password FROM users LIMIT %s;", (limit,))
#         rows = cursor.fetchall()
        
#         cursor.close()
#         conn.close()
        
#         if not rows:
#             return "No users found in the database."
            
#         return str(rows)
#     except Exception as e:
#         return f"Database query failed: {str(e)}"

# @router.get("/description")
# async def get_user_descriptions():
#     try:
#         # 1. Fetch raw data directly via your tool function (bypasses agent overhead/token bloat)
#         db_data = fetch_users_from_db.invoke({"limit": 100})
        
#         # 2. Construct a direct prompt with system context and data
#         prompt = (
#             "You are an expert data analyst assistant. Analyze the following raw database user records "
#             "and write a concise, professional summary description of the user base.\n\n"
#             "CRITICAL RULES:\n"
#             "- Output ONLY plain text sentences.\n"
#             "- Do NOT output JSON, code blocks, dictionaries, or lists.\n"
#             "- Keep your response direct and brief to conserve tokens.\n\n"
#             f"Raw Data: {db_data}"
#         )
        
#         # 3. Invoke model directly in a single turn
#         response = model.invoke(prompt)
        
#         # Extract pure string content
#         description_text = response.content if hasattr(response, "content") else str(response)

#         return {
#             "status": "success",
#             "description": description_text.strip()
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
# from langchain.chat_models import init_chat_model
# from config import settings
# from fastapi import APIRouter, HTTPException
# import psycopg
# from langchain_core.tools import tool
# from langchain.agents import create_agent
# import json

# router = APIRouter()

# model= init_chat_model("google_genai:gemini-2.5-flash", google_api_key=settings.GOOGLE_API_KEY)

# @tool
# def fetch_users_from_db(limit: int = 100) -> str:
#     """Queries the PostgreSQL database to fetch raw user records and profiles for analysis."""
#     try:
        
#         connection_url = settings.DATABASE_URL.get_secret_value()
#         conn = psycopg.connect(connection_url)
#         cursor = conn.cursor()
#         cursor.execute("SELECT id, username, password FROM users LIMIT %s;", (limit,))
#         rows = cursor.fetchall()
        
#         cursor.close()
#         conn.close()
        
#         if not rows:
#             return "No users found in the database."
            
#         return str(rows)
#     except Exception as e:
#         return f"Database query failed: {str(e)}"


# system_prompt = (
#     "You are an expert data analyst assistant. Your job is to look at raw user data "
#     "retrieved from a PostgreSQL database via tools, analyze their behavioral attributes, "
#     "and write a concise, professional summary description of the user base.\n\n"
#     "CRITICAL RULES:\n"
#     "- Output ONLY plain text sentences.\n"
#     "- Do NOT output JSON, code blocks, dictionaries, or lists.\n"
#     "- Keep your response direct and brief to conserve tokens."
# )
# tools = [fetch_users_from_db]
# agent_executor = create_agent(model, tools, system_prompt=system_prompt)


# @router.get("/description")
# async def get_user_descriptions():
#     try:
#         response = agent_executor.invoke({
#             "messages": [("user", "Fetch the latest users from the database and generate a comprehensive summary description of our user base.")]
#         })
        
#         final_message = response["messages"][-1].content
        
#         # If the LLM returned a JSON string, parse it to extract just the text value
#         try:
#             parsed_json = json.loads(final_message)
#             # Navigate to the text field inside description
#             description_text = parsed_json["description"][0]["text"]
#         except (json.JSONDecodeError, KeyError, TypeError):
#             # Fallback if the model just returned normal text directly
#             description_text = final_message
        
#         return {
#             "status": "success",
#             "description": description_text
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


