from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Any, Optional
from datetime import date, timedelta

from app.core.db import supabase
from app.core.security import get_current_user, check_admin_role
from app.schemas.driver import (
    DriverCreate,
    DriverUpdate,
    DriverResponse,
    DriverRating
)

router = APIRouter()

@router.get("/", response_model=List[DriverResponse])
async def get_drivers(
    current_user = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None
) -> Any:
    """
    Retrieve all drivers with optional status filtering.
    """
    query = supabase.table("drivers").select("*").order("name").range(skip, skip + limit - 1)
    
    if status:
        query = query.eq("status", status)
    
    response = query.execute()
    
    return response.data

@router.post("/", response_model=DriverResponse)
async def create_driver(
    driver_in: DriverCreate,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Create new driver.
    """
    # Check if license_no already exists
    existing = supabase.table("drivers").select("*").eq("license_no", driver_in.license_no).execute()
    
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Driver with this license number already exists",
        )
    
    response = supabase.table("drivers").insert(driver_in.dict()).execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create driver",
        )
    
    return response.data[0]

@router.get("/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: str,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get driver by ID.
    """
    response = supabase.table("drivers").select("*").eq("id", driver_id).execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    return response.data[0]

@router.put("/{driver_id}", response_model=DriverResponse)
async def update_driver(
    driver_id: str,
    driver_in: DriverUpdate,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Update a driver.
    """
    # Check if driver exists
    existing = supabase.table("drivers").select("*").eq("id", driver_id).execute()
    
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Filter out None values
    update_data = {k: v for k, v in driver_in.dict().items() if v is not None}
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    
    response = supabase.table("drivers").update(update_data).eq("id", driver_id).execute()
    
    return response.data[0]

@router.delete("/{driver_id}")
async def delete_driver(
    driver_id: str,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Delete a driver.
    """
    # Check if driver exists
    existing = supabase.table("drivers").select("*").eq("id", driver_id).execute()
    
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Check if driver has operations
    operations = supabase.table("operations").select("id").eq("driver_id", driver_id).limit(1).execute()
    
    if operations.data:
        # Instead of deleting, mark as inactive
        response = supabase.table("drivers").update({"status": "inactive"}).eq("id", driver_id).execute()
        return {"message": "Driver marked as inactive (has operations)"}
    
    # If no operations, delete the driver
    response = supabase.table("drivers").delete().eq("id", driver_id).execute()
    
    return {"message": "Driver deleted successfully"}

@router.get("/{driver_id}/performance", response_model=dict)
async def get_driver_performance(
    driver_id: str,
    days: int = 30,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get driver performance stats.
    """
    # Check if driver exists
    driver = supabase.table("drivers").select("*").eq("id", driver_id).execute()
    
    if not driver.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Calculate date range
    today = date.today()
    start_date = today - timedelta(days=days)
    
    # Get operations data
    operations = supabase.table("operations").select("*").eq("driver_id", driver_id).gte("date", start_date.isoformat()).execute()
    
    # Calculate performance metrics
    total_days = len(operations.data)
    total_collections = sum(op["morning_collection"] + op["evening_collection"] for op in operations.data) if operations.data else 0
    total_expenses = sum(op["fuel_expense"] + op["repair_expense"] for op in operations.data) if operations.data else 0
    
    # Get vehicle assignments
    vehicles_used = {}
    for op in operations.data:
        vehicle_id = op["vehicle_id"]
        if vehicle_id not in vehicles_used:
            vehicles_used[vehicle_id] = 1
        else:
            vehicles_used[vehicle_id] += 1
    
    # Calculate performance metrics
    metrics = {
        "driver_id": driver_id,
        "driver_name": driver.data[0]["name"],
        "days_worked": total_days,
        "total_collections": total_collections,
        "average_daily_collection": total_collections / total_days if total_days > 0 else 0,
        "total_expenses": total_expenses,
        "net_collection": total_collections - total_expenses,
        "vehicles_used": len(vehicles_used),
        "performance_period": f"{start_date.isoformat()} to {today.isoformat()}"
    }
    
    return metrics

@router.put("/{driver_id}/rate", response_model=DriverResponse)
async def rate_driver(
    driver_id: str,
    rating: DriverRating,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Rate a driver.
    """
    # Check if driver exists
    existing = supabase.table("drivers").select("*").eq("id", driver_id).execute()
    
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Update driver's rating
    response = supabase.table("drivers").update({"rating": rating.rating}).eq("id", driver_id).execute()
    
    return response.data[0] 