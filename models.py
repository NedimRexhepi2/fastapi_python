from pydantic import BaseModel


class UserModel(BaseModel):
    id: int
    username: str


class UserModelCreate(BaseModel):
    username: str
    password: str


class UserModelEdit(BaseModel):
    username: str
