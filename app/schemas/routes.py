from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum
from uuid import UUID

class RouteStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class RouteBase(BaseModel):
    name: str
    origin: str
    destination: str
    fare_amount: float
    distance: Optional[float] = None
    estimated_duration: Optional[int] = None
    status: RouteStatus = RouteStatus.ACTIVE
    description: Optional[str] = None

class RouteCreate(RouteBase):
    pass

class RouteUpdate(BaseModel):
    name: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    fare_amount: Optional[float] = None
    distance: Optional[float] = None
    estimated_duration: Optional[int] = None
    status: Optional[RouteStatus] = None
    description: Optional[str] = None

class RouteResponse(RouteBase):
    id: str
    created_at: datetime
    updated_at: datetime

    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, UUID):
            return str(v)
        return v

    class Config:
        from_attributes = True 