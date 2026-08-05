from pydantic import BaseModel,field_validator
import re

class UserModel(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True

class UserModelCreate(BaseModel):
    username: str
    password: str

@field_validator("password")
@classmethod
def validate_password(cls, v: str) -> str:
    if len(v) < 8:
      raise ValueError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", v):
      raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[0-9]", v):
      raise ValueError("Password must contain at least one number.")
    return v

class UserModelEdit(BaseModel):
    username: str
