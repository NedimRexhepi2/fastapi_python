from pydantic import BaseModel
from enum import Enum
from fastapi import Depends, HTTPException, status, Request
from schemas import User
from typing import Annotated, Optional
from config import settings
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session
from database import get_session
from dependecy import UserRolesf

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
        payload = jwt.decode(token, settings.SECRET_KEY.get_secret_value(), algorithms=[settings.ALGORITHM])
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

class RoleChecker:
    def __init__(self, allowed_roles: list[UserRolesf]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        return current_user

class UserModel(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True

class UserModelCreate(BaseModel):
    username: str
    password: str


class UserModelEdit(BaseModel):
    username: str
