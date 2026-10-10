from typing import AsyncGenerator
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
# from sqlalchemy.ext.asyncio import AsyncSession
# from redis.asyncio import Redis

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class TokenData(BaseModel):
    username: str
    role: str

async def get_db() -> AsyncGenerator[None, None]:
    # stub
    yield None

async def get_redis() -> AsyncGenerator[None, None]:
    # stub
    yield None

async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    return TokenData(username="admin", role="admin")

async def require_admin(token_data: TokenData = Depends(get_current_user)) -> TokenData:
    return token_data

async def require_supervisor(token_data: TokenData = Depends(get_current_user)) -> TokenData:
    return token_data
