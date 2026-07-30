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
from routers import items, units, users, langchain
from schemas import User
from config import settings
from models import get_current_user, RoleChecker, UserModel, UserModelCreate
from dependecy import UserRolesf

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
app.include_router(langchain.router, prefix="/api/langchain/bot", tags=["bot"])



    
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
    return jwt.encode(to_encode, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)


# def get_current_user(
#     request: Request,
#     db: Annotated[Session, Depends(get_session)],
# ):
#     credentials_exception = HTTPException(
#         status_code=status.HTTP_401_UNAUTHORIZED,
#         detail="Could not validate credentials or session expired",
#     )

#     token = request.cookies.get("access_token")
#     if not token:
#         raise credentials_exception

#     try:
#         payload = jwt.decode(token, settings.SECRET_KEY.get_secret_value(), algorithms=[settings.ALGORITHM])
#         username: Optional[str] = payload.get("sub")
#         if username is None:
#             raise credentials_exception
#     except JWTError as e:
#         print(f"JWT Decode Exception: {e}")
#         raise credentials_exception

#     stmt = select(User).where(User.username == username)
#     user = db.scalars(stmt).first()

#     if user is None:
#         raise credentials_exception
#     return user

# class RoleChecker:
#     def __init__(self, allowed_roles: list[UserRole]):
#         self.allowed_roles = allowed_roles

#     def __call__(self, current_user: Annotated[User, Depends(get_current_user)]) -> User:
#         if current_user.role not in self.allowed_roles:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Access denied",
#             )
#         return current_user

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
        username=user_data.username, password=hash_password(user_data.password), role=UserRolesf.USER
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
    current_user: Annotated[User, Depends(RoleChecker([UserRolesf.USER, UserRolesf.PREMIUM]))]
):
    return {"message": f"Welcome to the zone, {current_user.username}!"}
@app.get("/premium-endpoint")
def premium_route(
    current_user: Annotated[User, Depends(RoleChecker([UserRolesf.PREMIUM]))]
):
    return {"message": f"Welcome to the premium zone, {current_user.username}!"}