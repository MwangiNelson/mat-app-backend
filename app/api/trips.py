from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status
from typing import List, Any, Optional, Dict
import math
import json
import logging
from datetime import datetime, date, timedelta, timezone

from app.models import get_db
from app.models.models import Trip, Driver, Vehicle, User
from app.core.security import get_current_active_user, check_admin_role
from app.core.cache import cached, invalidate_cache
from app.schemas.trips import TripCreate, TripUpdate, TripResponse, TripDetail, PaginatedResponse
from app.schemas.user import ErrorResponse
from app.core.utils import DateTimeEncoder, serialize_datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

logger = logging.getLogger(__name__)

router = APIRouter()

def create_trip_error(status_code: int, message: str, error_type: str, details: Dict = None) -> HTTPException:
    """Create standardized trip API error response"""
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

def serialize_for_db(data):
    """
    Convert dict with datetime objects to JSON serializable format.
    """
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data

@router.post("/", response_model=TripDetail)
@invalidate_cache("trips:*", "dashboard:*", "vehicles:*", "drivers:*")  # Clear multiple caches
async def create_trip(
    trip_data: TripCreate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Create a new trip.
    """
    try:
        # Check if vehicle exists
        vehicle = db.query(Vehicle).filter(Vehicle.id == trip_data.vehicle_id).first()

        if not vehicle:
            raise create_trip_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Vehicle not found. Please check the vehicle ID and try again.",
                error_type="vehicle_not_found",
                details={"vehicle_id": str(trip_data.vehicle_id)}
            )

        # Check if driver exists
        driver = db.query(Driver).filter(Driver.id == trip_data.driver_id).first()

        if not driver:
            raise create_trip_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Driver not found. Please check the driver ID and try again.",
                error_type="driver_not_found",
                details={"driver_id": str(trip_data.driver_id)}
            )

        # Check if driver is active
        if driver.status != "active":
            raise create_trip_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Cannot assign trip to inactive driver. Please select an active driver.",
                error_type="driver_inactive",
                details={"driver_id": str(trip_data.driver_id), "driver_status": driver.status}
            )

        # Check if vehicle is active
        if vehicle.status != "active":
            raise create_trip_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Cannot assign trip to inactive vehicle. Please select an active vehicle.",
                error_type="vehicle_inactive",
                details={"vehicle_id": str(trip_data.vehicle_id), "vehicle_status": vehicle.status}
            )
        

        # Create new trip
        new_trip = Trip(
            driver_id=trip_data.driver_id,
            vehicle_id=trip_data.vehicle_id,
            collection_time=trip_data.collection_time,
            route=trip_data.route,
            notes=trip_data.notes,
            collected_amount=trip_data.collected_amount or 0,
            repair_expense=trip_data.repair_expense or 0.0,
            created_by=current_user.user_id,  # Use current user, not from payload
            status=trip_data.status or "completed"
        )

        db.add(new_trip)
        db.commit()
        db.refresh(new_trip)

        # Return enriched trip data
        enriched_trip = {
            "id": str(new_trip.id),
            "driver_id": str(new_trip.driver_id),
            "vehicle_id": str(new_trip.vehicle_id),
            "driver_name": driver.name,
            "vehicle_registration": vehicle.reg_no,
            "collection_time": new_trip.collection_time.isoformat() if new_trip.collection_time else None,
            "route": new_trip.route,
            "notes": new_trip.notes,
            "collected_amount": new_trip.collected_amount,
            "repair_expense": new_trip.repair_expense,
            "created_by": str(new_trip.created_by),
            "status": new_trip.status,
            "created_at": new_trip.created_at.isoformat() if new_trip.created_at else None,
            "updated_at": new_trip.updated_at.isoformat() if new_trip.updated_at else None,
        }

        return enriched_trip

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create trip: {str(e)}")
        raise create_trip_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create trip. Please try again later.",
            error_type="trip_creation_failed",
            details={"error": str(e)}
        )

@router.get("/", response_model=PaginatedResponse[TripDetail])
@cached(ttl=300, key_prefix="trips")  # Cache for 5 minutes
async def get_trips(
    vehicle_id: Optional[str] = None,
    driver_id: Optional[str] = None,
    route: Optional[str] = None,
    trip_status: Optional[str] = None,
    date: Optional[date] = None,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get all trips, with optional filtering and pagination.
    """
    try:
        # Build base query with joins
        query = db.query(Trip).join(Driver, Trip.driver_id == Driver.id).join(Vehicle, Trip.vehicle_id == Vehicle.id)

        # Apply filters
        if vehicle_id:
            query = query.filter(Trip.vehicle_id == vehicle_id)

        if driver_id:
            query = query.filter(Trip.driver_id == driver_id)

        if route:
            query = query.filter(Trip.route.ilike(f"%{route}%"))  # Case-insensitive search

        if trip_status:
            query = query.filter(Trip.status == trip_status)

        if date:
            # Filter by date range (from start of date to end of date)
            start_datetime = datetime.combine(date, datetime.min.time())
            end_datetime = datetime.combine(date, datetime.max.time())
            query = query.filter(Trip.collection_time >= start_datetime, Trip.collection_time <= end_datetime)

        # Get total count for pagination
        total = query.count()

        # Calculate pagination values
        total_pages = math.ceil(total / per_page) if total > 0 else 1
        offset = (page - 1) * per_page

        # Apply ordering and pagination
        trips = query.order_by(desc(Trip.collection_time)).offset(offset).limit(per_page).all()

        # Process trips data with enriched information
        enriched_trips = []
        for trip in trips:
            # Create enriched trip object
            enriched_trip = {
                "id": str(trip.id),
                "driver_id": str(trip.driver_id),
                "vehicle_id": str(trip.vehicle_id),
                "driver_name": trip.driver.name,
                "vehicle_registration": trip.vehicle.reg_no,
                "collection_time": trip.collection_time.isoformat() if trip.collection_time else None,
                "route": trip.route,
                "notes": trip.notes,
                "collected_amount": float(trip.collected_amount),
                "repair_expense": float(trip.repair_expense) if trip.repair_expense else 0.0,
                "created_by": str(trip.created_by),
                "status": trip.status,
                "created_at": trip.created_at.isoformat() if trip.created_at else None,
                "updated_at": trip.updated_at.isoformat() if trip.updated_at else None,
                # Additional fields for TripDetail schema
                "route_text": trip.route,  # Using route as route_text
                "origin": None,  # Not available in current schema
                "destination": None,  # Not available in current schema
                "fare_amount": None  # Not available in current schema
            }

            # Split collection_time into date and time fields if available
            if trip.collection_time:
                enriched_trip["collection_date"] = trip.collection_time.strftime("%Y-%m-%d")
                enriched_trip["collection_time_only"] = trip.collection_time.strftime("%H:%M:%S")

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
        logger.error(f"Failed to retrieve trips: {str(e)}")
        raise create_trip_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve trips. Please try again later.",
            error_type="trips_retrieval_failed",
            details={"error": str(e)}
        )

@router.get("/{trip_id}", response_model=TripDetail)
@cached(ttl=300, key_prefix="trips")  # Cache for 5 minutes - individual trip details
async def get_trip_detail(
    trip_id: str,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get detailed information about a specific trip.
    """
    try:
        # Query trip with joined driver and vehicle information
        trip = db.query(Trip).join(Driver, Trip.driver_id == Driver.id).join(Vehicle, Trip.vehicle_id == Vehicle.id).filter(Trip.id == trip_id).first()

        if not trip:
            raise create_trip_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Trip not found. Please check the trip ID and try again.",
                error_type="trip_not_found",
                details={"trip_id": trip_id}
            )

        # Build detailed trip response
        trip_detail = {
            "id": str(trip.id),
            "driver_id": str(trip.driver_id),
            "vehicle_id": str(trip.vehicle_id),
            "driver_name": trip.driver.name,
            "vehicle_registration": trip.vehicle.reg_no,
            "collection_time": trip.collection_time.isoformat() if trip.collection_time else None,
            "route": trip.route,
            "route_text": trip.route,  # Using route as route_text
            "notes": trip.notes,
            "collected_amount": float(trip.collected_amount),
            "repair_expense": float(trip.repair_expense) if trip.repair_expense else 0.0,
            "created_by": str(trip.created_by),
            "status": trip.status,
            "created_at": trip.created_at.isoformat() if trip.created_at else None,
            "updated_at": trip.updated_at.isoformat() if trip.updated_at else None,
            # Additional fields for compatibility
            "origin": None,  # Not available in current schema
            "destination": None,  # Not available in current schema
            "fare_amount": None  # Not available in current schema
        }

        # Split collection_time into date and time fields if available
        if trip.collection_time:
            trip_detail["collection_date"] = trip.collection_time.strftime("%Y-%m-%d")
            trip_detail["collection_time_only"] = trip.collection_time.strftime("%H:%M:%S")

        return trip_detail

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to retrieve trip detail for {trip_id}: {str(e)}")
        raise create_trip_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve trip details. Please try again later.",
            error_type="trip_detail_retrieval_failed",
            details={"trip_id": trip_id, "error": str(e)}
        )

@router.put("/{trip_id}", response_model=TripDetail)
@invalidate_cache("trips:*", "dashboard:*", "vehicles:*", "drivers:*")  # Clear multiple caches
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
@invalidate_cache("trips:*", "dashboard:*", "vehicles:*", "drivers:*")  # Clear multiple caches
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