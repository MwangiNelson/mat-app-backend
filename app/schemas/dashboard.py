from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum

class TimeSeriesData(BaseModel):
    """Time series data for charts"""
    label: str  # Date or time period
    value: float  # Value for that period

class ExpiringLicense(BaseModel):
    """Information about a license that is expiring"""
    license: str
    days_left: int

class VehicleRenewal(BaseModel):
    """Vehicle with expiring licenses"""
    vehicle_name: str
    expiring_licenses: List[ExpiringLicense]

class DashboardOverview(BaseModel):
    """Dashboard overview statistics for the finance cards"""
    total_revenue_today: float
    active_vehicles_count: int
    total_vehicles_count: int  # Total number of vehicles
    upcoming_renewals: int
    renewals: List[VehicleRenewal] = []  # Detailed information about upcoming renewals
    avg_collection_per_vehicle: float
    revenue_comparison: float  # Revenue comparison between today and yesterday
    vehicle_utilization: float  # Vehicle utilization percentage
    avg_collection_comparison: float  # Average collection compared to previous week
    
class VehiclePerformance(BaseModel):
    """Performance metrics for a vehicle"""
    vehicle_id: str
    registration: str
    total_collections: float
    total_expenses: float
    fuel_expense: float = 0
    repair_expense: float = 0
    net_profit: float
    trip_count: int
    profit_per_trip: float = 0
    collection_per_trip: float = 0
    expense_ratio: float = 0  # Expenses as percentage of collections
    utilization_rate: Optional[float] = None  # Percentage of days vehicle was used

class DetailedVehiclePerformance(VehiclePerformance):
    """Detailed performance metrics with time series data"""
    collections_by_day: List[TimeSeriesData] = []
    expenses_by_day: List[TimeSeriesData] = []
    profit_by_day: List[TimeSeriesData] = []
    trips_by_day: List[TimeSeriesData] = []

class VehiclePerformanceList(BaseModel):
    """List of vehicle performance data with summary metrics"""
    vehicles: List[VehiclePerformance]
    total_vehicles: int
    total_collections: float
    total_profit: float
    average_profit_per_vehicle: float
    start_date: date
    end_date: date

class DriverPerformance(BaseModel):
    """Performance metrics for a driver"""
    driver_id: str
    name: str
    total_collections: float
    trip_count: int
    avg_per_trip: float
    collection_efficiency: float = 0  # Collected amount vs expected amount
    total_vehicles_driven: int = 0
    most_driven_vehicle: Optional[str] = None

class DetailedDriverPerformance(DriverPerformance):
    """Detailed driver performance with time series data"""
    collections_by_day: List[TimeSeriesData] = []
    trips_by_day: List[TimeSeriesData] = []
    vehicles_driven: List[Dict[str, Any]] = []

class DriverPerformanceList(BaseModel):
    """List of driver performance data with summary metrics"""
    drivers: List[DriverPerformance]
    total_drivers: int
    total_collections: float
    average_collections_per_driver: float
    start_date: date
    end_date: date

class DashboardStats(BaseModel):
    """Comprehensive dashboard statistics"""
    overview: DashboardOverview
    top_vehicles: List[VehiclePerformance]
    top_drivers: List[DriverPerformance]
    revenue_by_day: List[TimeSeriesData]
    expenses_by_day: List[TimeSeriesData]
    profit_by_day: List[TimeSeriesData]

class CollectionTrendItem(BaseModel):
    """Daily collection and expense trend item"""
    date: str
    collection_amount: float
    fuel_expense: float
    repair_expense: float
    total_expense: float

class CollectionTrend(BaseModel):
    """Collection trend data with date range"""
    start_date: date
    end_date: date
    trend_data: List[CollectionTrendItem]

class PerformanceSummary(BaseModel):
    """Summary of performance metrics across selected vehicles and drivers"""
    total_collections: float
    total_expenses: float
    fuel_expense: float
    repair_expense: float
    net_revenue: float
    trip_count: int
    start_date: date
    end_date: date
    vehicle_ids: Optional[List[str]] = None
    driver_ids: Optional[List[str]] = None

class ReportFormat(str, Enum):
    """Format options for generated reports"""
    PDF = "pdf"
    HTML = "html"

class ReportResponse(BaseModel):
    """Response with report file information"""
    filename: str
    content_type: str
    file_content: str  # Base64 encoded file content 