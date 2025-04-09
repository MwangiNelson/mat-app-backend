from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Any, Optional
from datetime import datetime

from app.core.db import supabase
from app.core.security import get_current_active_user, check_admin_role
from app.schemas.routes import RouteCreate, RouteUpdate, RouteResponse
from app.core.utils import DateTimeEncoder
import json

router = APIRouter()

@router.post("/", response_model=RouteResponse)
async def create_route(route_data: RouteCreate, current_user = Depends(check_admin_role)) -> Any:
    """
    Create a new route (admin only).
    """
    try:
        response = supabase.table("routes").insert(route_data.dict()).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create route"
            )
        
        return response.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating route: {str(e)}"
        )

@router.get("/", response_model=List[RouteResponse])
async def get_routes(
    status: Optional[str] = None,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Get all routes, with optional filtering by status.
    """
    try:
        query = supabase.table("routes").select("*")
        
        if status:
            query = query.eq("status", status)
        
        response = query.order("name").execute()
        
        return response.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching routes: {str(e)}"
        )

@router.get("/{route_id}", response_model=RouteResponse)
async def get_route(route_id: str, current_user = Depends(get_current_active_user)) -> Any:
    """
    Get a specific route by ID.
    """
    try:
        response = supabase.table("routes").select("*").eq("id", route_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Route not found"
            )
        
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching route: {str(e)}"
        )

@router.put("/{route_id}", response_model=RouteResponse)
async def update_route(
    route_id: str, 
    route_update: RouteUpdate, 
    current_user = Depends(check_admin_role)
) -> Any:
    """
    Update a route (admin only).
    """
    try:
        # Check if route exists
        check_response = supabase.table("routes").select("*").eq("id", route_id).execute()
        
        if not check_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Route not found"
            )
        
        # Filter out None values
        update_data = {k: v for k, v in route_update.dict().items() if v is not None}
        
        if not update_data:
            return check_response.data[0]
        
        # Update route
        response = supabase.table("routes").update(update_data).eq("id", route_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update route"
            )
        
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating route: {str(e)}"
        )

@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route(route_id: str, current_user = Depends(check_admin_role)) -> None:
    """
    Delete a route (admin only).
    """
    try:
        # Check if route exists
        check_response = supabase.table("routes").select("*").eq("id", route_id).execute()
        
        if not check_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Route not found"
            )
        
        # Check if route is in use by vehicles
        vehicle_check = supabase.table("vehicles").select("id").eq("route_id", route_id).execute()
        
        if vehicle_check.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete route that is assigned to vehicles"
            )
        
        # Check if route is used in trips
        trip_check = supabase.table("trips").select("id").eq("route_id", route_id).execute()
        
        if trip_check.data:
            # Instead of deleting, mark as inactive
            supabase.table("routes").update({"status": "inactive"}).eq("id", route_id).execute()
            return
        
        # Delete route if no dependencies
        supabase.table("routes").delete().eq("id", route_id).execute()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting route: {str(e)}"
        ) 