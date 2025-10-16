from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from typing import List, Any, Optional, Dict
from datetime import date, timedelta
import json
import logging

from app.models import get_db
from app.models.models import Driver, Trip, Deficit, DailySummary
from app.core.security import get_current_user, check_admin_role
from app.core.cache import cached, invalidate_cache
from app.schemas.driver import (
    DriverCreate,
    DriverUpdate,
    DriverResponse,
    DriverRating
)
from app.schemas.user import ErrorResponse
from app.core.utils import DateTimeEncoder
from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)

router = APIRouter()

def create_driver_error(status_code: int, message: str, error_type: str, details: Dict = None) -> HTTPException:
    """Create standardized driver API error response"""
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

@router.get("/", response_model=List[DriverResponse])
@cached(ttl=300, key_prefix="drivers")  # Cache for 5 minutes
async def get_drivers(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None
) -> Any:
    """
    Retrieve all drivers with optional status filtering.
    """
    try:
        query = db.query(Driver).order_by(Driver.name)

        if status:
            query = query.filter(Driver.status == status)

        drivers = query.offset(skip).limit(limit).all()

        return [DriverResponse.from_orm(driver) for driver in drivers]

    except Exception as e:
        logger.error(f"Failed to retrieve drivers: {str(e)}")
        raise create_driver_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve drivers. Please try again later.",
            error_type="drivers_retrieval_failed",
            details={"error": str(e)}
        )

@router.post("/", response_model=DriverResponse)
@invalidate_cache("drivers:*")  # Clear all driver caches when creating
async def create_driver(
    driver_in: DriverCreate,
    current_user = Depends(check_admin_role),
    db: Session = Depends(get_db)
) -> Any:
    """
    Create new driver.
    """
    try:
        # Check if license_no already exists
        existing_driver = db.query(Driver).filter(Driver.license_no == driver_in.license_no).first()

        if existing_driver:
            raise create_driver_error(
                status_code=status.HTTP_409_CONFLICT,
                message="A driver with this license number already exists. Please use a different license number.",
                error_type="driver_license_exists",
                details={"license_no": driver_in.license_no}
            )

        # Create new driver
        new_driver = Driver(
            name=driver_in.name,
            license_no=driver_in.license_no,
            phone=driver_in.phone,
            status=driver_in.status,
            experience=driver_in.experience,
            rating=driver_in.rating
        )

        db.add(new_driver)
        db.commit()
        db.refresh(new_driver)

        return DriverResponse.from_orm(new_driver)

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create driver: {str(e)}")
        raise create_driver_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create driver. Please try again later.",
            error_type="driver_creation_failed",
            details={"error": str(e)}
        )

@router.get("/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get driver by ID.
    """
    try:
        driver = db.query(Driver).filter(Driver.id == driver_id).first()

        if not driver:
            raise create_driver_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Driver not found. Please check the driver ID and try again.",
                error_type="driver_not_found",
                details={"driver_id": driver_id}
            )

        return DriverResponse.from_orm(driver)

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to retrieve driver {driver_id}: {str(e)}")
        raise create_driver_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve driver. Please try again later.",
            error_type="driver_retrieval_failed",
            details={"driver_id": driver_id, "error": str(e)}
        )

@router.put("/{driver_id}", response_model=DriverResponse)
@invalidate_cache("drivers:*")  # Clear all driver caches when updating
async def update_driver(
    driver_id: str,
    driver_in: DriverUpdate,
    current_user = Depends(check_admin_role),
    db: Session = Depends(get_db)
) -> Any:
    """
    Update a driver.
    """
    try:
        # Check if driver exists
        driver = db.query(Driver).filter(Driver.id == driver_id).first()

        if not driver:
            raise create_driver_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Driver not found. Please check the driver ID and try again.",
                error_type="driver_not_found",
                details={"driver_id": driver_id}
            )

        # Filter out None values and check for license_no conflicts if updating
        update_data = {k: v for k, v in driver_in.dict().items() if v is not None}

        if not update_data:
            raise create_driver_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="No fields to update. Please provide at least one field to update.",
                error_type="no_update_data",
                details={"driver_id": driver_id}
            )

        # Check for license number conflicts if updating license_no
        if "license_no" in update_data and update_data["license_no"] != driver.license_no:
            existing_license = db.query(Driver).filter(
                Driver.license_no == update_data["license_no"],
                Driver.id != driver_id
            ).first()

            if existing_license:
                raise create_driver_error(
                    status_code=status.HTTP_409_CONFLICT,
                    message="A driver with this license number already exists. Please use a different license number.",
                    error_type="driver_license_exists",
                    details={"license_no": update_data["license_no"]}
                )

        # Update driver fields
        for field, value in update_data.items():
            if hasattr(driver, field):
                setattr(driver, field, value)

        driver.updated_at = func.now()

        db.commit()
        db.refresh(driver)

        return DriverResponse.from_orm(driver)

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update driver {driver_id}: {str(e)}")
        raise create_driver_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update driver. Please try again later.",
            error_type="driver_update_failed",
            details={"driver_id": driver_id, "error": str(e)}
        )

@router.delete("/{driver_id}")
@invalidate_cache("drivers:*")  # Clear all driver caches when deleting
async def delete_driver(
    driver_id: str,
    current_user = Depends(check_admin_role),
    db: Session = Depends(get_db)
) -> Any:
    """
    Delete a driver.
    If driver has related records (trips, deficits), mark as inactive instead of deleting.
    """
    try:
        # Check if driver exists
        driver = db.query(Driver).filter(Driver.id == driver_id).first()

        if not driver:
            raise create_driver_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Driver not found. Please check the driver ID and try again.",
                error_type="driver_not_found",
                details={"driver_id": driver_id}
            )

        # Check if driver has related trips
        trips_count = db.query(Trip).filter(Trip.driver_id == driver_id).count()

        # Check if driver has related deficits
        deficits_count = db.query(Deficit).filter(Deficit.driver == driver_id).count()

        # Check if driver has related daily summaries
        daily_summaries_count = db.query(DailySummary).filter(DailySummary.driver_id == driver_id).count()

        has_related_records = trips_count > 0 or deficits_count > 0 or daily_summaries_count > 0

        if has_related_records:
            # Instead of deleting, mark as inactive
            driver.status = "inactive"
            driver.updated_at = func.now()

            db.commit()

            return {
                "message": "Driver marked as inactive (has related records)",
                "driver_id": str(driver_id),
                "status": "inactive",
                "related_records": {
                    "trips": trips_count,
                    "deficits": deficits_count,
                    "daily_summaries": daily_summaries_count
                }
            }

        # If no related records, delete the driver
        db.delete(driver)
        db.commit()

        return {
            "message": "Driver deleted successfully",
            "driver_id": str(driver_id)
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete driver {driver_id}: {str(e)}")
        raise create_driver_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to delete driver. Please try again later.",
            error_type="driver_deletion_failed",
            details={"driver_id": driver_id, "error": str(e)}
        )

@router.get("/{driver_id}/performance", response_model=dict)
@cached(ttl=300, key_prefix="drivers")  # Cache for 5 minutes - individual driver performance
async def get_driver_performance(
    driver_id: str,
    days: int = 30,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get driver performance stats.
    """
    try:
        # Check if driver exists
        driver = db.query(Driver).filter(Driver.id == driver_id).first()

        if not driver:
            raise create_driver_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Driver not found. Please check the driver ID and try again.",
                error_type="driver_not_found",
                details={"driver_id": driver_id}
            )

        # Calculate date range
        today = date.today()
        start_date = today - timedelta(days=days)

        # Get trips data (since operations table doesn't exist in our schema, we'll use trips)
        trips = db.query(Trip).filter(
            Trip.driver_id == driver_id,
            Trip.collection_time >= start_date,
            Trip.collection_time <= today
        ).all()

        # Calculate performance metrics
        total_trips = len(trips)
        total_collections = sum(trip.collected_amount for trip in trips)
        total_expenses = sum(trip.repair_expense or 0 for trip in trips)

        # Get unique vehicles used
        vehicles_used = set(trip.vehicle_id for trip in trips)

        # Calculate performance metrics
        metrics = {
            "driver_id": str(driver_id),
            "driver_name": driver.name,
            "days_worked": total_trips,  # Using trips as proxy for days worked
            "total_collections": float(total_collections),
            "average_daily_collection": float(total_collections / total_trips) if total_trips > 0 else 0.0,
            "total_expenses": float(total_expenses),
            "net_collection": float(total_collections - total_expenses),
            "vehicles_used": len(vehicles_used),
            "performance_period": f"{start_date.isoformat()} to {today.isoformat()}"
        }

        return metrics

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to get driver performance for {driver_id}: {str(e)}")
        raise create_driver_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to retrieve driver performance. Please try again later.",
            error_type="driver_performance_failed",
            details={"driver_id": driver_id, "error": str(e)}
        )

@router.put("/{driver_id}/rate", response_model=DriverResponse)
@invalidate_cache("drivers:*")  # Clear all driver caches when rating
async def rate_driver(
    driver_id: str,
    rating: DriverRating,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Rate a driver.
    """
    try:
        # Check if driver exists
        driver = db.query(Driver).filter(Driver.id == driver_id).first()

        if not driver:
            raise create_driver_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Driver not found. Please check the driver ID and try again.",
                error_type="driver_not_found",
                details={"driver_id": driver_id}
            )

        # Validate rating value
        if rating.rating < 1 or rating.rating > 5:
            raise create_driver_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Rating must be between 1 and 5.",
                error_type="invalid_rating",
                details={"rating": rating.rating}
            )

        # Update driver's rating
        driver.rating = rating.rating
        driver.updated_at = func.now()

        db.commit()
        db.refresh(driver)

        return DriverResponse.from_orm(driver)

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to rate driver {driver_id}: {str(e)}")
        raise create_driver_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update driver rating. Please try again later.",
            error_type="driver_rating_failed",
            details={"driver_id": driver_id, "error": str(e)}
        ) 