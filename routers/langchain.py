from langchain.chat_models import init_chat_model
from config import settings
from fastapi import APIRouter, HTTPException
import psycopg2
from langchain_core.tools import tool
from langchain.agents import create_agent

router = APIRouter()

model= init_chat_model("google_genai:gemini-2.5-flash", google_api_key=settings.GOOGLE_API_KEY)

@tool
def fetch_users_from_db(limit: int = 100) -> str:
    """Queries the PostgreSQL database to fetch raw user records and profiles for analysis."""
    try:
        
        connection_url = settings.DATABASE_URL.get_secret_value()
        conn = psycopg2.connect(connection_url)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password FROM users LIMIT %s;", (limit,))
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if not rows:
            return "No users found in the database."
            
        return str(rows)
    except Exception as e:
        return f"Database query failed: {str(e)}"


system_prompt = (
    "You are an expert data analyst assistant. Your job is to look at raw user data "
    "retrieved from a PostgreSQL database via tools, analyze their behavioral attributes, "
    "and write a concise, professional summary description of the user base."
)

tools = [fetch_users_from_db]
agent_executor = create_agent(model, tools, system_prompt=system_prompt)


@router.get("/description")
async def get_user_descriptions():
    try:
   
        response = agent_executor.invoke({
            "messages": [("user", "Fetch the latest users from the database and generate a comprehensive summary description of our user base.")]
        })
        
        final_message = response["messages"][-1].content
        
        return {
            "status": "success",
            "description": final_message
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


