
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from typing import Annotated, Optional
from config import settings
from sqlalchemy import select
from sqlalchemy.orm import Session
from dependencies.schemas import User
from fastapi import Depends, HTTPException, status, Request
from database import get_session


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

def find_user_db(user_id: int, db: Annotated[Session, Depends(get_session)]):
    result = db.execute(select(User).where(user_id == User.id)).scalars().first()
    return result

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