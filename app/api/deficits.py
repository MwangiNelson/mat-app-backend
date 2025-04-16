from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from app.core.db import supabase
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

router = APIRouter(tags=["deficits"])


@router.post("/", response_model=Deficit, status_code=201)
async def create_deficit(
    deficit: DeficitCreate,
    current_user = Depends(get_current_active_user)
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
        driver_response = supabase.table("drivers").select("id, name").eq("id", deficit.driver).execute()
        
        if not driver_response.data:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        # Verify vehicle exists
        vehicle_response = supabase.table("vehicles").select("id, reg_no").eq("id", deficit.vehicle).execute()
        
        if not vehicle_response.data:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        
        # Create deficit record
        deficit_data = {
            "driver": str(deficit.driver),
            "vehicle": str(deficit.vehicle),
            "amount": deficit.amount,
            "deficit_type": deficit.deficit_type
        }
        
        result = supabase.table("deficits").insert(deficit_data).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create deficit record")
        
        new_deficit = result.data[0]
        
        return {
            "id": new_deficit["id"],
            "created_at": new_deficit["created_at"],
            "driver": new_deficit["driver"],
            "vehicle": new_deficit["vehicle"],
            "amount": new_deficit["amount"],
            "deficit_type": new_deficit["deficit_type"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating deficit: {str(e)}")


@router.get("/", response_model=DeficitDetailedSummary)
async def get_deficits(
    driver_id: Optional[UUID] = Query(None, description="Filter by driver ID"),
    vehicle_id: Optional[UUID] = Query(None, description="Filter by vehicle ID"),
    current_user = Depends(get_current_active_user)
):
    """
    Get a list of all deficits with totals and breakdowns.
    
    Optionally filter by driver_id and/or vehicle_id.
    
    Returns:
        DeficitDetailedSummary with overall totals, breakdowns by driver and vehicle,
        and the list of deficit records.
    """
    try:
        # Set up query for deficits
        query = supabase.table("deficits").select("*")
        
        # Apply filters if provided
        if driver_id:
            query = query.eq("driver", str(driver_id))
            
        if vehicle_id:
            query = query.eq("vehicle", str(vehicle_id))
        
        # Execute query
        deficits_result = query.order("created_at", desc=True).execute()
        
        # Join with driver and vehicle information
        deficits = []
        total_deficit = 0
        total_repaid = 0
        
        for row in deficits_result.data:
            # Get driver info for each deficit
            driver_info = supabase.table("drivers").select("name").eq("id", row["driver"]).execute()
            driver_name = driver_info.data[0]["name"] if driver_info.data else None
            
            # Get vehicle info for each deficit
            vehicle_info = supabase.table("vehicles").select("reg_no").eq("id", row["vehicle"]).execute()
            vehicle_registration = vehicle_info.data[0]["reg_no"] if vehicle_info.data else None
            
            deficit = {
                "id": row["id"],
                "created_at": row["created_at"],
                "driver": row["driver"],
                "vehicle": row["vehicle"],
                "amount": row["amount"],
                "deficit_type": row["deficit_type"]
            }
            deficits.append(deficit)
            
            if row["deficit_type"] == "deficit":
                total_deficit += row["amount"]
            elif row["deficit_type"] == "repayment":
                total_repaid += row["amount"]
        
        # Calculate overall balance
        overall_totals = {
            "total_deficit": total_deficit,
            "total_repaid": total_repaid,
            "balance": total_deficit - total_repaid
        }
        
        # Get driver breakdowns using RPC or aggregation in code
        driver_summaries = []
        
        # Identify unique drivers
        unique_drivers = set(d["driver"] for d in deficits_result.data)
        
        for driver in unique_drivers:
            driver_deficits = [d for d in deficits_result.data if d["driver"] == driver]
            
            driver_total_deficit = sum(d["amount"] for d in driver_deficits if d["deficit_type"] == "deficit")
            driver_total_repaid = sum(d["amount"] for d in driver_deficits if d["deficit_type"] == "repayment")
            driver_balance = driver_total_deficit - driver_total_repaid
            
            # Get driver name
            driver_info = supabase.table("drivers").select("name").eq("id", driver).execute()
            driver_name = driver_info.data[0]["name"] if driver_info.data else None
            
            driver_summaries.append({
                "driver_id": driver,
                "driver_name": driver_name,
                "total_deficit": driver_total_deficit,
                "total_repaid": driver_total_repaid,
                "balance": driver_balance
            })
        
        # Get vehicle breakdowns
        vehicle_summaries = []
        
        # Identify unique vehicles
        unique_vehicles = set(d["vehicle"] for d in deficits_result.data)
        
        for vehicle in unique_vehicles:
            vehicle_deficits = [d for d in deficits_result.data if d["vehicle"] == vehicle]
            
            vehicle_total_deficit = sum(d["amount"] for d in vehicle_deficits if d["deficit_type"] == "deficit")
            vehicle_total_repaid = sum(d["amount"] for d in vehicle_deficits if d["deficit_type"] == "repayment")
            vehicle_balance = vehicle_total_deficit - vehicle_total_repaid
            
            # Get vehicle reg_no
            vehicle_info = supabase.table("vehicles").select("reg_no").eq("id", vehicle).execute()
            vehicle_registration = vehicle_info.data[0]["reg_no"] if vehicle_info.data else None
            
            vehicle_summaries.append({
                "vehicle_id": vehicle,
                "vehicle_registration": vehicle_registration,
                "total_deficit": vehicle_total_deficit,
                "total_repaid": vehicle_total_repaid,
                "balance": vehicle_balance
            })
        
        return {
            "overall": overall_totals,
            "by_driver": driver_summaries,
            "by_vehicle": vehicle_summaries,
            "deficits": deficits
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching deficits: {str(e)}")


@router.get("/{deficit_id}", response_model=Deficit)
async def get_deficit(
    deficit_id: UUID,
    current_user = Depends(get_current_active_user)
):
    """
    Get a specific deficit by ID.
    """
    try:
        result = supabase.table("deficits").select("*").eq("id", str(deficit_id)).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Deficit not found")
        
        deficit = result.data[0]
        
        return {
            "id": deficit["id"],
            "created_at": deficit["created_at"],
            "driver": deficit["driver"],
            "vehicle": deficit["vehicle"],
            "amount": deficit["amount"],
            "deficit_type": deficit["deficit_type"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching deficit: {str(e)}")


@router.delete("/{deficit_id}", status_code=204)
async def delete_deficit(
    deficit_id: UUID,
    current_user = Depends(get_current_active_user)
):
    """
    Delete a deficit record.
    """
    try:
        # Check if deficit exists
        result = supabase.table("deficits").select("*").eq("id", str(deficit_id)).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Deficit not found")
        
        # Delete the deficit
        supabase.table("deficits").delete().eq("id", str(deficit_id)).execute()
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting deficit: {str(e)}") 