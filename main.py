from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import users, langchain

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(langchain.router, prefix="/api/langchain/bot", tags=["bot"])

