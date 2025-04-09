from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Any, Optional
from datetime import date, timedelta

from app.core.db import supabase
from app.core.security import get_current_user, check_admin_role
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleUpdate,
    VehicleResponse
)

router = APIRouter()

@router.get("/", response_model=List[VehicleResponse])
async def get_vehicles(
    current_user = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None
) -> Any:
    """
    Retrieve all vehicles with optional status filtering.
    """
    query = supabase.table("vehicles").select("*").order("reg_no").range(skip, skip + limit - 1)
    
    if status:
        query = query.eq("status", status)
    
    response = query.execute()
    
    return response.data

@router.post("/", response_model=VehicleResponse)
async def create_vehicle(
    vehicle_in: VehicleCreate,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Create new vehicle.
    """
    # Check if reg_no already exists
    existing = supabase.table("vehicles").select("*").eq("reg_no", vehicle_in.reg_no).execute()
    
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vehicle with this registration number already exists",
        )
    
    response = supabase.table("vehicles").insert(vehicle_in.dict()).execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create vehicle",
        )
    
    return response.data[0]

@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: str,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get vehicle by ID.
    """
    response = supabase.table("vehicles").select("*").eq("id", vehicle_id).execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    return response.data[0]

@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: str,
    vehicle_in: VehicleUpdate,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Update a vehicle.
    """
    # Check if vehicle exists
    existing = supabase.table("vehicles").select("*").eq("id", vehicle_id).execute()
    
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Filter out None values
    update_data = {k: v for k, v in vehicle_in.dict().items() if v is not None}
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    
    response = supabase.table("vehicles").update(update_data).eq("id", vehicle_id).execute()
    
    return response.data[0]

@router.delete("/{vehicle_id}")
async def delete_vehicle(
    vehicle_id: str,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Delete a vehicle.
    """
    # Check if vehicle exists
    existing = supabase.table("vehicles").select("*").eq("id", vehicle_id).execute()
    
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Check if vehicle has operations
    operations = supabase.table("operations").select("id").eq("vehicle_id", vehicle_id).limit(1).execute()
    
    if operations.data:
        # Instead of deleting, mark as inactive
        response = supabase.table("vehicles").update({"status": "inactive"}).eq("id", vehicle_id).execute()
        return {"message": "Vehicle marked as inactive (has operations)"}
    
    # If no operations, delete the vehicle
    response = supabase.table("vehicles").delete().eq("id", vehicle_id).execute()
    
    return {"message": "Vehicle deleted successfully"}

@router.get("/expiring", response_model=List[VehicleResponse])
async def get_expiring_vehicles(
    days: int = Query(30, ge=1, le=90),
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get vehicles with documents expiring within the next X days.
    """
    today = date.today()
    expiry_date = today + timedelta(days=days)
    
    # Get vehicles where either insurance or TLB is expiring
    query = supabase.table("vehicles").select("*").or_(
        f"insurance_expiry.lte.{expiry_date.isoformat()},tlb_expiry.lte.{expiry_date.isoformat()}"
    ).gte("insurance_expiry", today.isoformat()).gte("tlb_expiry", today.isoformat()).execute()
    
    return query.data 