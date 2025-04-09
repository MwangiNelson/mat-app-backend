from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class LocationBase(BaseModel):
    driver_id: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)

class LocationCreate(LocationBase):
    pass

class LocationInDB(LocationBase):
    id: str
    timestamp: datetime

    class Config:
        from_attributes = True

class LocationResponse(LocationBase):
    id: str
    timestamp: datetime
    driver_name: Optional[str] = None

    class Config:
        from_attributes = True

class TripStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class RoutePoint(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    timestamp: datetime

class TripBase(BaseModel):
    driver_id: str
    vehicle_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    route: Optional[List[RoutePoint]] = []
    status: TripStatus = TripStatus.ACTIVE

class TripCreate(BaseModel):
    driver_id: str
    vehicle_id: str

class TripUpdate(BaseModel):
    end_time: Optional[datetime] = None
    route_point: Optional[RoutePoint] = None
    status: Optional[TripStatus] = None

class TripInDB(TripBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True

class TripResponse(TripBase):
    id: str
    created_at: datetime
    driver_name: Optional[str] = None
    vehicle_reg_no: Optional[str] = None

    class Config:
        from_attributes = True 