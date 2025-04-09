from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
from enum import Enum

class VehicleStatus(str, Enum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    INACTIVE = "inactive"

class VehicleBase(BaseModel):
    registration: str
    model: str
    owner: str
    status: VehicleStatus = VehicleStatus.ACTIVE
    insurance_expiry: date
    tlb_expiry: date
    passenger_capacity: int
    route_id: Optional[str] = None

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    model: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[VehicleStatus] = None
    insurance_expiry: Optional[date] = None
    tlb_expiry: Optional[date] = None
    passenger_capacity: Optional[int] = None
    route_id: Optional[str] = None

class VehicleInDB(VehicleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class VehicleResponse(VehicleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class VehicleDetail(VehicleResponse):
    route_name: Optional[str] = None 