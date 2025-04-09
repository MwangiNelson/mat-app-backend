from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class TripStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TripBase(BaseModel):
    vehicle_id: str
    driver_id: str
    route_id: str
    start_time: datetime
    passenger_count: int = 0
    expected_amount: float
    collected_amount: Optional[float] = None
    fuel_cost: Optional[float] = 0
    other_expenses: Optional[float] = 0
    expenses_notes: Optional[str] = None
    notes: Optional[str] = None
    status: TripStatus = TripStatus.IN_PROGRESS

class TripCreate(TripBase):
    pass

class TripUpdate(BaseModel):
    end_time: Optional[datetime] = None
    passenger_count: Optional[int] = None
    collected_amount: Optional[float] = None
    fuel_cost: Optional[float] = None
    other_expenses: Optional[float] = None
    expenses_notes: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[TripStatus] = None

class TripResponse(TripBase):
    id: str
    end_time: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TripDetail(TripResponse):
    vehicle_registration: str
    driver_name: str
    route_name: str
    origin: str
    destination: str
    fare_amount: float 