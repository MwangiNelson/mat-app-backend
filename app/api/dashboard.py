from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Any, Dict, List, Optional
from datetime import datetime, date, time, timedelta

from app.models import get_db
from app.models.models import Trip, Driver, Vehicle, DailySummary
from app.core.security import get_current_active_user
from app.schemas.dashboard import DashboardOverview, DashboardStats, VehiclePerformance, DriverPerformance, TimeSeriesData, CollectionTrend, DetailedVehiclePerformance, VehiclePerformanceList, DetailedDriverPerformance, DriverPerformanceList, PerformanceSummary
from app.schemas.user import ErrorResponse
from app.core.utils import DateTimeEncoder
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_, desc
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

def create_dashboard_error(status_code: int, message: str, error_type: str, details: Dict = None) -> HTTPException:
    """Create standardized dashboard API error response"""
    # Ensure message is a string
    message = str(message)

    error_response = ErrorResponse(
        status="error",
        code=status_code,
        message=message,
        details=details,
        errors=[{"type": error_type, "message": message}]
    )

    # Convert datetime to string in ISO format
    content = json.loads(
        json.dumps(error_response.dict(), cls=DateTimeEncoder)
    )

    return HTTPException(
        status_code=status_code,
        detail=content
    )

def get_financial_overview(db: Session) -> Dict:
    """
    Get financial overview for the dashboard cards:
    - Total revenue today
    - Active vehicles count
    - Total vehicles count
    - Upcoming renewals (static value)
    - Average collection per vehicle
    - Revenue comparison between today and yesterday
    - Vehicle utilization percentage
    - Average collection compared to previous week
    """
    try:
        # Get today's date for filtering
        today = date.today()
        today_str = today.isoformat()
        yesterday = today - timedelta(days=1)
        yesterday_str = yesterday.isoformat()
        week_ago = today - timedelta(days=7)
        
        # 1. Calculate Total Revenue Today
        # Sum collected_amount from trips with collection_time today
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())

        today_trips_result = db.query(func.sum(Trip.collected_amount)).filter(
            Trip.collection_time >= start_of_day,
            Trip.collection_time <= end_of_day
        ).scalar()

        total_revenue_today = float(today_trips_result or 0)

        # 2. Count Active Vehicles
        active_vehicles_count = db.query(func.count(Vehicle.id)).filter(Vehicle.status == "active").scalar()

        # 2.1 Count Total Vehicles (all vehicles regardless of status)
        total_vehicles_count = db.query(func.count(Vehicle.id)).scalar()
        
        # 3. Upcoming Renewals - Calculate based on expiry dates
        # Get vehicles with any license expiring within the next 10 days
        future_date = today + timedelta(days=10)

        # Query vehicles with any expiry date within the threshold
        upcoming_renewal_vehicles = db.query(Vehicle).filter(
            ((Vehicle.insurance_expiry >= today) & (Vehicle.insurance_expiry <= future_date)) |
            ((Vehicle.tlb_expiry >= today) & (Vehicle.tlb_expiry <= future_date)) |
            ((Vehicle.inspection_expiry >= today) & (Vehicle.inspection_expiry <= future_date)) |
            ((Vehicle.speed_governor_expiry >= today) & (Vehicle.speed_governor_expiry <= future_date))
        ).all()

        # Count vehicles with upcoming renewals
        upcoming_renewals = len(upcoming_renewal_vehicles)

        # Prepare detailed renewals information
        renewals = []
        for vehicle in upcoming_renewal_vehicles:
            expiring_licenses = []

            # Check each expiry type
            if vehicle.insurance_expiry and today <= vehicle.insurance_expiry <= future_date:
                days_left = (vehicle.insurance_expiry - today).days
                expiring_licenses.append({"license": "Insurance", "days_left": days_left})

            if vehicle.tlb_expiry and today <= vehicle.tlb_expiry <= future_date:
                days_left = (vehicle.tlb_expiry - today).days
                expiring_licenses.append({"license": "TLB", "days_left": days_left})

            if vehicle.inspection_expiry and today <= vehicle.inspection_expiry <= future_date:
                days_left = (vehicle.inspection_expiry - today).days
                expiring_licenses.append({"license": "Inspection", "days_left": days_left})

            if vehicle.speed_governor_expiry and today <= vehicle.speed_governor_expiry <= future_date:
                days_left = (vehicle.speed_governor_expiry - today).days
                expiring_licenses.append({"license": "Speed Governor", "days_left": days_left})

            if expiring_licenses:
                renewals.append({
                    "vehicle_name": vehicle.reg_no,
                    "expiring_licenses": expiring_licenses
                })
        
        # 4. Average Collection Per Vehicle
        # Get all vehicles count
        total_vehicles_for_avg = db.query(func.count(Vehicle.id)).scalar()

        # Get all trips from the last 30 days to calculate average
        thirty_days_ago = datetime.combine(today - timedelta(days=30), datetime.min.time())
        recent_trips_stats = db.query(
            func.sum(Trip.collected_amount).label('total_collections')
        ).filter(Trip.collection_time >= thirty_days_ago).scalar()

        total_recent_collections = float(recent_trips_stats or 0)

        # Calculate average per vehicle
        if total_vehicles_for_avg and total_vehicles_for_avg > 0:
            avg_collection_per_vehicle = total_recent_collections / total_vehicles_for_avg
        else:
            avg_collection_per_vehicle = 0
        
        # 5. Revenue comparison between today and yesterday
        yesterday_start = datetime.combine(yesterday, datetime.min.time())
        yesterday_end = datetime.combine(yesterday, datetime.max.time())

        yesterday_revenue_result = db.query(func.sum(Trip.collected_amount)).filter(
            Trip.collection_time >= yesterday_start,
            Trip.collection_time <= yesterday_end
        ).scalar()

        total_revenue_yesterday = float(yesterday_revenue_result or 0)

        # Calculate percentage change
        if total_revenue_yesterday > 0:
            revenue_comparison = ((total_revenue_today - total_revenue_yesterday) / total_revenue_yesterday) * 100
        else:
            revenue_comparison = 100 if total_revenue_today > 0 else 0
        
        # 6. Calculate vehicle utilization
        # Count unique vehicles that had trips today
        active_vehicles_today_count = db.query(func.count(func.distinct(Trip.vehicle_id))).filter(
            Trip.collection_time >= start_of_day,
            Trip.collection_time <= end_of_day
        ).scalar()

        # Calculate utilization percentage
        if active_vehicles_count > 0:
            vehicle_utilization = (active_vehicles_today_count / active_vehicles_count) * 100
        else:
            vehicle_utilization = 0
        
        # 7. Average collection compared to previous week
        prev_week_start = datetime.combine(week_ago - timedelta(days=7), datetime.min.time())
        prev_week_end = datetime.combine(week_ago, datetime.max.time())

        prev_week_revenue_result = db.query(func.sum(Trip.collected_amount)).filter(
            Trip.collection_time >= prev_week_start,
            Trip.collection_time <= prev_week_end
        ).scalar()

        prev_week_total = float(prev_week_revenue_result or 0)

        if total_vehicles_for_avg and total_vehicles_for_avg > 0:
            prev_week_avg = prev_week_total / total_vehicles_for_avg
            if prev_week_avg > 0:
                avg_collection_comparison = ((avg_collection_per_vehicle - prev_week_avg) / prev_week_avg) * 100
            else:
                avg_collection_comparison = 100 if avg_collection_per_vehicle > 0 else 0
        else:
            avg_collection_comparison = 0
        
        # Return the overview data
        return {
            "total_revenue_today": total_revenue_today,
            "active_vehicles_count": active_vehicles_count,
            "total_vehicles_count": total_vehicles_count,
            "upcoming_renewals": len(renewals),
            "renewals": renewals,
            "avg_collection_per_vehicle": avg_collection_per_vehicle,
            "revenue_comparison": revenue_comparison,
            "vehicle_utilization": vehicle_utilization,
            "avg_collection_comparison": avg_collection_comparison
        }
        
    except Exception as e:
        logger.error(f"Error fetching financial overview: {str(e)}")
        raise e

@router.get("/overview/finances", response_model=DashboardOverview)
async def get_financial_overview_endpoint(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get financial overview for the dashboard cards.
    """
    try:
        return get_financial_overview(db)
    except Exception as e:
        logger.error(f"Error in financial overview endpoint: {str(e)}")
        raise create_dashboard_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve financial overview. Please try again later.",
            error_type="financial_overview_failed",
            details={"error": str(e)}
        )

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    days: int = 30,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get comprehensive dashboard statistics including:
    - Financial overview
    - Top performing vehicles
    - Top performing drivers
    - Revenue, expenses, and profit time series data
    
    Parameters:
    - days: Number of days to include in the statistics (default: 30)
    """
    try:
        # Get date range
        today = date.today()
        start_date = today - timedelta(days=days)
        
        # Get the financial overview first
        overview = get_financial_overview(db)
        
        # Get all trips in the date range
        start_datetime = datetime.combine(start_date, datetime.min.time())
        trips = db.query(Trip).filter(Trip.collection_time >= start_datetime).all()
        
        # Process vehicle performance
        vehicle_metrics: Dict[str, Dict] = {}
        for trip in trips:
            vehicle_id = str(trip.vehicle_id)
            if not vehicle_id:
                continue

            if vehicle_id not in vehicle_metrics:
                vehicle_metrics[vehicle_id] = {
                    "vehicle_id": vehicle_id,
                    "total_collections": 0,
                    "total_expenses": 0,
                    "trip_count": 0
                }

            # Add collections
            collected = float(trip.collected_amount or 0)
            vehicle_metrics[vehicle_id]["total_collections"] += collected

            # Add expenses
            repair_expense = float(trip.repair_expense or 0)
            vehicle_metrics[vehicle_id]["total_expenses"] += repair_expense

            # Count trip
            vehicle_metrics[vehicle_id]["trip_count"] += 1

        # Get vehicle registration numbers
        vehicle_ids = [vid for vid in vehicle_metrics.keys()]
        if vehicle_ids:
            vehicles = db.query(Vehicle).filter(Vehicle.id.in_(vehicle_ids)).all()

            for vehicle in vehicles:
                v_id = str(vehicle.id)
                if v_id in vehicle_metrics:
                    vehicle_metrics[v_id]["registration"] = vehicle.reg_no
        
        # Calculate net profit and prepare top vehicles list
        top_vehicles = []
        for v_id, metrics in vehicle_metrics.items():
            net_profit = metrics["total_collections"] - metrics["total_expenses"]
            metrics["net_profit"] = net_profit
            if "registration" not in metrics:
                metrics["registration"] = "Unknown"
                
            top_vehicles.append(metrics)
        
        # Sort by net profit and get top 5
        top_vehicles.sort(key=lambda x: x["net_profit"], reverse=True)
        top_vehicles = top_vehicles[:5]
        
        # Process driver performance
        driver_metrics: Dict[str, Dict] = {}
        for trip in trips:
            driver_id = str(trip.driver_id)
            if not driver_id:
                continue

            if driver_id not in driver_metrics:
                driver_metrics[driver_id] = {
                    "driver_id": driver_id,
                    "total_collections": 0,
                    "trip_count": 0
                }

            # Add collections
            collected = float(trip.collected_amount or 0)
            driver_metrics[driver_id]["total_collections"] += collected

            # Count trip
            driver_metrics[driver_id]["trip_count"] += 1
        
        # Get driver names
        driver_ids = [did for did in driver_metrics.keys()]
        if driver_ids:
            drivers = db.query(Driver).filter(Driver.id.in_(driver_ids)).all()

            for driver in drivers:
                d_id = str(driver.id)
                if d_id in driver_metrics:
                    driver_metrics[d_id]["name"] = driver.name
        
        # Calculate average per trip and prepare top drivers list
        top_drivers = []
        for d_id, metrics in driver_metrics.items():
            if metrics["trip_count"] > 0:
                metrics["avg_per_trip"] = metrics["total_collections"] / metrics["trip_count"]
            else:
                metrics["avg_per_trip"] = 0
                
            if "name" not in metrics:
                metrics["name"] = "Unknown"
                
            top_drivers.append(metrics)
        
        # Sort by total collections and get top 5
        top_drivers.sort(key=lambda x: x["total_collections"], reverse=True)
        top_drivers = top_drivers[:5]
        
        # Process time series data
        day_metrics: Dict[str, Dict[str, float]] = {}
        for trip in trips:
            # Get the date from collection_time
            collection_time = trip.collection_time
            if not collection_time:
                continue

            # Convert to date
            trip_date = collection_time.date().isoformat()

            if trip_date not in day_metrics:
                day_metrics[trip_date] = {
                    "revenue": 0,
                    "expenses": 0
                }

            # Add revenue
            collected = float(trip.collected_amount or 0)
            day_metrics[trip_date]["revenue"] += collected

            # Add expenses (only repair_expense since fuel_expense doesn't exist in our schema)
            repair_expense = float(trip.repair_expense or 0)
            day_metrics[trip_date]["expenses"] += repair_expense
        
        # Prepare time series data
        revenue_by_day = []
        expenses_by_day = []
        profit_by_day = []
        
        # Sort days
        sorted_days = sorted(day_metrics.keys())
        
        for day in sorted_days:
            metrics = day_metrics[day]
            revenue = metrics["revenue"]
            expenses = metrics["expenses"]
            profit = revenue - expenses
            
            revenue_by_day.append({"label": day, "value": revenue})
            expenses_by_day.append({"label": day, "value": expenses})
            profit_by_day.append({"label": day, "value": profit})
        
        # Return all dashboard stats
        return {
            "overview": overview,
            "top_vehicles": top_vehicles,
            "top_drivers": top_drivers,
            "revenue_by_day": revenue_by_day,
            "expenses_by_day": expenses_by_day,
            "profit_by_day": profit_by_day
        }
        
    except Exception as e:
        logger.error(f"Error fetching dashboard statistics: {str(e)}")
        raise create_dashboard_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve dashboard statistics. Please try again later.",
            error_type="dashboard_stats_failed",
            details={"error": str(e)}
        )

@router.get("/trends/collections", response_model=CollectionTrend)
async def get_collection_trends(
    start_date: Optional[str] = Query(None, description="Start date for trend data (DD-MM-YYYY)"),
    end_date: Optional[str] = Query(None, description="End date for trend data (DD-MM-YYYY)"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get trends of money collections within a specified date range.
    - Defaults to the past 7 days if no dates are provided
    - Date format should be DD-MM-YYYY
    - Shows collection amounts, fuel expenses, and repair expenses
    - Maximum end date is the current date (no future values)
    """
    try:
        # Parse date strings if provided
        parsed_start_date = None
        parsed_end_date = None
        
        # Set default date range to past 7 days if not provided
        today = date.today()
        
        if start_date:
            try:
                # Parse DD-MM-YYYY format
                day, month, year = map(int, start_date.split('-'))
                parsed_start_date = date(year, month, day)
            except (ValueError, TypeError):
                raise create_dashboard_error(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    message="Invalid start_date format. Please use DD-MM-YYYY",
                    error_type="invalid_date_format",
                    details={"field": "start_date", "expected_format": "DD-MM-YYYY"}
                )
        else:
            parsed_start_date = today - timedelta(days=6)  # 7 days including today
            
        if end_date:
            try:
                # Parse DD-MM-YYYY format
                day, month, year = map(int, end_date.split('-'))
                parsed_end_date = date(year, month, day)
                # Ensure end date is not in the future
                if parsed_end_date > today:
                    parsed_end_date = today
            except (ValueError, TypeError):
                raise create_dashboard_error(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    message="Invalid end_date format. Please use DD-MM-YYYY",
                    error_type="invalid_date_format",
                    details={"field": "end_date", "expected_format": "DD-MM-YYYY"}
                )
        else:
            parsed_end_date = today
        
        # Ensure the end date is not in the future
        if parsed_end_date > today:
            parsed_end_date = today
            
        # If start date is in the future, adjust it to today
        if parsed_start_date > today:
            parsed_start_date = today
        
        # Validate date range
        if parsed_end_date < parsed_start_date:
            raise create_dashboard_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="End date must be greater than or equal to start date",
                error_type="invalid_date_range",
                details={
                    "start_date": parsed_start_date.isoformat(),
                    "end_date": parsed_end_date.isoformat()
                }
            )
        
        # Initialize result structure with dates in range
        date_range = []
        current_date = parsed_start_date
        while current_date <= parsed_end_date:
            date_range.append(current_date.isoformat())
            current_date += timedelta(days=1)
        
        # Initialize result data structure
        trend_data = {date_str: {
            "date": date_str,
            "collection_amount": 0,
            "fuel_expense": 0,
            "repair_expense": 0,
            "total_expense": 0
        } for date_str in date_range}
        
        # Get trips in date range
        start_datetime = datetime.combine(parsed_start_date, datetime.min.time())
        end_datetime = datetime.combine(parsed_end_date, datetime.max.time())

        trips = db.query(Trip).filter(
            Trip.collection_time >= start_datetime,
            Trip.collection_time <= end_datetime
        ).all()

        # Process trips data
        for trip in trips:
            # Extract date from collection_time
            trip_date = trip.collection_time.date().isoformat()

            # Skip if date is not in our range
            if trip_date not in trend_data:
                continue

            # Add collection amount
            collected_amount = float(trip.collected_amount or 0)
            trend_data[trip_date]["collection_amount"] += collected_amount

            # Add repair expense (fuel expense doesn't exist in our schema)
            repair_expense = float(trip.repair_expense or 0)
            trend_data[trip_date]["repair_expense"] += repair_expense

            # Calculate total expense (only repair expense in our schema)
            trend_data[trip_date]["total_expense"] = repair_expense
        
        # Convert dict to list for response
        result_data = list(trend_data.values())
        
        # Sort by date
        result_data.sort(key=lambda x: x["date"])
        
        return {
            "start_date": parsed_start_date,
            "end_date": parsed_end_date,
            "trend_data": result_data
        }
        
    except Exception as e:
        logger.error(f"Error fetching collection trends: {str(e)}")
        raise create_dashboard_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve collection trends. Please try again later.",
            error_type="collection_trends_failed",
            details={"error": str(e)}
        )

@router.get("/performance/vehicles", response_model=VehiclePerformanceList)
async def get_vehicle_performance(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get performance metrics for all vehicles.
    
    Returns detailed metrics including:
    - Total collections
    - Trip counts
    - Fuel and repair expenses
    - Profit calculations
    - Efficiency metrics
    """
    try:
        # Parse date strings if provided
        today = date.today()
        
        # Default to last 30 days if no dates provided
        if not start_date:
            parsed_start_date = today - timedelta(days=29)
        else:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
        
        if not end_date:
            parsed_end_date = today
        else:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Ensure dates are valid
        if parsed_end_date < parsed_start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be after start date"
            )
            
        # Get all active vehicles
        vehicles = db.query(Vehicle).filter(Vehicle.status == "active").all()

        if not vehicles:
            return {
                "vehicles": [],
                "total_vehicles": 0,
                "total_collections": 0,
                "total_profit": 0,
                "average_profit_per_vehicle": 0,
                "start_date": parsed_start_date,
                "end_date": parsed_end_date
            }

        # Get all trips in date range for these vehicles
        start_datetime = datetime.combine(parsed_start_date, datetime.min.time())
        end_datetime = datetime.combine(parsed_end_date, datetime.max.time())
        trips = db.query(Trip).filter(
            Trip.collection_time >= start_datetime,
            Trip.collection_time <= end_datetime
        ).all()
        
        # Process data for each vehicle
        vehicle_metrics = {}
        date_range = (parsed_end_date - parsed_start_date).days + 1
        
        # Initialize vehicle metrics
        for vehicle in vehicles:
            vehicle_id = str(vehicle.id)
            vehicle_metrics[vehicle_id] = {
                "vehicle_id": vehicle_id,
                "registration": vehicle.reg_no or "Unknown",
                "total_collections": 0,
                "total_expenses": 0,
                "fuel_expense": 0,
                "repair_expense": 0,
                "net_profit": 0,
                "trip_count": 0,
                "active_days": set(),  # To calculate utilization
                "collections_by_date": {},  # For time series data
                "expenses_by_date": {},  # For time series data
            }
        
        # Process trip data
        for trip in trips:
            vehicle_id = str(trip.vehicle_id) if trip.vehicle_id else None
            if not vehicle_id or vehicle_id not in vehicle_metrics:
                continue

            # Extract values
            collected_amount = float(trip.collected_amount or 0)
            fuel_expense = float(trip.fuel_expense or 0) if hasattr(trip, 'fuel_expense') else 0
            repair_expense = float(trip.repair_expense or 0)
            total_expense = fuel_expense + repair_expense

            # Get trip date
            if trip.collection_time:
                trip_date_str = trip.collection_time.date().isoformat()
                vehicle_metrics[vehicle_id]["active_days"].add(trip_date_str)

                # Add to daily collections/expenses
                if trip_date_str not in vehicle_metrics[vehicle_id]["collections_by_date"]:
                    vehicle_metrics[vehicle_id]["collections_by_date"][trip_date_str] = 0
                    vehicle_metrics[vehicle_id]["expenses_by_date"][trip_date_str] = 0

                vehicle_metrics[vehicle_id]["collections_by_date"][trip_date_str] += collected_amount
                vehicle_metrics[vehicle_id]["expenses_by_date"][trip_date_str] += total_expense

            # Update aggregates
            vehicle_metrics[vehicle_id]["total_collections"] += collected_amount
            vehicle_metrics[vehicle_id]["fuel_expense"] += fuel_expense
            vehicle_metrics[vehicle_id]["repair_expense"] += repair_expense
            vehicle_metrics[vehicle_id]["total_expenses"] += total_expense
            vehicle_metrics[vehicle_id]["trip_count"] += 1
        
        # Calculate derived metrics
        vehicles_list = []
        total_collections = 0
        total_profit = 0
        
        for vehicle_id, metrics in vehicle_metrics.items():
            # Calculate net profit
            metrics["net_profit"] = metrics["total_collections"] - metrics["total_expenses"]
            
            # Calculate profit per trip (if trips > 0)
            metrics["profit_per_trip"] = (metrics["net_profit"] / metrics["trip_count"]) if metrics["trip_count"] > 0 else 0
            
            # Calculate collection per trip
            metrics["collection_per_trip"] = (metrics["total_collections"] / metrics["trip_count"]) if metrics["trip_count"] > 0 else 0
            
            # Calculate expense ratio (expenses as % of collections)
            metrics["expense_ratio"] = (metrics["total_expenses"] / metrics["total_collections"] * 100) if metrics["total_collections"] > 0 else 0
            
            # Calculate utilization rate
            metrics["utilization_rate"] = (len(metrics["active_days"]) / date_range * 100) if date_range > 0 else 0
            
            # Clean up and remove temporary fields
            del metrics["active_days"]
            del metrics["collections_by_date"]
            del metrics["expenses_by_date"]
            
            # Add to running totals
            total_collections += metrics["total_collections"]
            total_profit += metrics["net_profit"]
            
            # Add to list
            vehicles_list.append(metrics)
        
        # Sort by net profit
        vehicles_list.sort(key=lambda x: x["net_profit"], reverse=True)
        
        # Calculate average profit per vehicle
        avg_profit_per_vehicle = total_profit / len(vehicles_list) if vehicles_list else 0
        
        return {
            "vehicles": vehicles_list,
            "total_vehicles": len(vehicles_list),
            "total_collections": total_collections,
            "total_profit": total_profit,
            "average_profit_per_vehicle": avg_profit_per_vehicle,
            "start_date": parsed_start_date,
            "end_date": parsed_end_date
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching vehicle performance: {str(e)}"
        )

@router.get("/performance/vehicles/{vehicle_id}", response_model=DetailedVehiclePerformance)
async def get_vehicle_detail_performance(
    vehicle_id: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get detailed performance metrics for a specific vehicle including daily breakdowns.
    """
    try:
        # Parse date strings if provided
        today = date.today()
        
        # Default to last 30 days if no dates provided
        if not start_date:
            parsed_start_date = today - timedelta(days=29)
        else:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
        
        if not end_date:
            parsed_end_date = today
        else:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Check if vehicle exists
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()

        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )

        # Get all trips for this vehicle in date range
        start_datetime = datetime.combine(parsed_start_date, datetime.min.time())
        end_datetime = datetime.combine(parsed_end_date, datetime.max.time())
        trips = db.query(Trip).filter(
            Trip.vehicle_id == vehicle_id,
            Trip.collection_time >= start_datetime,
            Trip.collection_time <= end_datetime
        ).all()
        
        # Initialize performance metrics
        vehicle_detail = {
            "vehicle_id": vehicle_id,
            "registration": vehicle.reg_no or "Unknown",
            "total_collections": 0,
            "total_expenses": 0,
            "fuel_expense": 0,
            "repair_expense": 0,
            "net_profit": 0,
            "trip_count": 0,
            "collections_by_day": [],
            "expenses_by_day": [],
            "profit_by_day": [],
            "trips_by_day": []
        }
        
        # Process trip data and organize by day
        daily_data = {}
        date_range = (parsed_end_date - parsed_start_date).days + 1
        active_days = set()

        for trip in trips:
            # Extract values
            collected_amount = float(trip.collected_amount or 0)
            fuel_expense = float(trip.fuel_expense or 0) if hasattr(trip, 'fuel_expense') else 0
            repair_expense = float(trip.repair_expense or 0)
            total_expense = fuel_expense + repair_expense

            # Get trip date
            if trip.collection_time:
                trip_date = trip.collection_time.date()
                trip_date_str = trip_date.isoformat()
                active_days.add(trip_date_str)

                # Initialize daily data if needed
                if trip_date_str not in daily_data:
                    daily_data[trip_date_str] = {
                        "collection": 0,
                        "fuel_expense": 0,
                        "repair_expense": 0,
                        "total_expense": 0,
                        "trip_count": 0
                    }

                # Add to daily data
                daily_data[trip_date_str]["collection"] += collected_amount
                daily_data[trip_date_str]["fuel_expense"] += fuel_expense
                daily_data[trip_date_str]["repair_expense"] += repair_expense
                daily_data[trip_date_str]["total_expense"] += total_expense
                daily_data[trip_date_str]["trip_count"] += 1

            # Update aggregates
            vehicle_detail["total_collections"] += collected_amount
            vehicle_detail["fuel_expense"] += fuel_expense
            vehicle_detail["repair_expense"] += repair_expense
            vehicle_detail["total_expenses"] += (fuel_expense + repair_expense)
            vehicle_detail["trip_count"] += 1
        
        # Calculate net profit
        vehicle_detail["net_profit"] = vehicle_detail["total_collections"] - vehicle_detail["total_expenses"]
        
        # Calculate derived metrics
        if vehicle_detail["trip_count"] > 0:
            vehicle_detail["profit_per_trip"] = vehicle_detail["net_profit"] / vehicle_detail["trip_count"]
            vehicle_detail["collection_per_trip"] = vehicle_detail["total_collections"] / vehicle_detail["trip_count"]
        
        if vehicle_detail["total_collections"] > 0:
            vehicle_detail["expense_ratio"] = (vehicle_detail["total_expenses"] / vehicle_detail["total_collections"]) * 100
        
        vehicle_detail["utilization_rate"] = (len(active_days) / date_range) * 100 if date_range > 0 else 0
        
        # Prepare time series data
        # Sort dates
        dates = sorted(daily_data.keys())
        
        for date_str in dates:
            day_data = daily_data[date_str]
            profit = day_data["collection"] - day_data["total_expense"]
            
            vehicle_detail["collections_by_day"].append({
                "label": date_str,
                "value": day_data["collection"]
            })
            
            vehicle_detail["expenses_by_day"].append({
                "label": date_str,
                "value": day_data["total_expense"]
            })
            
            vehicle_detail["profit_by_day"].append({
                "label": date_str,
                "value": profit
            })
            
            vehicle_detail["trips_by_day"].append({
                "label": date_str,
                "value": day_data["trip_count"]
            })
        
        return vehicle_detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching detailed vehicle performance: {str(e)}"
        )

@router.get("/performance/drivers", response_model=DriverPerformanceList)
async def get_driver_performance(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get performance metrics for all drivers.
    
    Returns detailed metrics including:
    - Total collections
    - Trip counts
    - Average collections per trip
    - Collection efficiency
    - Vehicles driven
    """
    try:
        # Parse date strings if provided
        today = date.today()
        
        # Default to last 30 days if no dates provided
        if not start_date:
            parsed_start_date = today - timedelta(days=29)
        else:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
        
        if not end_date:
            parsed_end_date = today
        else:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Ensure dates are valid
        if parsed_end_date < parsed_start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be after start date"
            )
            
        # Get all active drivers
        drivers = db.query(Driver).all()

        if not drivers:
            return {
                "drivers": [],
                "total_drivers": 0,
                "total_collections": 0,
                "average_collections_per_driver": 0,
                "start_date": parsed_start_date,
                "end_date": parsed_end_date
            }

        # Get all trips in date range
        start_datetime = datetime.combine(parsed_start_date, datetime.min.time())
        end_datetime = datetime.combine(parsed_end_date, datetime.max.time())
        trips = db.query(Trip).filter(
            Trip.collection_time >= start_datetime,
            Trip.collection_time <= end_datetime
        ).all()
        
        # Process data for each driver
        driver_metrics = {}
        
        # Initialize driver metrics
        for driver in drivers:
            driver_id = str(driver.id)
            driver_metrics[driver_id] = {
                "driver_id": driver_id,
                "name": driver.name or "Unknown",
                "total_collections": 0,
                "trip_count": 0,
                "total_expected": 0,  # For calculating efficiency
                "vehicles": set(),    # Set of vehicles driven
                "vehicle_trips": {}   # Count trips per vehicle to find most driven
            }
        
        # Get vehicle registrations for reference
        vehicle_ids = set()
        for trip in trips:
            if trip.vehicle_id:
                vehicle_ids.add(str(trip.vehicle_id))

        vehicle_reg_map = {}
        if vehicle_ids:
            vehicles = db.query(Vehicle).filter(Vehicle.id.in_(list(vehicle_ids))).all()
            for vehicle in vehicles:
                vehicle_reg_map[str(vehicle.id)] = vehicle.reg_no or "Unknown"
        
        # Process trip data
        for trip in trips:
            driver_id = str(trip.driver_id) if trip.driver_id else None
            if not driver_id or driver_id not in driver_metrics:
                continue

            # Extract values
            collected_amount = float(trip.collected_amount or 0)
            expected_amount = float(trip.expected_amount or 0) if hasattr(trip, 'expected_amount') else 0
            vehicle_id = str(trip.vehicle_id) if trip.vehicle_id else None

            # Update aggregates
            driver_metrics[driver_id]["total_collections"] += collected_amount
            driver_metrics[driver_id]["total_expected"] += expected_amount
            driver_metrics[driver_id]["trip_count"] += 1

            # Track vehicles driven
            if vehicle_id:
                driver_metrics[driver_id]["vehicles"].add(vehicle_id)

                # Count trips per vehicle
                if vehicle_id not in driver_metrics[driver_id]["vehicle_trips"]:
                    driver_metrics[driver_id]["vehicle_trips"][vehicle_id] = 0
                driver_metrics[driver_id]["vehicle_trips"][vehicle_id] += 1
        
        # Calculate derived metrics
        drivers_list = []
        total_collections = 0
        
        for driver_id, metrics in driver_metrics.items():
            # Calculate average per trip
            metrics["avg_per_trip"] = metrics["total_collections"] / metrics["trip_count"] if metrics["trip_count"] > 0 else 0
            
            # Calculate collection efficiency
            metrics["collection_efficiency"] = (metrics["total_collections"] / metrics["total_expected"] * 100) if metrics["total_expected"] > 0 else 0
            
            # Set total vehicles driven
            metrics["total_vehicles_driven"] = len(metrics["vehicles"])
            
            # Find most driven vehicle
            if metrics["vehicle_trips"]:
                most_driven_id = max(metrics["vehicle_trips"].items(), key=lambda x: x[1])[0]
                metrics["most_driven_vehicle"] = vehicle_reg_map.get(most_driven_id, "Unknown")
            
            # Clean up temporary fields
            del metrics["vehicles"]
            del metrics["vehicle_trips"]
            del metrics["total_expected"]
            
            # Add to total collections
            total_collections += metrics["total_collections"]
            
            # Add to list
            drivers_list.append(metrics)
        
        # Sort by total collections
        drivers_list.sort(key=lambda x: x["total_collections"], reverse=True)
        
        # Calculate average collections per driver
        avg_collections_per_driver = total_collections / len(drivers_list) if drivers_list else 0
        
        return {
            "drivers": drivers_list,
            "total_drivers": len(drivers_list),
            "total_collections": total_collections,
            "average_collections_per_driver": avg_collections_per_driver,
            "start_date": parsed_start_date,
            "end_date": parsed_end_date
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching driver performance: {str(e)}"
        )

@router.get("/performance/drivers/{driver_id}", response_model=DetailedDriverPerformance)
async def get_driver_detail_performance(
    driver_id: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get detailed performance metrics for a specific driver including daily breakdowns.
    """
    try:
        # Parse date strings if provided
        today = date.today()
        
        # Default to last 30 days if no dates provided
        if not start_date:
            parsed_start_date = today - timedelta(days=29)
        else:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
        
        if not end_date:
            parsed_end_date = today
        else:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Check if driver exists
        driver = db.query(Driver).filter(Driver.id == driver_id).first()

        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found"
            )

        # Get all trips for this driver in date range
        start_datetime = datetime.combine(parsed_start_date, datetime.min.time())
        end_datetime = datetime.combine(parsed_end_date, datetime.max.time())
        trips = db.query(Trip).filter(
            Trip.driver_id == driver_id,
            Trip.collection_time >= start_datetime,
            Trip.collection_time <= end_datetime
        ).all()
        
        # Initialize performance metrics
        driver_detail = {
            "driver_id": driver_id,
            "name": driver.name or "Unknown",
            "total_collections": 0,
            "trip_count": 0,
            "avg_per_trip": 0,
            "collection_efficiency": 0,
            "total_vehicles_driven": 0,
            "most_driven_vehicle": None,
            "collections_by_day": [],
            "trips_by_day": [],
            "vehicles_driven": []
        }
        
        # Process trip data and organize by day
        daily_data = {}
        vehicle_data = {}
        total_expected = 0
        vehicles_driven = set()
        vehicle_trips = {}

        for trip in trips:
            # Extract values
            collected_amount = float(trip.collected_amount or 0)
            expected_amount = float(trip.expected_amount or 0) if hasattr(trip, 'expected_amount') else 0
            vehicle_id = str(trip.vehicle_id) if trip.vehicle_id else None

            # Get trip date
            if trip.collection_time:
                trip_date = trip.collection_time.date()
                trip_date_str = trip_date.isoformat()

                # Initialize daily data if needed
                if trip_date_str not in daily_data:
                    daily_data[trip_date_str] = {
                        "collection": 0,
                        "trip_count": 0
                    }

                # Add to daily data
                daily_data[trip_date_str]["collection"] += collected_amount
                daily_data[trip_date_str]["trip_count"] += 1

            # Track vehicle usage
            if vehicle_id:
                vehicles_driven.add(vehicle_id)

                # Count trips per vehicle
                if vehicle_id not in vehicle_trips:
                    vehicle_trips[vehicle_id] = 0
                vehicle_trips[vehicle_id] += 1

                # Collect data per vehicle
                if vehicle_id not in vehicle_data:
                    vehicle_data[vehicle_id] = {
                        "vehicle_id": vehicle_id,
                        "registration": "Unknown",  # Will be filled later
                        "trip_count": 0,
                        "total_collections": 0
                    }

                vehicle_data[vehicle_id]["trip_count"] += 1
                vehicle_data[vehicle_id]["total_collections"] += collected_amount

            # Update aggregates
            driver_detail["total_collections"] += collected_amount
            driver_detail["trip_count"] += 1
            total_expected += expected_amount
        
        # Get vehicle registrations
        if vehicles_driven:
            vehicles = db.query(Vehicle).filter(Vehicle.id.in_(list(vehicles_driven))).all()
            for vehicle in vehicles:
                vehicle_id_str = str(vehicle.id)
                if vehicle_id_str in vehicle_data:
                    vehicle_data[vehicle_id_str]["registration"] = vehicle.reg_no or "Unknown"
        
        # Find most driven vehicle
        most_driven_vehicle = None
        most_trips = 0
        for v_id, trips in vehicle_trips.items():
            if trips > most_trips:
                most_trips = trips
                most_driven_vehicle = v_id
        
        if most_driven_vehicle and most_driven_vehicle in vehicle_data:
            driver_detail["most_driven_vehicle"] = vehicle_data[most_driven_vehicle]["registration"]
        
        # Calculate derived metrics
        if driver_detail["trip_count"] > 0:
            driver_detail["avg_per_trip"] = driver_detail["total_collections"] / driver_detail["trip_count"]
        
        if total_expected > 0:
            driver_detail["collection_efficiency"] = (driver_detail["total_collections"] / total_expected) * 100
        
        driver_detail["total_vehicles_driven"] = len(vehicles_driven)
        
        # Prepare time series data
        # Sort dates
        dates = sorted(daily_data.keys())
        
        for date_str in dates:
            day_data = daily_data[date_str]
            
            driver_detail["collections_by_day"].append({
                "label": date_str,
                "value": day_data["collection"]
            })
            
            driver_detail["trips_by_day"].append({
                "label": date_str,
                "value": day_data["trip_count"]
            })
        
        # Prepare vehicles driven data
        for v_id, v_data in vehicle_data.items():
            driver_detail["vehicles_driven"].append(v_data)
        
        # Sort vehicles by trip count
        driver_detail["vehicles_driven"].sort(key=lambda x: x["trip_count"], reverse=True)
        
        return driver_detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching detailed driver performance: {str(e)}"
        )

@router.get("/performance/summary", response_model=PerformanceSummary)
async def get_performance_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    vehicle_ids: Optional[List[str]] = Query(None, description="List of vehicle IDs to filter by"),
    driver_ids: Optional[List[str]] = Query(None, description="List of driver IDs to filter by"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get a summary of performance metrics across specified vehicles and drivers.
    
    Accepts date range and optional filters for specific vehicles and drivers.
    Returns aggregated collections, expenses, and net revenue.
    
    Default date range is the last 7 days if not specified.
    """
    try:
        # Parse date strings if provided
        today = date.today()
        
        # Default to last 7 days if no dates provided
        if not start_date:
            parsed_start_date = today - timedelta(days=6)  # Last 7 days including today
        else:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
        
        if not end_date:
            parsed_end_date = today
        else:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Ensure dates are valid
        if parsed_end_date < parsed_start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be after start date"
            )
        
        start_datetime = datetime.combine(parsed_start_date, time.min)
        end_datetime = datetime.combine(parsed_end_date, time.max)


        # Build the query with date range filter
        query = db.query(Trip).filter(
            Trip.collection_time >= start_datetime,
            Trip.collection_time <= end_datetime
        )

        # Add vehicle filter if provided
        if vehicle_ids and len(vehicle_ids) > 0:
            query = query.filter(Trip.vehicle_id.in_(vehicle_ids))

        # Add driver filter if provided
        if driver_ids and len(driver_ids) > 0:
            query = query.filter(Trip.driver_id.in_(driver_ids))

        # Execute the query
        trips = query.all()
        
        # Initialize counters
        total_collections = 0.0
        total_fuel_expense = 0.0
        total_repair_expense = 0.0
        trip_count = 0
        
        # Process trip data
        for trip in trips:
            # Extract values with safety checks
            collected_amount = float(trip.collected_amount or 0)
            fuel_expense = float(trip.fuel_expense or 0) if hasattr(trip, 'fuel_expense') else 0
            repair_expense = float(trip.repair_expense or 0)

            # Update totals
            total_collections += collected_amount
            total_fuel_expense += fuel_expense
            total_repair_expense += repair_expense
            trip_count += 1
        
        # Calculate total expenses and net revenue
        total_expenses = total_fuel_expense + total_repair_expense
        net_revenue = total_collections - total_expenses
        
        # Return the summary
        return {
            "total_collections": total_collections,
            "total_expenses": total_expenses,
            "fuel_expense": total_fuel_expense,
            "repair_expense": total_repair_expense,
            "net_revenue": net_revenue,
            "trip_count": trip_count,
            "start_date": parsed_start_date,
            "end_date": parsed_end_date,
            "vehicle_ids": vehicle_ids,
            "driver_ids": driver_ids
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching performance summary: {str(e)}"
        ) 