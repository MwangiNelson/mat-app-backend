from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Any, Optional, Dict
from datetime import date, timedelta, datetime
import json

from app.models import get_db
from app.models.models import Vehicle, Trip, Deficit, DailySummary
from app.core.security import get_current_user, check_admin_role
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleUpdate,
    VehicleResponse,
    parse_date_string
)
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)
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
    for date_field in ["insurance_expiry", "tlb_expiry", "speed_governor_expiry", "inspection_expiry"]:
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
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None
) -> Any:
    """
    Retrieve all vehicles with optional status filtering.
    """
    try:
        query = db.query(Vehicle).order_by(Vehicle.reg_no)

        if status:
            query = query.filter(Vehicle.status == status)

        vehicles = query.offset(skip).limit(limit).all()

        # Convert to response format with date formatting
        result = []
        for vehicle in vehicles:
            vehicle_dict = {
                "id": str(vehicle.id),
                "reg_no": vehicle.reg_no,
                "model": vehicle.model,
                "owner": vehicle.owner,
                "status": vehicle.status,
                "passenger_capacity": vehicle.passenger_capacity,
                "insurance_expiry": vehicle.insurance_expiry.isoformat() if vehicle.insurance_expiry else None,
                "tlb_expiry": vehicle.tlb_expiry.isoformat() if vehicle.tlb_expiry else None,
                "inspection_expiry": vehicle.inspection_expiry.isoformat() if vehicle.inspection_expiry else None,
                "speed_governor_expiry": vehicle.speed_governor_expiry.isoformat() if vehicle.speed_governor_expiry else None,
                "created_at": vehicle.created_at.isoformat() if vehicle.created_at else None,
                "updated_at": vehicle.updated_at.isoformat() if vehicle.updated_at else None,
            }
            # Apply date conversion formatting
            vehicle_dict = convert_iso_dates_to_client_format(vehicle_dict)
            result.append(vehicle_dict)

        return result

    except Exception as e:
        logger.error(f"Failed to retrieve vehicles: {str(e)}")
        raise create_vehicle_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve vehicles. Please try again later.",
            error_type="vehicles_retrieval_failed",
            details={"error": str(e)}
        )

@router.post("/", response_model=VehicleResponse)
async def create_vehicle(
    vehicle_in: VehicleCreate,
    current_user = Depends(check_admin_role),
    db: Session = Depends(get_db)
) -> Any:
    """
    Create new vehicle.
    """
    try:
        # Check if reg_no already exists
        existing_vehicle = db.query(Vehicle).filter(Vehicle.reg_no == vehicle_in.registration).first()

        if existing_vehicle:
            raise create_vehicle_error(
                status_code=status.HTTP_409_CONFLICT,
                message="A vehicle with this registration number already exists. Please use a different registration number.",
                error_type="vehicle_registration_exists",
                details={"registration": vehicle_in.registration}
            )

        # Parse dates from strings if needed
        insurance_expiry = vehicle_in.insurance_expiry
        if isinstance(insurance_expiry, str):
            insurance_expiry = parse_date_string(insurance_expiry)

        tlb_expiry = vehicle_in.tlb_expiry
        if isinstance(tlb_expiry, str):
            tlb_expiry = parse_date_string(tlb_expiry)

        speed_governor_expiry = vehicle_in.speed_governor_expiry
        if isinstance(speed_governor_expiry, str):
            speed_governor_expiry = parse_date_string(speed_governor_expiry)

        inspection_expiry = vehicle_in.inspection_expiry
        if isinstance(inspection_expiry, str):
            inspection_expiry = parse_date_string(inspection_expiry)

        # Create new vehicle
        new_vehicle = Vehicle(
            reg_no=vehicle_in.registration,
            model=vehicle_in.model,
            owner=vehicle_in.owner,
            status=vehicle_in.status,
            insurance_expiry=insurance_expiry,
            tlb_expiry=tlb_expiry,
            speed_governor_expiry=speed_governor_expiry,
            inspection_expiry=inspection_expiry,
            passenger_capacity=vehicle_in.passenger_capacity
        )

        db.add(new_vehicle)
        db.commit()
        db.refresh(new_vehicle)

        # Return formatted response
        vehicle_dict = {
            "id": str(new_vehicle.id),
            "reg_no": new_vehicle.reg_no,
            "model": new_vehicle.model,
            "owner": new_vehicle.owner,
            "status": new_vehicle.status,
            "passenger_capacity": new_vehicle.passenger_capacity,
            "insurance_expiry": new_vehicle.insurance_expiry.isoformat() if new_vehicle.insurance_expiry else None,
            "tlb_expiry": new_vehicle.tlb_expiry.isoformat() if new_vehicle.tlb_expiry else None,
            "inspection_expiry": new_vehicle.inspection_expiry.isoformat() if new_vehicle.inspection_expiry else None,
            "speed_governor_expiry": new_vehicle.speed_governor_expiry.isoformat() if new_vehicle.speed_governor_expiry else None,
            "created_at": new_vehicle.created_at.isoformat() if new_vehicle.created_at else None,
            "updated_at": new_vehicle.updated_at.isoformat() if new_vehicle.updated_at else None,
        }

        # Apply date conversion formatting
        vehicle_dict = convert_iso_dates_to_client_format(vehicle_dict)

        return vehicle_dict
    
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
            elif key in ['insurance_expiry', 'tlb_expiry', 'speed_governor_expiry', 'inspection_expiry'] and isinstance(value, date):
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