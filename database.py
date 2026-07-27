from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import create_engine

engine = create_engine("postgresql://local_user:local_password@localhost:5432/my_fastapi_db")

SessionLocal=sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass


def get_session():
    with SessionLocal() as db:
        yield db
