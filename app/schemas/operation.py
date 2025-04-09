from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date

class OperationBase(BaseModel):
    date: date
    vehicle_id: str
    driver_id: str
    morning_collection: float = Field(default=0.0, ge=0.0)
    evening_collection: float = Field(default=0.0, ge=0.0)
    fuel_expense: float = Field(default=0.0, ge=0.0)
    repair_expense: float = Field(default=0.0, ge=0.0)
    notes: Optional[str] = None

class OperationCreate(OperationBase):
    pass

class OperationUpdate(BaseModel):
    morning_collection: Optional[float] = Field(default=None, ge=0.0)
    evening_collection: Optional[float] = Field(default=None, ge=0.0)
    fuel_expense: Optional[float] = Field(default=None, ge=0.0) 
    repair_expense: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = None

class OperationInDB(OperationBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OperationResponse(OperationBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    
    # Include additional fields for easy display
    vehicle_reg_no: Optional[str] = None
    driver_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class DateRangeParams(BaseModel):
    start_date: date
    end_date: date

class OperationSummary(BaseModel):
    date: date
    total_collections: float
    total_expenses: float
    net_income: float
    vehicles_count: int
    
class DashboardStats(BaseModel):
    total_vehicles: int
    active_vehicles: int
    total_drivers: int
    active_drivers: int
    today_collections: float
    today_expenses: float
    weekly_collections: List[Dict[str, Any]]
    monthly_collections: List[Dict[str, Any]]
    vehicle_performance: List[Dict[str, Any]]
    driver_performance: List[Dict[str, Any]] 