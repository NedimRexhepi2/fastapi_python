from fastapi import APIRouter, Depends, HTTPException, status
from models import UserModel, UserModelCreate, UserModelEdit
from schemas import User
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Annotated
from database import get_session


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
    result.average = user.average
    result.nickname = user.nickname
    result.parent = user.parent
    db.commit()
    db.refresh(result)
    return result


@router.post("/createuser", response_model=UserModel)
async def create_user_db(
    user: UserModelCreate, db: Annotated[Session, Depends(get_session)]
):
    result = db.execute(
        select(User).where(User.username == user.username),
    )

    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="user already registered"
        )

    new_user = User(
        username=user.username,
        average=user.average,
        nickname=user.nickname,
        parent=user.parent,
    )
    db.add(new_user)
    db.commit()
    db.refresh(instance=new_user)
    return new_user


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
