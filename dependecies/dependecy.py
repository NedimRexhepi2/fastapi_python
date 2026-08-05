from enum import Enum
from typing import Annotated
from dependecies.schemas import User
from fastapi import Depends, HTTPException, status
from dependecies.methods import get_current_user

class UserRoles(str, Enum):
    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"


class RoleChecker:
    def __init__(self, allowed_roles: list[UserRoles]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        return current_user