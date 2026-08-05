from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session
from database import get_session
from routers import users, langchain
from dependecies.schemas import User
from config import settings
from dependecies.models import UserModel, UserModelCreate
from dependecies.dependecy import UserRoles, RoleChecker
from dependecies.methods import hash_password, verify_password, create_access_token,get_current_user

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
        username=user_data.username, password=hash_password(user_data.password), role=UserRoles.USER
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

    access_token = create_access_token(data={"sub": user.username, "role": user.role})

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

@app.get("/user-endpoint")
def premium_route(
    current_user: Annotated[User, Depends(RoleChecker([UserRoles.USER, UserRoles.PREMIUM]))]
):
    return {"message": f"Welcome to the zone, {current_user.username}!"}
@app.get("/premium-endpoint")
def premium_route(
    current_user: Annotated[User, Depends(RoleChecker([UserRoles.PREMIUM]))]
):
    return {"message": f"Welcome to the premium zone, {current_user.username}!"}