from dependencies.schemas import User, Transaction
from dependencies.models import TransactionCreate, TransactionResponse

from datetime import date
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from dependencies.methods import get_current_user
from database import get_session

router = APIRouter()

@router.post("/transact", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    # 1. Prevent self-transfer
    if current_user.id == payload.to_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot send money to yourself."
        )

    # 2. Fetch recipient using SQLAlchemy 2.0 select style
    recipient_stmt = select(User).where(User.id == payload.to_user_id)
    recipient = db.scalars(recipient_stmt).first()

    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found."
        )

    # 3. Check if sender has enough balance
    if current_user.balance < payload.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient funds."
        )

    try:
        # 4. Update ledger balances
        current_user.balance -= payload.amount
        recipient.balance += payload.amount

        # 5. Create transaction log
        new_transaction = Transaction(
            from_user_id=current_user.id,
            to_user_id=recipient.id,
            amount=payload.amount,
            date=date.today()
        )

        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)

        return new_transaction

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction failed to process."
        )