from fastapi import APIRouter, Depends, HTTPException, status
from dependencies.models import UserModel, UserModelCreate, UserModelEdit
from dependencies.schemas import User
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Annotated
from database import get_session
from dependencies.dependency import UserRoles, RoleChecker
from fastapi.security import OAuth2PasswordRequestForm
from config import settings
from fastapi import Depends, HTTPException, Response, status

from dependencies.methods import hash_password, verify_password, create_access_token,get_current_user

router = APIRouter()


def find_user_db(user_id: int, db: Annotated[Session, Depends(get_session)]):
    result = db.execute(select(User).where(user_id == User.id)).scalars().first()
    return result


@router.put("/updateuser/{user_id}", response_model=UserModel)
async def update_user(
    user_id: int, user: UserModelEdit, db: Annotated[Session, Depends(get_session)]
):
    result = find_user_db(user_id, db)
    result.username = user.username
    db.commit()
    db.refresh(result)
    return result


@router.post("/createuser", response_model=UserModel, status_code=status.HTTP_201_CREATED)
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


@router.post("/token")
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


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", samesite="lax")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserModel)
def read_current_user(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.get("", response_model=list[UserModel])
async def get_users(db: Annotated[Session, Depends(get_session)]):
    result = db.execute(select(User))
    users = result.scalars().all()

    if not users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    return users


@router.delete("/delete/{user_id}", response_model=UserModel)
async def delete_user(user_id: int, db: Annotated[Session, Depends(get_session)]):
    user_found = find_user_db(user_id, db)
    if not user_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    db.delete(user_found)
    db.commit()
    return user_found


@router.get("/{user_id}", response_model=UserModel)
async def get_user(user_id: int, db: Annotated[Session, Depends(get_session)]):
    user_found = find_user_db(user_id, db)
    if not user_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    return user_found

@router.get("/user-endpoint")
def premium_route(
    current_user: Annotated[User, Depends(RoleChecker([UserRoles.USER, UserRoles.PREMIUM]))]
):
    return {"message": f"Welcome to the zone, {current_user.username}!"}

@router.get("/premium-endpoint")
def premium_route(
    current_user: Annotated[User, Depends(RoleChecker([UserRoles.PREMIUM]))]
):
    return {"message": f"Welcome to the premium zone, {current_user.username}!"}
