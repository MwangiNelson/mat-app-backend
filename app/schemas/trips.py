from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

class TripStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TripBase(BaseModel):
    vehicle_id: str
    driver_id: str
    collection_time: datetime
    route: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    collected_amount: Optional[int] = 0
    fuel_expense: Optional[float] = 0
    repair_expense: Optional[float] = 0
    created_by: str
    route_id: Optional[str] = None
    expected_amount: Optional[float] = 0
    updated_at: Optional[datetime] = None

class TripCreate(BaseModel):
    vehicle_id: str
    driver_id: str
    collection_time: datetime
    route: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None
    created_by: str
    route_id: Optional[str] = None
    expected_amount: Optional[float] = 0
    collected_amount: Optional[int] = 0
    fuel_expense: Optional[float] = 0
    repair_expense: Optional[float] = 0
    updated_at: Optional[datetime] = None

class TripUpdate(BaseModel):
    notes: Optional[str] = None
    status: Optional[TripStatus] = None
    collected_amount: Optional[int] = None
    fuel_expense: Optional[float] = None
    repair_expense: Optional[float] = None
    route_id: Optional[str] = None
    expected_amount: Optional[float] = None
    updated_at: Optional[datetime] = None

class TripResponse(TripBase):
    id: str
    created_at: datetime
    updated_at: datetime 

    class Config:
        from_attributes = True

class TripDetail(TripResponse):
    vehicle_registration: Optional[str] = None
    driver_name: Optional[str] = None
    route_name: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    fare_amount: Optional[float] = None
    collection_date: Optional[str] = None
    collection_time_only: Optional[str] = None 