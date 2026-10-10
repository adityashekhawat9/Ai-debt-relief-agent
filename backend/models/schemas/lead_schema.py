from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr

class LeadCreate(BaseModel):
    phone: str
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    state: str | None = None
    country: str = "US"
    timezone: str | None = None
    phone_type: Literal["mobile", "landline", "voip"] | None = None
    has_consent: bool = False
    source: str | None = None

class LeadUpdate(BaseModel):
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    state: str | None = None
    country: str | None = None
    timezone: str | None = None
    phone_type: Literal["mobile", "landline", "voip"] | None = None
    has_consent: bool | None = None
    call_attempts: int | None = None
    last_called_at: datetime | None = None
    dnc_flagged: bool | None = None
    status: str | None = None
    source: str | None = None

class LeadRead(BaseModel):
    id: UUID
    phone: str
    first_name: str | None
    last_name: str | None
    email: str | None
    state: str | None
    country: str
    timezone: str | None
    phone_type: str | None
    has_consent: bool
    call_attempts: int
    last_called_at: datetime | None
    dnc_flagged: bool
    status: str
    source: str | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class LeadListResponse(BaseModel):
    items: list[LeadRead]
    total: int
    page: int
    page_size: int
