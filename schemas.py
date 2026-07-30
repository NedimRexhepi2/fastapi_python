from database import Base
from sqlalchemy import String, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column
from dependecy import UserRolesf


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default=UserRolesf.USER, nullable=False)
