from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Any, Dict, List, Optional
from datetime import datetime, date, time, timedelta

from app.core.db import supabase
from app.core.security import get_current_active_user
from app.schemas.dashboard import DashboardOverview, DashboardStats, VehiclePerformance, DriverPerformance, TimeSeriesData, CollectionTrend, DetailedVehiclePerformance, VehiclePerformanceList, DetailedDriverPerformance, DriverPerformanceList, PerformanceSummary

router = APIRouter()

@router.get("/overview/finances", response_model=DashboardOverview)
async def get_financial_overview(current_user = Depends(get_current_active_user)) -> Any:
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
        today_trips = supabase.table("trips").select("collected_amount").gte("collection_time", f"{today_str}T00:00:00").lt("collection_time", f"{today_str}T23:59:59").execute()
        
        # Calculate total revenue from today's trips
        total_revenue_today = 0
        for trip in today_trips.data:
            total_revenue_today += float(trip.get("collected_amount", 0) or 0)
        
        # 2. Count Active Vehicles
        active_vehicles_response = supabase.table("vehicles").select("id").eq("status", "active").execute()
        active_vehicles_count = len(active_vehicles_response.data)
        
        # 2.1 Count Total Vehicles (all vehicles regardless of status)
        total_vehicles_response = supabase.table("vehicles").select("id").execute()
        total_vehicles_count = len(total_vehicles_response.data)
        
        # 3. Upcoming Renewals - Static value as requested
        upcoming_renewals = 5  # Static value as per requirements
        
        # 4. Average Collection Per Vehicle
        # First, get all active vehicles
        all_vehicles = supabase.table("vehicles").select("id").execute()
        
        # Then, get all trips from the last 30 days to calculate average
        thirty_days_ago = (today - timedelta(days=30)).isoformat()
        recent_trips = supabase.table("trips").select("vehicle_id,collected_amount").gte("collection_time", f"{thirty_days_ago}T00:00:00").execute()
        
        # Calculate total collections per vehicle
        vehicle_collections = {}
        for trip in recent_trips.data:
            vehicle_id = trip.get("vehicle_id")
            if vehicle_id:
                if vehicle_id not in vehicle_collections:
                    vehicle_collections[vehicle_id] = 0
                vehicle_collections[vehicle_id] += float(trip.get("collected_amount", 0) or 0)
        
        # Calculate average
        if all_vehicles.data and len(all_vehicles.data) > 0:
            total_collections = sum(vehicle_collections.values())
            avg_collection_per_vehicle = total_collections / len(all_vehicles.data)
        else:
            avg_collection_per_vehicle = 0
        
        # 5. Revenue comparison between today and yesterday
        yesterday_trips = supabase.table("trips").select("collected_amount").gte("collection_time", f"{yesterday_str}T00:00:00").lt("collection_time", f"{yesterday_str}T23:59:59").execute()
        
        # Calculate yesterday's revenue
        total_revenue_yesterday = 0
        for trip in yesterday_trips.data:
            total_revenue_yesterday += float(trip.get("collected_amount", 0) or 0)
        
        # Calculate percentage change
        if total_revenue_yesterday > 0:
            revenue_comparison = ((total_revenue_today - total_revenue_yesterday) / total_revenue_yesterday) * 100
        else:
            revenue_comparison = 100 if total_revenue_today > 0 else 0
        
        # 6. Calculate vehicle utilization
        # Get all trips that were active today by looking at collection_time and status
        all_active_trips_today = supabase.table("trips").select("vehicle_id").gte("collection_time", f"{today_str}T00:00:00").lt("collection_time", f"{today_str}T23:59:59").execute()
        
        # Count unique vehicles that had trips today
        active_vehicles_today = set()
        for trip in all_active_trips_today.data:
            if trip.get("vehicle_id"):
                active_vehicles_today.add(trip.get("vehicle_id"))
        
        # Calculate utilization percentage
        if active_vehicles_count > 0:
            vehicle_utilization = (len(active_vehicles_today) / active_vehicles_count) * 100
        else:
            vehicle_utilization = 0
        
        # 7. Average collection compared to previous week
        prev_week_start = week_ago - timedelta(days=7)
        prev_week_trips = supabase.table("trips").select("vehicle_id,collected_amount").gte("collection_time", f"{prev_week_start.isoformat()}T00:00:00").lt("collection_time", f"{week_ago.isoformat()}T00:00:00").execute()
        
        # Calculate previous week's average
        prev_week_collections = {}
        for trip in prev_week_trips.data:
            vehicle_id = trip.get("vehicle_id")
            if vehicle_id:
                if vehicle_id not in prev_week_collections:
                    prev_week_collections[vehicle_id] = 0
                prev_week_collections[vehicle_id] += float(trip.get("collected_amount", 0) or 0)
        
        if prev_week_collections and len(all_vehicles.data) > 0:
            prev_week_avg = sum(prev_week_collections.values()) / len(all_vehicles.data)
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
            "upcoming_renewals": upcoming_renewals,
            "avg_collection_per_vehicle": avg_collection_per_vehicle,
            "revenue_comparison": revenue_comparison,
            "vehicle_utilization": vehicle_utilization,
            "avg_collection_comparison": avg_collection_comparison
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching financial overview: {str(e)}"
        )

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    days: int = 30,
    current_user = Depends(get_current_active_user)
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
        overview = await get_financial_overview(current_user)
        
        # Get all trips in the date range
        trips_response = supabase.table("trips").select("*").gte("collection_time", start_date.isoformat()).execute()
        trips = trips_response.data
        
        # Process vehicle performance
        vehicle_metrics: Dict[str, Dict] = {}
        for trip in trips:
            vehicle_id = trip.get("vehicle_id")
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
            collected = float(trip.get("collected_amount", 0) or 0)
            vehicle_metrics[vehicle_id]["total_collections"] += collected
            
            # Add expenses
            fuel_expense = float(trip.get("fuel_expense", 0) or 0)
            repair_expense = float(trip.get("repair_expense", 0) or 0)
            vehicle_metrics[vehicle_id]["total_expenses"] += (fuel_expense + repair_expense)
            
            # Count trip
            vehicle_metrics[vehicle_id]["trip_count"] += 1
        
        # Get vehicle registration numbers
        vehicle_ids = list(vehicle_metrics.keys())
        if vehicle_ids:
            vehicles_response = supabase.table("vehicles").select("id,registration").in_("id", vehicle_ids).execute()
            
            for vehicle in vehicles_response.data:
                v_id = vehicle.get("id")
                if v_id in vehicle_metrics:
                    vehicle_metrics[v_id]["registration"] = vehicle.get("registration", "Unknown")
        
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
            driver_id = trip.get("driver_id")
            if not driver_id:
                continue
                
            if driver_id not in driver_metrics:
                driver_metrics[driver_id] = {
                    "driver_id": driver_id,
                    "total_collections": 0,
                    "trip_count": 0
                }
            
            # Add collections
            collected = float(trip.get("collected_amount", 0) or 0)
            driver_metrics[driver_id]["total_collections"] += collected
            
            # Count trip
            driver_metrics[driver_id]["trip_count"] += 1
        
        # Get driver names
        driver_ids = list(driver_metrics.keys())
        if driver_ids:
            drivers_response = supabase.table("drivers").select("id,name").in_("id", driver_ids).execute()
            
            for driver in drivers_response.data:
                d_id = driver.get("id")
                if d_id in driver_metrics:
                    driver_metrics[d_id]["name"] = driver.get("name", "Unknown")
        
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
            # Get the date from start_time
            start_time = trip.get("collection_time")
            if not start_time:
                continue
                
            # Convert to date
            if isinstance(start_time, str):
                trip_date = datetime.fromisoformat(start_time.replace('Z', '+00:00')).date().isoformat()
            else:
                trip_date = start_time.date().isoformat()
                
            if trip_date not in day_metrics:
                day_metrics[trip_date] = {
                    "revenue": 0,
                    "expenses": 0
                }
            
            # Add revenue
            collected = float(trip.get("collected_amount", 0) or 0)
            day_metrics[trip_date]["revenue"] += collected
            
            # Add expenses
            fuel_expense = float(trip.get("fuel_expense", 0) or 0)
            repair_expense = float(trip.get("repair_expense", 0) or 0)
            day_metrics[trip_date]["expenses"] += (fuel_expense + repair_expense)
        
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching dashboard statistics: {str(e)}"
        )

@router.get("/trends/collections", response_model=CollectionTrend)
async def get_collection_trends(
    start_date: Optional[str] = Query(None, description="Start date for trend data (DD-MM-YYYY)"),
    end_date: Optional[str] = Query(None, description="End date for trend data (DD-MM-YYYY)"),
    current_user = Depends(get_current_active_user)
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
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Please use DD-MM-YYYY"
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
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Please use DD-MM-YYYY"
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="End date must be greater than or equal to start date"
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
        trips_response = supabase.table("trips").select("*").gte("collection_time", f"{parsed_start_date.isoformat()}T00:00:00").lte("collection_time", f"{parsed_end_date.isoformat()}T23:59:59").execute()
        
        # Process trips data
        for trip in trips_response.data:
            # Extract date from start_time
            if isinstance(trip.get("collection_time"), str):
                trip_date = datetime.fromisoformat(trip.get("collection_time").replace('Z', '+00:00')).date().isoformat()
            else:
                trip_date = trip.get("collection_time").date().isoformat()
            
            # Skip if date is not in our range
            if trip_date not in trend_data:
                continue
            
            # Add collection amount
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            trend_data[trip_date]["collection_amount"] += collected_amount
            
            # Add fuel expense
            fuel_expense = float(trip.get("fuel_cost", 0) or 0)
            trend_data[trip_date]["fuel_expense"] += fuel_expense
            
            # Add repair expense (using other_expenses as repair expense)
            repair_expense = float(trip.get("other_expenses", 0) or 0)
            trend_data[trip_date]["repair_expense"] += repair_expense
            
            # Calculate total expense
            trend_data[trip_date]["total_expense"] = trend_data[trip_date]["fuel_expense"] + trend_data[trip_date]["repair_expense"]
        
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching collection trends: {str(e)}"
        )

@router.get("/performance/vehicles", response_model=VehiclePerformanceList)
async def get_vehicle_performance(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user = Depends(get_current_active_user)
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
        vehicles_response = supabase.table("vehicles").select("id,reg_no").execute()
        
        if not vehicles_response.data:
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
        trips_response = supabase.table("trips").select("*").gte("collection_time", parsed_start_date.isoformat()).lte("collection_time", parsed_end_date.isoformat()).execute()
        
        # Process data for each vehicle
        vehicle_metrics = {}
        date_range = (parsed_end_date - parsed_start_date).days + 1
        
        # Initialize vehicle metrics
        for vehicle in vehicles_response.data:
            vehicle_id = vehicle["id"]
            vehicle_metrics[vehicle_id] = {
                "vehicle_id": vehicle_id,
                "registration": vehicle.get("reg_no", "Unknown"),
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
        for trip in trips_response.data:
            vehicle_id = trip.get("vehicle_id")
            if not vehicle_id or vehicle_id not in vehicle_metrics:
                continue
            
            # Extract values
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            fuel_expense = float(trip.get("fuel_expense", 0) or 0)
            repair_expense = float(trip.get("repair_expense", 0) or 0)
            total_expense = fuel_expense + repair_expense
            
            # Get trip date
            if "collection_time" in trip and trip["collection_time"]:
                trip_date_str = datetime.fromisoformat(trip["collection_time"].replace('Z', '+00:00')).date().isoformat()
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
    current_user = Depends(get_current_active_user)
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
        vehicle_response = supabase.table("vehicles").select("id,reg_no").eq("id", vehicle_id).execute()
        
        if not vehicle_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
        
        # Get all trips for this vehicle in date range
        trips_response = supabase.table("trips").select("*").eq("vehicle_id", vehicle_id).gte("collection_time", parsed_start_date.isoformat()).lte("collection_time", parsed_end_date.isoformat()).execute()
        
        # Initialize performance metrics
        vehicle_detail = {
            "vehicle_id": vehicle_id,
            "registration": vehicle_response.data[0].get("reg_no", "Unknown"),
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
        
        for trip in trips_response.data:
            # Extract values
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            fuel_expense = float(trip.get("fuel_expense", 0) or 0)
            repair_expense = float(trip.get("repair_expense", 0) or 0)
            total_expense = fuel_expense + repair_expense
            
            # Get trip date
            if "collection_time" in trip and trip["collection_time"]:
                trip_date = datetime.fromisoformat(trip["collection_time"].replace('Z', '+00:00')).date()
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
    current_user = Depends(get_current_active_user)
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
        drivers_response = supabase.table("drivers").select("id,name").execute()
        
        if not drivers_response.data:
            return {
                "drivers": [],
                "total_drivers": 0,
                "total_collections": 0,
                "average_collections_per_driver": 0,
                "start_date": parsed_start_date,
                "end_date": parsed_end_date
            }
        
        # Get all trips in date range
        trips_response = supabase.table("trips").select("*").gte("collection_time", parsed_start_date.isoformat()).lte("collection_time", parsed_end_date.isoformat()).execute()
        
        # Process data for each driver
        driver_metrics = {}
        
        # Initialize driver metrics
        for driver in drivers_response.data:
            driver_id = driver["id"]
            driver_metrics[driver_id] = {
                "driver_id": driver_id,
                "name": driver.get("name", "Unknown"),
                "total_collections": 0,
                "trip_count": 0,
                "total_expected": 0,  # For calculating efficiency
                "vehicles": set(),    # Set of vehicles driven
                "vehicle_trips": {}   # Count trips per vehicle to find most driven
            }
        
        # Get vehicle registrations for reference
        vehicle_ids = set()
        for trip in trips_response.data:
            if trip.get("vehicle_id"):
                vehicle_ids.add(trip["vehicle_id"])
        
        vehicle_reg_map = {}
        if vehicle_ids:
            vehicles_response = supabase.table("vehicles").select("id,reg_no").in_("id", list(vehicle_ids)).execute()
            for vehicle in vehicles_response.data:
                vehicle_reg_map[vehicle["id"]] = vehicle.get("reg_no", "Unknown")
        
        # Process trip data
        for trip in trips_response.data:
            driver_id = trip.get("driver_id")
            if not driver_id or driver_id not in driver_metrics:
                continue
            
            # Extract values
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            expected_amount = float(trip.get("expected_amount", 0) or 0)
            vehicle_id = trip.get("vehicle_id")
            
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
    current_user = Depends(get_current_active_user)
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
        driver_response = supabase.table("drivers").select("id,name").eq("id", driver_id).execute()
        
        if not driver_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found"
            )
        
        # Get all trips for this driver in date range
        trips_response = supabase.table("trips").select("*").eq("driver_id", driver_id).gte("collection_time", parsed_start_date.isoformat()).lte("collection_time", parsed_end_date.isoformat()).execute()
        
        # Initialize performance metrics
        driver_detail = {
            "driver_id": driver_id,
            "name": driver_response.data[0].get("name", "Unknown"),
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
        
        for trip in trips_response.data:
            # Extract values
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            expected_amount = float(trip.get("expected_amount", 0) or 0)
            vehicle_id = trip.get("vehicle_id")
            
            # Get trip date
            if "collection_time" in trip and trip["collection_time"]:
                trip_date = datetime.fromisoformat(trip["collection_time"].replace('Z', '+00:00')).date()
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
            vehicles_response = supabase.table("vehicles").select("id,reg_no").in_("id", list(vehicles_driven)).execute()
            for vehicle in vehicles_response.data:
                if vehicle["id"] in vehicle_data:
                    vehicle_data[vehicle["id"]]["registration"] = vehicle.get("reg_no", "Unknown")
        
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
    current_user = Depends(get_current_active_user)
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
        
        start_datetime = datetime.combine(parsed_start_date, time.min).isoformat()  # 00:00:00
        end_datetime = datetime.combine(parsed_end_date, time.max).isoformat()  # 23:59:59.999999

        
        # Build the query with date range filter
        query = supabase.table("trips").select("*").gte("collection_time", start_datetime).lte("collection_time", end_datetime)
        
        # Add vehicle filter if provided
        if vehicle_ids and len(vehicle_ids) > 0:
            query = query.in_("vehicle_id", vehicle_ids)
        
        # Add driver filter if provided
        if driver_ids and len(driver_ids) > 0:
            query = query.in_("driver_id", driver_ids)
        
        # Execute the query
        trips_response = query.execute()
        
        # Initialize counters
        total_collections = 0.0
        total_fuel_expense = 0.0
        total_repair_expense = 0.0
        trip_count = 0
        
        # Process trip data
        for trip in trips_response.data:
            # Extract values with safety checks
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            fuel_expense = float(trip.get("fuel_expense", 0) or 0)
            repair_expense = float(trip.get("repair_expense", 0) or 0)
            
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