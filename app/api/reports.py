from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Any, Optional
from datetime import datetime, date, timedelta

from app.core.db import supabase
from app.core.security import get_current_active_user, check_admin_role
from app.schemas.reports import DailySummaryResponse, DailySummaryDetail
from app.core.utils import DateTimeEncoder
import json

router = APIRouter()

@router.get("/daily/{vehicle_id}/{date}", response_model=DailySummaryDetail)
async def get_daily_summary(
    vehicle_id: str, 
    date_str: str,
    regenerate: bool = False,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Get or generate daily summary for a specific vehicle and date.
    
    Date format: YYYY-MM-DD
    Set regenerate=true to force recalculation of the summary.
    """
    try:
        # Parse date
        try:
            summary_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Check if vehicle exists
        vehicle_check = supabase.table("vehicles").select("registration").eq("id", vehicle_id).execute()
        
        if not vehicle_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
        
        vehicle_registration = vehicle_check.data[0]["registration"]
        
        if regenerate:
            # Generate new summary
            response = supabase.rpc('generate_daily_summary', {
                'vehicle_id_param': vehicle_id,
                'date_param': summary_date.isoformat()
            }).execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No trips found for this vehicle on the specified date"
                )
        else:
            # Check if summary exists
            response = supabase.table("daily_summaries").select("*").eq("vehicle_id", vehicle_id).eq("date", summary_date.isoformat()).execute()
            
            if not response.data:
                # Generate if it doesn't exist
                response = supabase.rpc('generate_daily_summary', {
                    'vehicle_id_param': vehicle_id,
                    'date_param': summary_date.isoformat()
                }).execute()
                
                if not response.data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="No trips found for this vehicle on the specified date"
                    )
        
        summary = response.data[0]
        
        # Get driver name if driver_id exists
        driver_name = None
        if summary["driver_id"]:
            driver_response = supabase.table("drivers").select("full_name").eq("id", summary["driver_id"]).execute()
            if driver_response.data:
                driver_name = driver_response.data[0]["full_name"]
        
        # Add additional details
        detail_summary = {**summary, "vehicle_registration": vehicle_registration, "driver_name": driver_name}
        
        return detail_summary
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting daily summary: {str(e)}"
        )

@router.get("/daily", response_model=List[DailySummaryResponse])
async def get_daily_summaries(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    driver_id: Optional[str] = None,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Get daily summaries with optional filtering.
    
    Date format: YYYY-MM-DD
    If no dates are provided, returns summaries for the last 7 days.
    """
    try:
        query = supabase.table("daily_summaries").select("*")
        
        # Default to last 7 days if no dates provided
        if not start_date and not end_date:
            end_date = datetime.now().date().isoformat()
            start_date = (datetime.now().date() - timedelta(days=7)).isoformat()
        
        if start_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                query = query.gte("date", start.isoformat())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD"
                )
        
        if end_date:
            try:
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
                query = query.lte("date", end.isoformat())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD"
                )
        
        if vehicle_id:
            query = query.eq("vehicle_id", vehicle_id)
        
        if driver_id:
            query = query.eq("driver_id", driver_id)
        
        response = query.order("date", desc=True).execute()
        
        return response.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching daily summaries: {str(e)}"
        ) 