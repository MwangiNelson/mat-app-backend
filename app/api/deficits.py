from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
import json
import logging

from app.models import get_db
from app.models.models import Deficit as DeficitModel, Driver, Vehicle
from app.core.security import get_current_active_user
from app.schemas.deficits import (
    DeficitCreate,
    Deficit,
    DeficitSummary,
    DeficitDetailedSummary,
    DeficitTotals,
    DriverDeficitSummary,
    VehicleDeficitSummary
)
from app.schemas.user import ErrorResponse
from app.core.utils import DateTimeEncoder
from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)

router = APIRouter(tags=["deficits"])

def create_deficit_error(status_code: int, message: str, error_type: str, details: Dict = None) -> HTTPException:
    """Create standardized deficit API error response"""
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


@router.post("/", response_model=Deficit, status_code=201)
async def create_deficit(
    deficit: DeficitCreate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new deficit or repayment record.

    Args:
        deficit: DeficitCreate schema with driver_id, vehicle_id, amount, and type

    Returns:
        The created deficit record
    """
    try:
        # Verify driver exists
        driver = db.query(Driver).filter(Driver.id == deficit.driver).first()

        if not driver:
            raise create_deficit_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Driver not found. Please check the driver ID and try again.",
                error_type="driver_not_found",
                details={"driver_id": str(deficit.driver)}
            )

        # Verify vehicle exists
        vehicle = db.query(Vehicle).filter(Vehicle.id == deficit.vehicle).first()

        if not vehicle:
            raise create_deficit_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Vehicle not found. Please check the vehicle ID and try again.",
                error_type="vehicle_not_found",
                details={"vehicle_id": str(deficit.vehicle)}
            )

        # Validate amount
        if deficit.amount <= 0:
            raise create_deficit_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Deficit amount must be greater than zero.",
                error_type="invalid_amount",
                details={"amount": deficit.amount}
            )

        # Create deficit record
        new_deficit = DeficitModel(
            driver=deficit.driver,
            vehicle=deficit.vehicle,
            amount=deficit.amount,
            deficit_type=deficit.deficit_type
        )

        db.add(new_deficit)
        db.commit()
        db.refresh(new_deficit)

        return Deficit.from_orm(new_deficit)

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create deficit: {str(e)}")
        raise create_deficit_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create deficit record. Please try again later.",
            error_type="deficit_creation_failed",
            details={"error": str(e)}
        )


@router.get("/", response_model=DeficitDetailedSummary)
async def get_deficits(
    driver_id: Optional[UUID] = Query(None, description="Filter by driver ID"),
    vehicle_id: Optional[UUID] = Query(None, description="Filter by vehicle ID"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a list of all deficits with totals and breakdowns.

    Optionally filter by driver_id and/or vehicle_id.

    Returns:
        DeficitDetailedSummary with overall totals, breakdowns by driver and vehicle,
        and the list of deficit records.
    """
    try:
        # Build base query with joins
        query = db.query(DeficitModel).join(Driver, DeficitModel.driver == Driver.id).join(Vehicle, DeficitModel.vehicle == Vehicle.id)

        # Apply filters if provided
        if driver_id:
            query = query.filter(DeficitModel.driver == driver_id)
        if vehicle_id:
            query = query.filter(DeficitModel.vehicle == vehicle_id)

        # Get all deficits with driver and vehicle info
        deficits_data = query.order_by(DeficitModel.created_at.desc()).all()

        # Convert to response format
        deficits = []
        for deficit in deficits_data:
            deficits.append(Deficit.from_orm(deficit))

        # Calculate overall totals
        total_deficit = sum(d.amount for d in deficits_data if d.deficit_type == "deficit")
        total_repaid = sum(d.amount for d in deficits_data if d.deficit_type == "repayment")
        overall_totals = DeficitTotals(
            total_deficit=total_deficit,
            total_repaid=total_repaid,
            balance=total_deficit - total_repaid
        )

        # Get driver breakdowns
        driver_summaries = []
        if deficits_data:
            # Group deficits by driver
            driver_groups = {}
            for deficit in deficits_data:
                driver_id = deficit.driver
                if driver_id not in driver_groups:
                    driver_groups[driver_id] = {
                        'driver': deficit.driver_rel,
                        'deficits': []
                    }
                driver_groups[driver_id]['deficits'].append(deficit)

            for driver_data in driver_groups.values():
                driver = driver_data['driver']
                driver_deficits = driver_data['deficits']

                driver_total_deficit = sum(d.amount for d in driver_deficits if d.deficit_type == "deficit")
                driver_total_repaid = sum(d.amount for d in driver_deficits if d.deficit_type == "repayment")

                driver_summaries.append(DriverDeficitSummary(
                    driver_id=driver.id,
                    driver_name=driver.name,
                    total_deficit=driver_total_deficit,
                    total_repaid=driver_total_repaid,
                    balance=driver_total_deficit - driver_total_repaid
                ))

        # Get vehicle breakdowns
        vehicle_summaries = []
        if deficits_data:
            # Group deficits by vehicle
            vehicle_groups = {}
            for deficit in deficits_data:
                vehicle_id = deficit.vehicle
                if vehicle_id not in vehicle_groups:
                    vehicle_groups[vehicle_id] = {
                        'vehicle': deficit.vehicle_rel,
                        'deficits': []
                    }
                vehicle_groups[vehicle_id]['deficits'].append(deficit)

            for vehicle_data in vehicle_groups.values():
                vehicle = vehicle_data['vehicle']
                vehicle_deficits = vehicle_data['deficits']

                vehicle_total_deficit = sum(d.amount for d in vehicle_deficits if d.deficit_type == "deficit")
                vehicle_total_repaid = sum(d.amount for d in vehicle_deficits if d.deficit_type == "repayment")

                vehicle_summaries.append(VehicleDeficitSummary(
                    vehicle_id=vehicle.id,
                    vehicle_registration=vehicle.reg_no,
                    total_deficit=vehicle_total_deficit,
                    total_repaid=vehicle_total_repaid,
                    balance=vehicle_total_deficit - vehicle_total_repaid
                ))

        return DeficitDetailedSummary(
            overall=overall_totals,
            by_driver=driver_summaries,
            by_vehicle=vehicle_summaries,
            deficits=deficits
        )

    except Exception as e:
        logger.error(f"Failed to fetch deficits: {str(e)}")
        raise create_deficit_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to fetch deficit records. Please try again later.",
            error_type="deficit_fetch_failed",
            details={"error": str(e)}
        )


@router.get("/{deficit_id}", response_model=Deficit)
async def get_deficit(
    deficit_id: UUID,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific deficit by ID.
    """
    try:
        deficit = db.query(DeficitModel).filter(DeficitModel.id == deficit_id).first()

        if not deficit:
            raise create_deficit_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Deficit not found. Please check the deficit ID and try again.",
                error_type="deficit_not_found",
                details={"deficit_id": str(deficit_id)}
            )

        return Deficit.from_orm(deficit)

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to fetch deficit {deficit_id}: {str(e)}")
        raise create_deficit_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to fetch deficit record. Please try again later.",
            error_type="deficit_fetch_failed",
            details={"deficit_id": str(deficit_id), "error": str(e)}
        )


@router.delete("/{deficit_id}", status_code=204)
async def delete_deficit(
    deficit_id: UUID,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a deficit record.
    """
    try:
        # Check if deficit exists
        deficit = db.query(DeficitModel).filter(DeficitModel.id == deficit_id).first()

        if not deficit:
            raise create_deficit_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Deficit not found. Please check the deficit ID and try again.",
                error_type="deficit_not_found",
                details={"deficit_id": str(deficit_id)}
            )

        # Delete the deficit
        db.delete(deficit)
        db.commit()

        return None

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete deficit {deficit_id}: {str(e)}")
        raise create_deficit_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to delete deficit record. Please try again later.",
            error_type="deficit_deletion_failed",
            details={"deficit_id": str(deficit_id), "error": str(e)}
        ) 