from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Any, Optional
import math
from datetime import datetime, date, timedelta

from app.core.db import supabase
from app.core.security import get_current_active_user, check_admin_role
from app.schemas.trips import TripCreate, TripUpdate, TripResponse, TripDetail, PaginatedResponse
from app.core.utils import DateTimeEncoder, serialize_datetime
import json

router = APIRouter()

def serialize_for_db(data):
    """
    Convert dict with datetime objects to JSON serializable format.
    """
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data

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
        

        route = None
        
        # # Get route information if route_id is provided
        # if trip_data.route_id:
        #     # Check if route exists and get fare amount
        #     route_response = supabase.table("routes").select("*").eq("id", trip_data.route_id).execute()
            
        #     if not route_response.data:
        #         raise HTTPException(
        #             status_code=status.HTTP_404_NOT_FOUND,
        #             detail="Route not found"
        #         )
            
        #     # Calculate expected amount based on passenger count and fare
        #     route_fare = route_response.data[0]["fare_amount"]
        #     route = route_response.data[0].get("route")
        #     origin = route_response.data[0].get("origin")
        #     destination = route_response.data[0].get("destination")
        
        # Create trip with calculated expected amount
        trip_dict = trip_data.dict()
        
        # collection_time is already compatible with the database schema
        
        # Serialize datetime objects for database
        trip_dict = serialize_for_db(trip_dict)
        
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
            "route": route,
        }
        
        return enriched_trip
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating trip: {str(e)}"
        )

@router.get("/", response_model=PaginatedResponse[TripDetail])
async def get_trips(
    vehicle_id: Optional[str] = None,
    driver_id: Optional[str] = None,
    route: Optional[str] = None,
    trip_status: Optional[str] = None,
    date: Optional[date] = None,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Get all trips, with optional filtering and pagination.
    """
    try:
        # Use optimized query with joins to fetch trips with related data in one query
        # Build the select statement with joins
        select_query = """
            *,
            vehicles!inner(reg_no),
            drivers!inner(name)
        """
        
        # Build base query for counting total records with joins
        count_query = supabase.table("trips").select("*", count="exact")
        
        # Apply filters to count query
        if vehicle_id:
            count_query = count_query.eq("vehicle_id", vehicle_id)
        
        if driver_id:
            count_query = count_query.eq("driver_id", driver_id)
        
        if route:
            count_query = count_query.eq("route", route)
        
        if trip_status:
            count_query = count_query.eq("status", trip_status)
        
        if date:
            count_query = count_query.gte("collection_time", date.isoformat())
            next_day = date + timedelta(days=1)
            count_query = count_query.lt("collection_time", next_day.isoformat())
        
        # Get total count
        count_response = count_query.execute()
        total = count_response.count
        
        # Calculate pagination values
        total_pages = math.ceil(total / per_page) if total > 0 else 1
        offset = (page - 1) * per_page
        
        # Build query for actual data with joins
        query = supabase.table("trips").select(select_query)
        
        # Apply same filters to data query
        if vehicle_id:
            query = query.eq("vehicle_id", vehicle_id)
        
        if driver_id:
            query = query.eq("driver_id", driver_id)
        
        if route:
            query = query.eq("route", route)
        
        if trip_status:
            query = query.eq("status", trip_status)
        
        if date:
            query = query.gte("collection_time", date.isoformat())
            next_day = date + timedelta(days=1)
            query = query.lt("collection_time", next_day.isoformat())
        
        # Apply pagination and ordering
        response = query.order("collection_time", desc=True).range(offset, offset + per_page - 1).execute()
        
        # Process trips data - the joins will include the related data
        enriched_trips = []
        for trip in response.data:
            # Extract vehicle and driver info from the joined data
            vehicle_data = trip.get("vehicles", {})
            driver_data = trip.get("drivers", {})
            
            # Create enriched trip object
            enriched_trip = {
                **{k: v for k, v in trip.items() if k not in ["vehicles", "drivers"]},  # Exclude join objects
                "driver_name": driver_data.get("name"),
                "vehicle_registration": vehicle_data.get("reg_no"),
                "route": None,  # These fields are in TripDetail but we're not populating them here
                "route_text": trip.get("route_text"),  # Include route_text in response
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
        
        # Create pagination metadata
        pagination_meta = {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
        
        return {
            "data": enriched_trips,
            "meta": pagination_meta
        }
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
        
        # Ensure route_text is included in the response
        if "route_text" not in trip_data and trip_data.get("route_text") is None:
            # Fallback to fetch from database if needed
            trip_raw = supabase.table("trips").select("route_text").eq("id", trip_id).execute()
            if trip_raw.data:
                trip_data["route_text"] = trip_raw.data[0].get("route_text")
        
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
                "route": None,
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
        
        # Serialize datetime objects for database
        update_data = serialize_for_db(update_data)
        
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
            total_expenses =  trip_data.get("repair_expense", 0)
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
            "route": None,
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