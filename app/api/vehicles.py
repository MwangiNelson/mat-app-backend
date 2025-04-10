from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Any, Optional, Dict
from datetime import date, timedelta, datetime
import json

from app.core.db import supabase
from app.core.security import get_current_user, check_admin_role
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleUpdate,
    VehicleResponse,
    parse_date_string
)
from app.schemas.user import ErrorResponse
from app.core.utils import DateTimeEncoder

router = APIRouter()

def create_vehicle_error(status_code: int, message: str, error_type: str, details: Dict = None) -> HTTPException:
    """Create standardized vehicle API error response"""
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

def convert_iso_dates_to_client_format(vehicle: Dict) -> Dict:
    """
    Converts ISO dates (YYYY-MM-DD) to client format (DD-MM-YYYY)
    and ensures passenger_capacity is set
    """
    # Add default passenger_capacity if missing
    if "passenger_capacity" not in vehicle or vehicle["passenger_capacity"] is None:
        vehicle["passenger_capacity"] = 0
        
    # Convert ISO format dates to the expected DD-MM-YYYY format for response
    for date_field in ["insurance_expiry", "tlb_expiry"]:
        if date_field in vehicle and vehicle[date_field]:
            parts = vehicle[date_field].split("-")
            if len(parts) == 3 and len(parts[0]) == 4:  # YYYY-MM-DD format
                year, month, day = parts
                vehicle[date_field] = f"{day}-{month}-{year}"
    
    return vehicle

@router.get("/expiring", response_model=List[VehicleResponse])
async def get_expiring_vehicles(
    days: int = Query(30, ge=1, le=90),
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get vehicles with documents expiring within the next X days.
    """
    try:
        today = date.today()
        expiry_date = today + timedelta(days=days)
        
        # Get vehicles where either insurance or TLB is expiring
        query = supabase.table("vehicles").select("*").or_(
            f"insurance_expiry.lte.{expiry_date.isoformat()},tlb_expiry.lte.{expiry_date.isoformat()}"
        ).gte("insurance_expiry", today.isoformat()).gte("tlb_expiry", today.isoformat()).execute()
        
        # Convert date formats for each vehicle
        for i in range(len(query.data)):
            query.data[i] = convert_iso_dates_to_client_format(query.data[i])
        
        return query.data
    except Exception as e:
        raise create_vehicle_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Error retrieving expiring vehicles: {str(e)}",
            error_type="server_error",
            details={"days": days}
        )

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
    try:
        query = supabase.table("vehicles").select("*").order("reg_no").range(skip, skip + limit - 1)
        
        if status:
            query = query.eq("status", status)
        
        response = query.execute()
        
        # Convert date formats for each vehicle
        for i in range(len(response.data)):
            response.data[i] = convert_iso_dates_to_client_format(response.data[i])
        
        return response.data
    except Exception as e:
        raise create_vehicle_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Error retrieving vehicles: {str(e)}",
            error_type="server_error"
        )

@router.post("/", response_model=VehicleResponse)
async def create_vehicle(
    vehicle_in: VehicleCreate,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Create new vehicle.
    """
    try:
        # Check if reg_no already exists
        existing = supabase.table("vehicles").select("*").eq("reg_no", vehicle_in.registration).execute()
        
        if existing.data:
            raise create_vehicle_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Vehicle with this registration number already exists",
                error_type="duplicate_registration",
                details={"registration": vehicle_in.registration}
            )
        
        # Convert to dict using by_alias=True to use the reg_no field name
        vehicle_dict = vehicle_in.dict(by_alias=True)
        
        # Convert date objects to ISO strings for Supabase
        for date_field in ['insurance_expiry', 'tlb_expiry']:
            if date_field in vehicle_dict and isinstance(vehicle_dict[date_field], date):
                vehicle_dict[date_field] = vehicle_dict[date_field].isoformat()
        
        response = supabase.table("vehicles").insert(vehicle_dict).execute()
        
        if not response.data:
            raise create_vehicle_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Failed to create vehicle",
                error_type="database_error"
            )
        
        return response.data[0]
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ValueError as e:
        # Handle validation errors from Pydantic
        raise create_vehicle_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(e),
            error_type="validation_error"
        )
    except Exception as e:
        # Handle any other exceptions
        raise create_vehicle_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Error creating vehicle: {str(e)}",
            error_type="server_error",
            details={"error": str(e)}
        )

@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: str,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get vehicle by ID.
    """
    try:
        response = supabase.table("vehicles").select("*").eq("id", vehicle_id).execute()
        
        if not response.data:
            raise create_vehicle_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Vehicle not found",
                error_type="not_found",
                details={"vehicle_id": vehicle_id}
            )
        
        # Convert date formats
        vehicle = convert_iso_dates_to_client_format(response.data[0])
        
        return vehicle
    except HTTPException:
        raise
    except Exception as e:
        raise create_vehicle_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Error retrieving vehicle: {str(e)}",
            error_type="server_error",
            details={"vehicle_id": vehicle_id}
        )

@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: str,
    vehicle_in: VehicleUpdate,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Update a vehicle.
    """
    try:
        # Check if vehicle exists
        existing = supabase.table("vehicles").select("*").eq("id", vehicle_id).execute()
        
        if not existing.data:
            raise create_vehicle_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Vehicle not found",
                error_type="not_found",
                details={"vehicle_id": vehicle_id}
            )
        
        # Filter out None values and handle field aliases
        update_data = {}
        data_dict = vehicle_in.dict(exclude_none=True)
        
        # Handle specific field mappings and convert dates to strings
        for key, value in data_dict.items():
            # Map registration to reg_no
            if key == "registration":
                update_data["reg_no"] = value
            # Convert date objects to ISO format strings
            elif key in ['insurance_expiry', 'tlb_expiry'] and isinstance(value, date):
                update_data[key] = value.isoformat()
            else:
                update_data[key] = value
        
        if not update_data:
            raise create_vehicle_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="No fields to update",
                error_type="missing_data"
            )
        
        response = supabase.table("vehicles").update(update_data).eq("id", vehicle_id).execute()
        
        # Add default passenger_capacity if missing
        if "passenger_capacity" not in response.data[0] or response.data[0]["passenger_capacity"] is None:
            response.data[0]["passenger_capacity"] = 0
        
        return response.data[0]
    except HTTPException:
        raise
    except ValueError as e:
        # Handle validation errors from Pydantic
        raise create_vehicle_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(e),
            error_type="validation_error"
        )
    except Exception as e:
        raise create_vehicle_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Error updating vehicle: {str(e)}",
            error_type="server_error",
            details={"vehicle_id": vehicle_id}
        )

@router.delete("/{vehicle_id}")
async def delete_vehicle(
    vehicle_id: str,
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Delete a vehicle.
    """
    try:
        # Check if vehicle exists
        existing = supabase.table("vehicles").select("*").eq("id", vehicle_id).execute()
        
        if not existing.data:
            raise create_vehicle_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Vehicle not found",
                error_type="not_found",
                details={"vehicle_id": vehicle_id}
            )
        
        # Check if vehicle has operations
        operations = supabase.table("operations").select("id").eq("vehicle_id", vehicle_id).limit(1).execute()
        
        if operations.data:
            # Instead of deleting, mark as inactive
            response = supabase.table("vehicles").update({"status": "inactive"}).eq("id", vehicle_id).execute()
            return {
                "status": "success",
                "message": "Vehicle marked as inactive (has operations)",
                "vehicle_id": vehicle_id
            }
        
        # If no operations, delete the vehicle
        response = supabase.table("vehicles").delete().eq("id", vehicle_id).execute()
        
        return {
            "status": "success",
            "message": "Vehicle deleted successfully",
            "vehicle_id": vehicle_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise create_vehicle_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Error deleting vehicle: {str(e)}",
            error_type="server_error",
            details={"vehicle_id": vehicle_id}
        ) 