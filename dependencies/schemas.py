from datetime import date
from database import Base
from decimal import Decimal
from sqlalchemy import String, Integer, Float, ForeignKey,Date, Numeric,CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="user", nullable=False)
   
    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), 
        CheckConstraint("balance >= 0", name="check_user_balance_not_negative"), 
        default=Decimal("0.00"),
        server_default="0.00", 
        nullable=False
    )

    sent_transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        foreign_keys="[Transaction.from_user_id]",
        back_populates="sender",
    )
    received_transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        foreign_keys="[Transaction.to_user_id]",
        back_populates="receiver",
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    from_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    to_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), 
        CheckConstraint("amount > 0", name="check_transaction_amount_positive"), 
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(String, nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
                                                          
    date: Mapped[date] = mapped_column(Date, nullable=False)
    sender: Mapped["User"] = relationship(
        "User", foreign_keys=[from_user_id], back_populates="sent_transactions"
    )
    receiver: Mapped["User"] = relationship(
        "User", foreign_keys=[to_user_id], back_populates="received_transactions"
    )