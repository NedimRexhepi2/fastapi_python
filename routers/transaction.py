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
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from config import settings

router = APIRouter()

embeddings_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001", 
    google_api_key=settings.GOOGLE_API_KEY,
    output_dimensionality=768
)

@router.post("/transact", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    if current_user.id == payload.to_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot send money to yourself."
        )

    recipient_stmt = select(User).where(User.id == payload.to_user_id)
    recipient = db.scalars(recipient_stmt).first()

    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found."
        )

    if current_user.balance < payload.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient funds."
        )

    try:
        current_user.balance -= payload.amount
        recipient.balance += payload.amount


        vector_embedding = None

        description_text = getattr(payload, "description", None)
        
        if description_text:
            vector_embedding = embeddings_model.embed_query(description_text)

        new_transaction = Transaction(
            from_user_id=current_user.id,
            to_user_id=recipient.id,
            amount=payload.amount,
            date=date.today(),
            description=description_text,
            embedding=vector_embedding
        )

        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)

        return new_transaction

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )