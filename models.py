from pydantic import BaseModel
from enum import Enum



class UserRole(str, Enum):
    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"


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
