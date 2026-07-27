from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import bcrypt
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_session
from models import UserModel, UserModelCreate
from routers import items, units, users
from schemas import User
from config import settings



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(units.router, prefix="/api/units", tags=["units"])
app.include_router(items.router, prefix="/api/items", tags=["items"])


def hash_password(password: str):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str):
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or session expired",
    )

    token = request.cookies.get("access_token")
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as e:
        print(f"JWT Decode Exception: {e}")
        raise credentials_exception

    stmt = select(User).where(User.username == username)
    user = db.scalars(stmt).first()

    if user is None:
        raise credentials_exception
    return user


@app.post("/createuser", response_model=UserModel, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserModelCreate, db: Annotated[Session, Depends(get_session)]
):
    stmt = select(User).where(User.username == user_data.username)
    if db.scalars(stmt).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    new_user = User(
        username=user_data.username, password=hash_password(user_data.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/token")
def login_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_session)],
):
    stmt = select(User).where(User.username == form_data.username)
    user = db.scalars(stmt).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(data={"sub": user.username})

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False,
    )

    return {"message": "Login successful"}


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", samesite="lax")
    return {"message": "Logged out successfully"}


@app.get("/users/me", response_model=UserModel)
def read_current_user(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# if not GEMINI_API_KEY:
#     raise RuntimeError("Missing GEMINI_API_KEY environment variable.")


# client = genai.Client(api_key=GEMINI_API_KEY)
# MODEL_ID = "gemini-2.5-flash"


# class ChatPayload(BaseModel):
#     message: str = Field(..., min_length=1, max_length=50)

# class AgentResponse(BaseModel):
#     response: str


# @app.post("/agent/chat", response_model=AgentResponse)
# async def run_gemini_agent(payload: ChatPayload):
#     try:
#         config = types.GenerateContentConfig(
#             tools=[types.Tool(google_search=types.GoogleSearch())],
#             temperature=0.3
#         )

#         response = await client.aio.models.generate_content(
#             model=MODEL_ID,
#             contents=payload.message,
#             config=config
#         )

#         return AgentResponse(response=response.text)

#     except Exception as e:
#         # Absolutely zero imports needed for this:
#         error_info = f"Type: {type(e).__name__} | Message: {str(e)}"

#         # This will print directly to your terminal console
#         print("\n!!! DETECTED ERROR !!!")
#         print(error_info)
#         print("!!!!!!!!!!!!!!!!!!!!!!\n")

#         # This sends the actual error straight back to your API response
#         raise HTTPException(
#             status_code=500,
#             detail=error_info
#         )


# import os
# import asyncio
# from fastapi import FastAPI, HTTPException, status
# from pydantic import BaseModel, Field
# from typing import Dict
# from google import genai
# from google.genai import types

# app = FastAPI(title="FastAPI AI Agent with Free Gemini")

# # Ensure your GEMINI_API_KEY environment variable is set
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# if not GEMINI_API_KEY:
#     raise RuntimeError("Missing GEMINI_API_KEY environment variable.")

# client = genai.Client(api_key=GEMINI_API_KEY)
# MODEL_ID = "gemini-2.5-flash"


# # --- 1. DATA SCHEMAS ---

# class ChatPayload(BaseModel):
#     message: str = Field(..., min_length=1, max_length=1000, example="What's the weather like in Tokyo?")
#     session_id: str | None = Field(default=None, description="Provide to continue an existing session")

# class AgentResponse(BaseModel):
#     session_id: str
#     response: str


# # --- 2. IN-MEMORY CHAT REGISTRY ---
# SESSION_REGISTRY: Dict[str, client.chats.Chat] = {}


# # --- 3. THE AGENT ENDPOINT ---

# @app.post("/agent/chat", response_model=AgentResponse)
# async def run_gemini_agent(payload: ChatPayload):
#     try:
#         # 1. Resolve or establish a valid session context
#         active_session = payload.session_id or "default-test-session"

#         # 2. Re-use existing chat history or initialize a clean one with Google Search enabled
#         if active_session not in SESSION_REGISTRY:
#             SESSION_REGISTRY[active_session] = client.chats.create(
#                 model=MODEL_ID,
#                 config=types.GenerateContentConfig(
#                     # Enable Google Search Grounding
#                     tools=[{"google_search": {}}],
#                     temperature=0.3
#                 )
#             )

#         chat = SESSION_REGISTRY[active_session]

#         # 3. Send the message to the active conversation history track
#         # Gemini automatically performs the Google Search under the hood and returns the grounded answer!
#         response = chat.send_message(payload.message)

#         return AgentResponse(session_id=active_session, response=response.text)

#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"The Gemini Agent layer encountered an unexpected error: {str(e)}"
#         )


# from fastapi import FastAPI
# from pydantic import BaseModel, Field
# from typing import List

# app = FastAPI(title="Looping Invoice API")

# class Item(BaseModel):
#     name: str
#     price: float
#     quantity: int

# class OrderRequest(BaseModel):
#     customer_name: str
#     items: List[Item]

# class InvoiceResponse(BaseModel):
#     customer_name: str
#     total_items_processed: int
#     subtotal: float
#     tax_total: float
#     grand_total: float

# @app.post("/calculate-invoice", response_model=InvoiceResponse)
# async def calculate_invoice(payload: OrderRequest):
#     TAX_RATE = 0.18

#     subtotal = 0.0
#     total_items_count = 0

#     for item in payload.items:

#         item_total = item.price * item.quantity

#         subtotal += item_total
#         total_items_count += item.quantity

#     tax_total = subtotal * TAX_RATE
#     grand_total = subtotal + tax_total

#     return InvoiceResponse(
#         customer_name=payload.customer_name,
#         total_items_processed=total_items_count,
#         subtotal=round(subtotal, 2),
#         tax_total=round(tax_total, 2),
#         grand_total=round(grand_total, 2)
#     )
