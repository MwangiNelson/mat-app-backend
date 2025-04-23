from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class DriverStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class DriverBase(BaseModel):
    name: str
    license_no: str
    phone: str
    status: DriverStatus = DriverStatus.ACTIVE
    experience: Optional[str] = None
    rating: Optional[float] = Field(default=0.0, ge=0.0, le=5.0)
    photo_url: Optional[str] = None

class DriverCreate(DriverBase):
    pass

class DriverUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[DriverStatus] = None
    experience: Optional[str] = None
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    photo_url: Optional[str] = None
    license_no: Optional[str] = None
class DriverInDB(DriverBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DriverResponse(DriverBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DriverRating(BaseModel):
    rating: float = Field(..., ge=0.0, le=5.0) 