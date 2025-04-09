from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict, List
from datetime import datetime, date, timedelta

from app.core.db import supabase
from app.core.security import get_current_active_user
from app.schemas.dashboard import DashboardOverview, DashboardStats, VehiclePerformance, DriverPerformance, TimeSeriesData

router = APIRouter()

@router.get("/overview/finances", response_model=DashboardOverview)
async def get_financial_overview(current_user = Depends(get_current_active_user)) -> Any:
    """
    Get financial overview for the dashboard cards:
    - Total revenue today
    - Active vehicles count
    - Upcoming renewals (static value)
    - Average collection per vehicle
    """
    try:
        # Get today's date for filtering
        today = date.today()
        today_str = today.isoformat()
        
        # 1. Calculate Total Revenue Today
        # Sum collected_amount from trips that started or ended today
        today_trips = supabase.table("trips").select("collected_amount").gte("start_time", f"{today_str}T00:00:00").lt("start_time", f"{today_str}T23:59:59").execute()
        
        # Add trips that ended today but might have started earlier
        ended_today_trips = supabase.table("trips").select("collected_amount").gte("end_time", f"{today_str}T00:00:00").lt("end_time", f"{today_str}T23:59:59").execute()
        
        # Combine and sum the results
        total_revenue_today = 0
        for trip in today_trips.data:
            total_revenue_today += float(trip.get("collected_amount", 0) or 0)
            
        for trip in ended_today_trips.data:
            if trip not in today_trips.data:  # Avoid double counting
                total_revenue_today += float(trip.get("collected_amount", 0) or 0)
        
        # 2. Count Active Vehicles
        active_vehicles_response = supabase.table("vehicles").select("id").eq("status", "active").execute()
        active_vehicles_count = len(active_vehicles_response.data)
        
        # 3. Upcoming Renewals - Static value as requested
        upcoming_renewals = 5  # Static value as per requirements
        
        # 4. Average Collection Per Vehicle
        # First, get all active vehicles
        all_vehicles = supabase.table("vehicles").select("id").execute()
        
        # Then, get all trips from the last 30 days to calculate average
        thirty_days_ago = (today - timedelta(days=30)).isoformat()
        recent_trips = supabase.table("trips").select("vehicle_id,collected_amount").gte("start_time", f"{thirty_days_ago}T00:00:00").execute()
        
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
        
        # Return the overview data
        return {
            "total_revenue_today": total_revenue_today,
            "active_vehicles_count": active_vehicles_count,
            "upcoming_renewals": upcoming_renewals,
            "avg_collection_per_vehicle": avg_collection_per_vehicle
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
        trips_response = supabase.table("trips").select("*").gte("start_time", start_date.isoformat()).execute()
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
            start_time = trip.get("start_time")
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