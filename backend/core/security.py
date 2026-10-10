from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from core.exceptions import AuthenticationError, AuthorizationError

class UserRole(str, Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    AGENT = "agent"

class TokenData(BaseModel):
    sub: str  # user_id
    role: UserRole
    exp: datetime

class SecurityService:
    def __init__(self, secret_key: str, algorithm: str, expire_minutes: int):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expire_minutes = expire_minutes
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        return self.pwd_context.hash(password)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return self.pwd_context.verify(plain, hashed)

    def create_access_token(self, user_id: str, role: UserRole) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.expire_minutes)
        to_encode = {"sub": user_id, "role": role.value, "exp": expire}
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_token(self, token: str) -> TokenData:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            sub: str = payload.get("sub")
            role: str = payload.get("role")
            exp = payload.get("exp")
            if sub is None or role is None or exp is None:
                raise AuthenticationError("Could not validate credentials")
            return TokenData(sub=sub, role=UserRole(role), exp=datetime.fromtimestamp(exp, tz=timezone.utc))
        except JWTError as e:
            raise AuthenticationError("Could not validate credentials") from e

    def require_role(self, token_data: TokenData, required_role: UserRole) -> None:
        role_hierarchy = {
            UserRole.ADMIN: 3,
            UserRole.SUPERVISOR: 2,
            UserRole.AGENT: 1,
        }
        user_level = role_hierarchy.get(token_data.role, 0)
        required_level = role_hierarchy.get(required_role, 99)
        
        if user_level < required_level:
            raise AuthorizationError("Insufficient permissions")
