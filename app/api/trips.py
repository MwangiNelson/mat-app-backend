from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Any, Optional
from datetime import datetime, date

from app.core.db import supabase
from app.core.security import get_current_active_user, check_admin_role
from app.schemas.trips import TripCreate, TripUpdate, TripResponse, TripDetail
from app.core.utils import DateTimeEncoder
import json

router = APIRouter()

@router.post("/", response_model=TripDetail)
async def create_trip(trip_data: TripCreate, current_user = Depends(get_current_active_user)) -> Any:
    """
    Create a new trip.
    """
    try:
        # Check if vehicle exists
        vehicle_response = supabase.table("vehicles").select("passenger_capacity, reg_no").eq("id", trip_data.vehicle_id).execute()
        
        if not vehicle_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
        
        # Check if driver exists
        driver_response = supabase.table("drivers").select("name").eq("id", trip_data.driver_id).execute()
        
        if not driver_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found"
            )
        
        # Check if route exists and get fare amount
        route_response = supabase.table("routes").select("*").eq("id", trip_data.route_id).execute()
        
        if not route_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Route not found"
            )
        
        # Calculate expected amount based on passenger count and fare
        route_fare = route_response.data[0]["fare_amount"]
        passenger_count = trip_data.passenger_count
        expected_amount = route_fare * passenger_count
        
        # Create trip with calculated expected amount
        trip_dict = trip_data.dict()
        trip_dict["expected_amount"] = expected_amount
        
        response = supabase.table("trips").insert(trip_dict).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create trip"
            )
        
        # Enrich response with driver and vehicle information
        trip_data = response.data[0]
        
        enriched_trip = {
            **trip_data,
            "driver_name": driver_response.data[0]["name"],
            "vehicle_registration": vehicle_response.data[0]["reg_no"],
            "route_name": route_response.data[0].get("name"),
            "origin": route_response.data[0].get("origin"),
            "destination": route_response.data[0].get("destination"),
            "fare_amount": route_fare
        }
        
        # Split collection_time into date and time fields
        if "collection_time" in trip_data and trip_data["collection_time"]:
            dt_obj = datetime.fromisoformat(trip_data["collection_time"].replace('Z', '+00:00'))
            enriched_trip["collection_date"] = dt_obj.strftime("%Y-%m-%d")
            enriched_trip["collection_time_only"] = dt_obj.strftime("%H:%M:%S")
        
        return enriched_trip
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating trip: {str(e)}"
        )

@router.get("/", response_model=List[TripDetail])
async def get_trips(
    vehicle_id: Optional[str] = None,
    driver_id: Optional[str] = None,
    route_id: Optional[str] = None,
    status: Optional[str] = None,
    date: Optional[date] = None,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Get all trips, with optional filtering.
    """
    try:
        query = supabase.table("trips").select("*")
        
        if vehicle_id:
            query = query.eq("vehicle_id", vehicle_id)
        
        if driver_id:
            query = query.eq("driver_id", driver_id)
        
        if route_id:
            query = query.eq("route_id", route_id)
        
        if status:
            query = query.eq("status", status)
        
        if date:
            query = query.gte("collection_time", date.isoformat())
            next_day = date.replace(day=date.day + 1)
            query = query.lt("collection_time", next_day.isoformat())
        
        response = query.order("collection_time", desc=True).execute()
        
        # Enrich trip data with driver and vehicle information
        enriched_trips = []
        for trip in response.data:
            # Get driver info
            driver = supabase.table("drivers").select("name").eq("id", trip["driver_id"]).execute()
            
            # Get vehicle info
            vehicle = supabase.table("vehicles").select("reg_no").eq("id", trip["vehicle_id"]).execute()
            
            # Create enriched trip object
            enriched_trip = {
                **trip,
                "driver_name": driver.data[0]["name"] if driver.data else None,
                "vehicle_registration": vehicle.data[0]["reg_no"] if vehicle.data else None,
                "route_name": None,  # These fields are in TripDetail but we're not populating them here
                "origin": None,
                "destination": None,
                "fare_amount": None
            }
            
            # Split collection_time into date and time fields
            if "collection_time" in trip and trip["collection_time"]:
                dt_obj = datetime.fromisoformat(trip["collection_time"].replace('Z', '+00:00'))
                enriched_trip["collection_date"] = dt_obj.strftime("%Y-%m-%d") 
                enriched_trip["collection_time_only"] = dt_obj.strftime("%H:%M:%S")
            
            enriched_trips.append(enriched_trip)
        
        return enriched_trips
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching trips: {str(e)}"
        )

@router.get("/{trip_id}", response_model=TripDetail)
async def get_trip_detail(trip_id: str, current_user = Depends(get_current_active_user)) -> Any:
    """
    Get detailed information about a specific trip.
    """
    try:
        # Call database function to get trip details
        response = supabase.rpc('get_trip_detail', {'trip_id': trip_id}).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )
        
        trip_data = response.data[0]
        
        # Split collection_time into date and time fields
        if "collection_time" in trip_data and trip_data["collection_time"]:
            dt_obj = datetime.fromisoformat(trip_data["collection_time"].replace('Z', '+00:00'))
            trip_data["collection_date"] = dt_obj.strftime("%Y-%m-%d")
            trip_data["collection_time_only"] = dt_obj.strftime("%H:%M:%S")
        
        return trip_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching trip details: {str(e)}"
        )

@router.put("/{trip_id}", response_model=TripDetail)
async def update_trip(
    trip_id: str, 
    trip_update: TripUpdate, 
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Update a trip.
    """
    try:
        # Check if trip exists
        check_response = supabase.table("trips").select("*").eq("id", trip_id).execute()
        
        if not check_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )
        
        # Filter out None values
        update_data = {k: v for k, v in trip_update.dict().items() if v is not None}
        
        if not update_data:
            # Even if no updates, we need to enrich the response with driver and vehicle info
            trip_data = check_response.data[0]
            driver = supabase.table("drivers").select("name").eq("id", trip_data["driver_id"]).execute()
            vehicle = supabase.table("vehicles").select("reg_no").eq("id", trip_data["vehicle_id"]).execute()
            
            enriched_trip = {
                **trip_data,
                "driver_name": driver.data[0]["name"] if driver.data else None,
                "vehicle_registration": vehicle.data[0]["reg_no"] if vehicle.data else None,
                "route_name": None,
                "origin": None,
                "destination": None,
                "fare_amount": None
            }
            
            # Split collection_time into date and time fields
            if "collection_time" in trip_data and trip_data["collection_time"]:
                dt_obj = datetime.fromisoformat(trip_data["collection_time"].replace('Z', '+00:00'))
                enriched_trip["collection_date"] = dt_obj.strftime("%Y-%m-%d")
                enriched_trip["collection_time_only"] = dt_obj.strftime("%H:%M:%S")
            
            return enriched_trip
        
        # Update trip
        response = supabase.table("trips").update(update_data).eq("id", trip_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update trip"
            )
        
        # If trip is completed, update daily summary
        if "status" in update_data and update_data["status"] == "completed":
            trip_data = response.data[0]
            trip_date = datetime.fromisoformat(trip_data["collection_time"].replace('Z', '+00:00')).date()
            
            # Calculate total expenses
            total_expenses = trip_data.get("fuel_expense", 0) + trip_data.get("repair_expense", 0)
            net_profit = trip_data.get("collected_amount", 0) - total_expenses
            
            # Check if summary exists for this vehicle and date
            summary_check = supabase.table("daily_summaries").select("*").eq("vehicle_id", trip_data["vehicle_id"]).eq("date", trip_date.isoformat()).execute()
            
            if summary_check.data:
                # Update existing summary
                summary = summary_check.data[0]
                summary_update = {
                    "trip_count": summary["trip_count"] + 1,
                    "total_expected_amount": summary["total_expected_amount"] + trip_data["expected_amount"],
                    "total_collected_amount": summary["total_collected_amount"] + (trip_data.get("collected_amount", 0) or 0),
                    "total_expenses": summary["total_expenses"] + total_expenses,
                    "net_profit": summary["net_profit"] + net_profit
                }
                
                supabase.table("daily_summaries").update(summary_update).eq("id", summary["id"]).execute()
            else:
                # Create new summary
                summary_data = {
                    "vehicle_id": trip_data["vehicle_id"],
                    "driver_id": trip_data["driver_id"],
                    "date": trip_date.isoformat(),
                    "trip_count": 1,
                    "total_expected_amount": trip_data["expected_amount"],
                    "total_collected_amount": trip_data.get("collected_amount", 0) or 0,
                    "total_expenses": total_expenses,
                    "net_profit": net_profit
                }
                
                supabase.table("daily_summaries").insert(summary_data).execute()
        
        # Enrich response with driver and vehicle information
        trip_data = response.data[0]
        driver = supabase.table("drivers").select("name").eq("id", trip_data["driver_id"]).execute()
        vehicle = supabase.table("vehicles").select("reg_no").eq("id", trip_data["vehicle_id"]).execute()
        
        enriched_trip = {
            **trip_data,
            "driver_name": driver.data[0]["name"] if driver.data else None,
            "vehicle_registration": vehicle.data[0]["reg_no"] if vehicle.data else None,
            "route_name": None,
            "origin": None,
            "destination": None,
            "fare_amount": None
        }
        
        # Split collection_time into date and time fields
        if "collection_time" in trip_data and trip_data["collection_time"]:
            dt_obj = datetime.fromisoformat(trip_data["collection_time"].replace('Z', '+00:00'))
            enriched_trip["collection_date"] = dt_obj.strftime("%Y-%m-%d")
            enriched_trip["collection_time_only"] = dt_obj.strftime("%H:%M:%S")
        
        return enriched_trip
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating trip: {str(e)}"
        )

@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(trip_id: str, current_user = Depends(check_admin_role)) -> None:
    """
    Delete a trip (admin only).
    """
    try:
        # Check if trip exists
        check_response = supabase.table("trips").select("*").eq("id", trip_id).execute()
        
        if not check_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found"
            )
        
        # Delete trip
        supabase.table("trips").delete().eq("id", trip_id).execute()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting trip: {str(e)}"
        ) 