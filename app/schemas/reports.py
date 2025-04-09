from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date

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

    class Config:
        from_attributes = True

class DailySummaryDetail(DailySummaryResponse):
    vehicle_registration: str
    driver_name: Optional[str] = None 