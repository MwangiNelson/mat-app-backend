from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Any, Optional
from datetime import datetime

from app.core.db import supabase
from app.core.security import get_current_user, get_current_active_user
from app.schemas.location import (
    LocationCreate,
    LocationResponse,
    TripCreate,
    TripUpdate,
    TripResponse,
    RoutePoint,
    TripStatus
)

router = APIRouter()

@router.post("/", response_model=LocationResponse)
async def update_driver_location(
    location: LocationCreate,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Update a driver's current location.
    """
    # Validate driver exists
    driver = supabase.table("drivers").select("*").eq("id", location.driver_id).execute()
    if not driver.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Create location entry
    response = supabase.table("locations").insert(location.dict()).execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update location",
        )
    
    # Enrich with driver name
    location_data = response.data[0]
    location_response = {
        **location_data,
        "driver_name": driver.data[0]["name"]
    }
    
    return location_response

@router.get("/drivers", response_model=List[LocationResponse])
async def get_drivers_locations(current_user = Depends(get_current_user)) -> Any:
    """
    Get the latest location for all active drivers.
    """
    # For each active driver, get the most recent location
    drivers = supabase.table("drivers").select("id, name").eq("status", "active").execute()
    
    if not drivers.data:
        return []
    
    locations = []
    for driver in drivers.data:
        # Get the most recent location for the driver
        latest_location = (
            supabase.table("locations")
            .select("*")
            .eq("driver_id", driver["id"])
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        
        if latest_location.data:
            location_data = latest_location.data[0]
            locations.append({
                **location_data,
                "driver_name": driver["name"]
            })
    
    return locations

@router.get("/driver/{driver_id}/history", response_model=List[LocationResponse])
async def get_driver_location_history(
    driver_id: str,
    limit: int = 20,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get location history for a specific driver.
    """
    # Validate driver exists
    driver = supabase.table("drivers").select("name").eq("id", driver_id).execute()
    if not driver.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Get the recent locations for the driver
    locations = (
        supabase.table("locations")
        .select("*")
        .eq("driver_id", driver_id)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    
    # Enrich with driver name
    location_history = []
    for loc in locations.data:
        location_history.append({
            **loc,
            "driver_name": driver.data[0]["name"]
        })
    
    return location_history

@router.post("/trips", response_model=TripResponse)
async def start_trip(
    trip: TripCreate,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Start a new trip.
    """
    # Validate driver exists
    driver = supabase.table("drivers").select("name").eq("id", trip.driver_id).execute()
    if not driver.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Validate vehicle exists
    vehicle = supabase.table("vehicles").select("reg_no").eq("id", trip.vehicle_id).execute()
    if not vehicle.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Check if driver already has an active trip
    active_trip = (
        supabase.table("trips")
        .select("*")
        .eq("driver_id", trip.driver_id)
        .eq("status", "active")
        .execute()
    )
    
    if active_trip.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Driver already has an active trip",
        )
    
    # Create trip data
    trip_data = {
        "driver_id": trip.driver_id,
        "vehicle_id": trip.vehicle_id,
        "start_time": datetime.utcnow().isoformat(),
        "route": [],
        "status": "active"
    }
    
    response = supabase.table("trips").insert(trip_data).execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start trip",
        )
    
    # Enrich response with driver and vehicle info
    trip_response = {
        **response.data[0],
        "driver_name": driver.data[0]["name"],
        "vehicle_reg_no": vehicle.data[0]["reg_no"]
    }
    
    return trip_response

@router.put("/trips/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: str,
    trip_update: TripUpdate,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Update a trip (add route points or complete/cancel).
    """
    # Validate trip exists
    trip = supabase.table("trips").select("*").eq("id", trip_id).execute()
    if not trip.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )
    
    current_trip = trip.data[0]
    
    # Handle different update operations
    update_data = {}
    
    # If status is updated to completed or cancelled, set end_time
    if trip_update.status and trip_update.status != current_trip["status"]:
        update_data["status"] = trip_update.status
        if trip_update.status in ["completed", "cancelled"]:
            update_data["end_time"] = datetime.utcnow().isoformat()
    
    # If route point is provided, append to route
    if trip_update.route_point:
        current_route = current_trip.get("route", [])
        if not isinstance(current_route, list):
            current_route = []
        
        route_point_data = {
            "latitude": trip_update.route_point.latitude,
            "longitude": trip_update.route_point.longitude,
            "timestamp": trip_update.route_point.timestamp.isoformat()
        }
        current_route.append(route_point_data)
        update_data["route"] = current_route
    
    # If end time is provided, use it
    if trip_update.end_time:
        update_data["end_time"] = trip_update.end_time.isoformat()
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    
    response = supabase.table("trips").update(update_data).eq("id", trip_id).execute()
    
    # Get driver and vehicle info
    driver_id = current_trip["driver_id"]
    vehicle_id = current_trip["vehicle_id"]
    
    driver = supabase.table("drivers").select("name").eq("id", driver_id).execute()
    vehicle = supabase.table("vehicles").select("reg_no").eq("id", vehicle_id).execute()
    
    # Enrich response
    trip_response = {
        **response.data[0],
        "driver_name": driver.data[0]["name"] if driver.data else None,
        "vehicle_reg_no": vehicle.data[0]["reg_no"] if vehicle.data else None
    }
    
    return trip_response

@router.get("/trips/active", response_model=List[TripResponse])
async def get_active_trips(current_user = Depends(get_current_user)) -> Any:
    """
    Get all active trips.
    """
    trips = supabase.table("trips").select("*").eq("status", "active").execute()
    
    # Enrich with driver and vehicle info
    enriched_trips = []
    for trip in trips.data:
        driver = supabase.table("drivers").select("name").eq("id", trip["driver_id"]).execute()
        vehicle = supabase.table("vehicles").select("reg_no").eq("id", trip["vehicle_id"]).execute()
        
        enriched_trip = {
            **trip,
            "driver_name": driver.data[0]["name"] if driver.data else None,
            "vehicle_reg_no": vehicle.data[0]["reg_no"] if vehicle.data else None
        }
        enriched_trips.append(enriched_trip)
    
    return enriched_trips

@router.get("/trips/vehicle/{vehicle_id}", response_model=List[TripResponse])
async def get_vehicle_trips(
    vehicle_id: str,
    limit: int = 10,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get trips for a specific vehicle.
    """
    # Validate vehicle exists
    vehicle = supabase.table("vehicles").select("reg_no").eq("id", vehicle_id).execute()
    if not vehicle.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Get trips
    trips = (
        supabase.table("trips")
        .select("*")
        .eq("vehicle_id", vehicle_id)
        .order("start_time", desc=True)
        .limit(limit)
        .execute()
    )
    
    # Enrich with driver info
    enriched_trips = []
    for trip in trips.data:
        driver = supabase.table("drivers").select("name").eq("id", trip["driver_id"]).execute()
        
        enriched_trip = {
            **trip,
            "driver_name": driver.data[0]["name"] if driver.data else None,
            "vehicle_reg_no": vehicle.data[0]["reg_no"]
        }
        enriched_trips.append(enriched_trip)
    
    return enriched_trips

@router.get("/trips/driver/{driver_id}", response_model=List[TripResponse])
async def get_driver_trips(
    driver_id: str,
    limit: int = 10,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get trips for a specific driver.
    """
    # Validate driver exists
    driver = supabase.table("drivers").select("name").eq("id", driver_id).execute()
    if not driver.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Get trips
    trips = (
        supabase.table("trips")
        .select("*")
        .eq("driver_id", driver_id)
        .order("start_time", desc=True)
        .limit(limit)
        .execute()
    )
    
    # Enrich with vehicle info
    enriched_trips = []
    for trip in trips.data:
        vehicle = supabase.table("vehicles").select("reg_no").eq("id", trip["vehicle_id"]).execute()
        
        enriched_trip = {
            **trip,
            "driver_name": driver.data[0]["name"],
            "vehicle_reg_no": vehicle.data[0]["reg_no"] if vehicle.data else None
        }
        enriched_trips.append(enriched_trip)
    
    return enriched_trips 