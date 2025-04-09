from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date

class DashboardOverview(BaseModel):
    """Dashboard overview statistics for the finance cards"""
    total_revenue_today: float
    active_vehicles_count: int
    upcoming_renewals: int = 5  # Static value as specified
    avg_collection_per_vehicle: float
    
class VehiclePerformance(BaseModel):
    """Performance metrics for a vehicle"""
    vehicle_id: str
    registration: str
    total_collections: float
    total_expenses: float
    net_profit: float
    trip_count: int

class DriverPerformance(BaseModel):
    """Performance metrics for a driver"""
    driver_id: str
    name: str
    total_collections: float
    trip_count: int
    avg_per_trip: float

class TimeSeriesData(BaseModel):
    """Time series data for charts"""
    label: str  # Date or time period
    value: float  # Value for that period

class DashboardStats(BaseModel):
    """Comprehensive dashboard statistics"""
    overview: DashboardOverview
    top_vehicles: List[VehiclePerformance]
    top_drivers: List[DriverPerformance]
    revenue_by_day: List[TimeSeriesData]
    expenses_by_day: List[TimeSeriesData]
    profit_by_day: List[TimeSeriesData] 