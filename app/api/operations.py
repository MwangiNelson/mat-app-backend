from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Any, Optional, Dict
from datetime import date, datetime, timedelta

from app.core.db import supabase
from app.core.security import get_current_user, get_current_active_user
from app.schemas.operation import (
    OperationCreate,
    OperationUpdate,
    OperationResponse,
    DateRangeParams,
    OperationSummary,
    DashboardStats
)
from app.schemas.trips import TripResponse
from app.core.utils import DateTimeEncoder
import json

router = APIRouter()

@router.get("/", response_model=List[OperationResponse])
async def get_operations(
    current_user = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    vehicle_id: Optional[str] = None,
    driver_id: Optional[str] = None
) -> Any:
    """
    Retrieve operations with optional filtering.
    """
    query = supabase.table("operations").select("*").order("date", desc=True).range(skip, skip + limit - 1)
    
    if start_date:
        query = query.gte("date", start_date.isoformat())
    
    if end_date:
        query = query.lte("date", end_date.isoformat())
    
    if vehicle_id:
        query = query.eq("vehicle_id", vehicle_id)
    
    if driver_id:
        query = query.eq("driver_id", driver_id)
    
    operation_data = query.execute()
    
    # If we have operations, enrich them with vehicle and driver info
    result = []
    for op in operation_data.data:
        # Fetch vehicle and driver info to add registration number and driver name
        if vehicle_id:
            vehicle = {"reg_no": None}  # Already know vehicle_id, avoid additional query
        else:
            vehicle_response = supabase.table("vehicles").select("reg_no").eq("id", op["vehicle_id"]).execute()
            vehicle = vehicle_response.data[0] if vehicle_response.data else {"reg_no": None}
        
        if driver_id:
            driver = {"name": None}  # Already know driver_id, avoid additional query
        else:
            driver_response = supabase.table("drivers").select("name").eq("id", op["driver_id"]).execute()
            driver = driver_response.data[0] if driver_response.data else {"name": None}
        
        # Combine operation with vehicle and driver info
        enriched_op = {
            **op,
            "vehicle_reg_no": vehicle["reg_no"],
            "driver_name": driver["name"]
        }
        result.append(enriched_op)
    
    return result

@router.post("/", response_model=OperationResponse)
async def create_operation(
    operation_in: OperationCreate,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Create new operation record.
    """
    # Validate vehicle exists
    vehicle = supabase.table("vehicles").select("reg_no").eq("id", operation_in.vehicle_id).execute()
    if not vehicle.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )
    
    # Validate driver exists
    driver = supabase.table("drivers").select("name").eq("id", operation_in.driver_id).execute()
    if not driver.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver not found",
        )
    
    # Check if operation already exists for this vehicle and date
    existing = (
        supabase.table("operations")
        .select("*")
        .eq("vehicle_id", operation_in.vehicle_id)
        .eq("date", operation_in.date.isoformat())
        .execute()
    )
    
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operation already exists for this vehicle and date",
        )
    
    # Create operation with current user as created_by
    operation_data = {
        **operation_in.dict(),
        "created_by": current_user.user_id
    }
    
    response = supabase.table("operations").insert(operation_data).execute()
    
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create operation",
        )
    
    # Enrich response with vehicle and driver info
    enriched_op = {
        **response.data[0],
        "vehicle_reg_no": vehicle.data[0]["reg_no"],
        "driver_name": driver.data[0]["name"]
    }
    
    return enriched_op

@router.get("/{operation_id}", response_model=OperationResponse)
async def get_operation(
    operation_id: str,
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get operation by ID.
    """
    operation = supabase.table("operations").select("*").eq("id", operation_id).execute()
    
    if not operation.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operation not found",
        )
    
    op = operation.data[0]
    
    # Fetch vehicle and driver info
    vehicle = supabase.table("vehicles").select("reg_no").eq("id", op["vehicle_id"]).execute()
    driver = supabase.table("drivers").select("name").eq("id", op["driver_id"]).execute()
    
    # Combine operation with vehicle and driver info
    enriched_op = {
        **op,
        "vehicle_reg_no": vehicle.data[0]["reg_no"] if vehicle.data else None,
        "driver_name": driver.data[0]["name"] if driver.data else None
    }
    
    return enriched_op

@router.put("/{operation_id}", response_model=OperationResponse)
async def update_operation(
    operation_id: str,
    operation_in: OperationUpdate,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Update an operation.
    """
    # Check if operation exists
    operation = supabase.table("operations").select("*").eq("id", operation_id).execute()
    
    if not operation.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operation not found",
        )
    
    # Filter out None values
    update_data = {k: v for k, v in operation_in.dict().items() if v is not None}
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    
    # Add updated_at timestamp
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    response = supabase.table("operations").update(update_data).eq("id", operation_id).execute()
    
    op = response.data[0]
    
    # Fetch vehicle and driver info
    vehicle = supabase.table("vehicles").select("reg_no").eq("id", op["vehicle_id"]).execute()
    driver = supabase.table("drivers").select("name").eq("id", op["driver_id"]).execute()
    
    # Combine operation with vehicle and driver info
    enriched_op = {
        **op,
        "vehicle_reg_no": vehicle.data[0]["reg_no"] if vehicle.data else None,
        "driver_name": driver.data[0]["name"] if driver.data else None
    }
    
    return enriched_op

@router.delete("/{operation_id}")
async def delete_operation(
    operation_id: str,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Delete an operation.
    """
    # Check if operation exists
    operation = supabase.table("operations").select("*").eq("id", operation_id).execute()
    
    if not operation.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operation not found",
        )
    
    response = supabase.table("operations").delete().eq("id", operation_id).execute()
    
    return {"message": "Operation deleted successfully"}

@router.get("/summary", response_model=List[OperationSummary])
async def get_operations_summary(
    start_date: date = Query(..., description="Start date for summary"),
    end_date: date = Query(..., description="End date for summary"),
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get summary of operations by date.
    """
    # Validate date range
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be greater than or equal to start date",
        )
    
    # Get operations within date range
    operations = (
        supabase.table("operations")
        .select("*")
        .gte("date", start_date.isoformat())
        .lte("date", end_date.isoformat())
        .execute()
    )
    
    # Group by date and calculate summaries
    summaries = {}
    for op in operations.data:
        op_date = op["date"]
        if op_date not in summaries:
            summaries[op_date] = {
                "date": op_date,
                "total_collections": 0,
                "total_expenses": 0,
                "net_income": 0,
                "vehicles_count": set()
            }
        
        # Add to totals
        collections = op["morning_collection"] + op["evening_collection"]
        expenses = op["fuel_expense"] + op["repair_expense"]
        
        summaries[op_date]["total_collections"] += collections
        summaries[op_date]["total_expenses"] += expenses
        summaries[op_date]["net_income"] = summaries[op_date]["total_collections"] - summaries[op_date]["total_expenses"]
        summaries[op_date]["vehicles_count"].add(op["vehicle_id"])
    
    # Convert to list and format for response
    result = []
    for date_str, summary in summaries.items():
        result.append({
            "date": date_str,
            "total_collections": summary["total_collections"],
            "total_expenses": summary["total_expenses"],
            "net_income": summary["net_income"],
            "vehicles_count": len(summary["vehicles_count"])
        })
    
    # Sort by date
    result.sort(key=lambda x: x["date"], reverse=True)
    
    return result

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(current_user = Depends(get_current_user)) -> Any:
    """
    Get dashboard statistics.
    """
    # Get counts for vehicles
    vehicles = supabase.table("vehicles").select("id, status").execute()
    total_vehicles = len(vehicles.data)
    active_vehicles = sum(1 for v in vehicles.data if v["status"] == "active")
    
    # Get counts for drivers
    drivers = supabase.table("drivers").select("id, status").execute()
    total_drivers = len(drivers.data)
    active_drivers = sum(1 for d in drivers.data if d["status"] == "active")
    
    # Get today's collections and expenses
    today = date.today()
    today_ops = (
        supabase.table("operations")
        .select("morning_collection, evening_collection, fuel_expense, repair_expense")
        .eq("date", today.isoformat())
        .execute()
    )
    
    today_collections = sum(op["morning_collection"] + op["evening_collection"] for op in today_ops.data) if today_ops.data else 0
    today_expenses = sum(op["fuel_expense"] + op["repair_expense"] for op in today_ops.data) if today_ops.data else 0
    
    # Get weekly collections (last 7 days)
    week_ago = today - timedelta(days=7)
    weekly_ops = (
        supabase.table("operations")
        .select("date, morning_collection, evening_collection")
        .gte("date", week_ago.isoformat())
        .lte("date", today.isoformat())
        .execute()
    )
    
    # Group weekly collections by date
    weekly_collections = {}
    for op in weekly_ops.data:
        date_str = op["date"]
        if date_str not in weekly_collections:
            weekly_collections[date_str] = 0
        weekly_collections[date_str] += op["morning_collection"] + op["evening_collection"]
    
    # Format weekly collections
    weekly_data = [{"date": date_str, "amount": amount} for date_str, amount in weekly_collections.items()]
    weekly_data.sort(key=lambda x: x["date"])
    
    # Get monthly collections (last 30 days by week)
    month_ago = today - timedelta(days=30)
    monthly_ops = (
        supabase.table("operations")
        .select("date, morning_collection, evening_collection")
        .gte("date", month_ago.isoformat())
        .lte("date", today.isoformat())
        .execute()
    )
    
    # Group monthly collections by week
    monthly_collections = {}
    for op in monthly_ops.data:
        op_date = datetime.strptime(op["date"], "%Y-%m-%d").date()
        week_number = (op_date - month_ago).days // 7
        week_label = f"Week {week_number + 1}"
        
        if week_label not in monthly_collections:
            monthly_collections[week_label] = 0
        monthly_collections[week_label] += op["morning_collection"] + op["evening_collection"]
    
    # Format monthly collections
    monthly_data = [{"week": week, "amount": amount} for week, amount in monthly_collections.items()]
    
    # Get vehicle performance
    vehicle_performance = []
    for vehicle in vehicles.data[:5]:  # Limited to top 5 for dashboard
        vehicle_ops = (
            supabase.table("operations")
            .select("morning_collection, evening_collection, fuel_expense, repair_expense")
            .eq("vehicle_id", vehicle["id"])
            .gte("date", month_ago.isoformat())
            .execute()
        )
        
        if vehicle_ops.data:
            collections = sum(op["morning_collection"] + op["evening_collection"] for op in vehicle_ops.data)
            expenses = sum(op["fuel_expense"] + op["repair_expense"] for op in vehicle_ops.data)
            
            # Get vehicle details
            vehicle_details = supabase.table("vehicles").select("reg_no").eq("id", vehicle["id"]).execute()
            reg_no = vehicle_details.data[0]["reg_no"] if vehicle_details.data else "Unknown"
            
            vehicle_performance.append({
                "vehicle_id": vehicle["id"],
                "reg_no": reg_no,
                "collections": collections,
                "expenses": expenses,
                "net_income": collections - expenses
            })
    
    # Sort by net_income
    vehicle_performance.sort(key=lambda x: x["net_income"], reverse=True)
    
    # Get driver performance
    driver_performance = []
    for driver in drivers.data[:5]:  # Limited to top 5 for dashboard
        driver_ops = (
            supabase.table("operations")
            .select("morning_collection, evening_collection")
            .eq("driver_id", driver["id"])
            .gte("date", month_ago.isoformat())
            .execute()
        )
        
        if driver_ops.data:
            collections = sum(op["morning_collection"] + op["evening_collection"] for op in driver_ops.data)
            days = len(driver_ops.data)
            
            # Get driver details
            driver_details = supabase.table("drivers").select("name").eq("id", driver["id"]).execute()
            name = driver_details.data[0]["name"] if driver_details.data else "Unknown"
            
            driver_performance.append({
                "driver_id": driver["id"],
                "name": name,
                "collections": collections,
                "days_worked": days,
                "average_daily": collections / days if days > 0 else 0
            })
    
    # Sort by collections
    driver_performance.sort(key=lambda x: x["collections"], reverse=True)
    
    return {
        "total_vehicles": total_vehicles,
        "active_vehicles": active_vehicles,
        "total_drivers": total_drivers,
        "active_drivers": active_drivers,
        "today_collections": today_collections,
        "today_expenses": today_expenses,
        "weekly_collections": weekly_data,
        "monthly_collections": monthly_data,
        "vehicle_performance": vehicle_performance,
        "driver_performance": driver_performance
    }

@router.get("/legacy", response_model=List[TripResponse])
async def get_operations_redirected(current_user = Depends(get_current_active_user)) -> Any:
    """
    Legacy endpoint - now redirects to trips API.
    Use /api/trips instead.
    """
    raise HTTPException(
        status_code=status.HTTP_301_MOVED_PERMANENTLY,
        detail="This endpoint is deprecated. Please use /api/trips instead."
    ) 