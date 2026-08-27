from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import users, langchain, transaction
from routers.langchain import lifespan

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(langchain.router, prefix="/api/langchain", tags=["bot"])
app.include_router(transaction.router, prefix="/api/transactions", tags=["trans"])