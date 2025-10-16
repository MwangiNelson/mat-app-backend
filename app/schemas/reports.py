from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, date
from uuid import UUID

class DailySummaryBase(BaseModel):
    vehicle_id: str
    driver_id: Optional[str] = None
    date: date
    trip_count: int
    total_passengers: int
    total_expected_amount: float
    total_collected_amount: float
    total_expenses: float
    net_profit: float

class DailySummaryResponse(DailySummaryBase):
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

class DailySummaryDetail(DailySummaryResponse):
    vehicle_registration: str
    driver_name: Optional[str] = None 