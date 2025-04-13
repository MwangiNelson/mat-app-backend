from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from typing import List, Any, Optional
from datetime import datetime, date, timedelta
import json
import base64
import io
from tempfile import NamedTemporaryFile
import os

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from app.core.db import supabase
from app.core.security import get_current_active_user
from app.schemas.dashboard import ReportFormat, ReportResponse

router = APIRouter()

# Initialize Jinja2 environment for template rendering
template_env = Environment(loader=FileSystemLoader("app/templates"))

def render_template_to_pdf(template_name, context_data):
    """Render an HTML template to PDF and return the PDF bytes"""
    try:
        # Get the template
        template = template_env.get_template(template_name)
        
        # Render the template with the context data
        html = template.render(**context_data)
        
        # Convert HTML to PDF
        pdf_content = io.BytesIO()
        pisa.CreatePDF(html, dest=pdf_content)
        
        # Reset file pointer to the beginning
        pdf_content.seek(0)
        
        return pdf_content
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rendering PDF: {str(e)}"
        )

def fetch_trip_data(start_date, end_date, vehicle_ids=None, driver_ids=None):
    """Fetch trip data with optional filters for multiple vehicles and drivers"""
    query = supabase.table("trips").select("*").gte("collection_time", start_date.isoformat()).lte("collection_time", end_date.isoformat())
    
    if vehicle_ids:
        if isinstance(vehicle_ids, list):
            query = query.in_("vehicle_id", vehicle_ids)
        else:
            query = query.eq("vehicle_id", vehicle_ids)
        
    if driver_ids:
        if isinstance(driver_ids, list):
            query = query.in_("driver_id", driver_ids)
        else:
            query = query.eq("driver_id", driver_ids)
    
    response = query.order("collection_time", desc=True).execute()
    return response.data

def enrich_trip_data(trips):
    """Enrich trip data with driver, vehicle and date/time info"""
    enriched_trips = []
    
    for trip in trips:
        # Get driver info
        driver_response = supabase.table("drivers").select("name").eq("id", trip["driver_id"]).execute()
        
        # Get vehicle info
        vehicle_response = supabase.table("vehicles").select("reg_no").eq("id", trip["vehicle_id"]).execute()
        
        # Get route info
        route_response = None
        if trip.get("route_id"):
            route_response = supabase.table("routes").select("name,origin,destination").eq("id", trip["route_id"]).execute()
        
        # Calculate efficiency
        efficiency = 0
        if trip.get("expected_amount") and float(trip.get("expected_amount")) > 0:
            collected = float(trip.get("collected_amount", 0) or 0)
            expected = float(trip.get("expected_amount", 0) or 0)
            efficiency = (collected / expected) * 100
        
        # Add date and time fields
        collection_date = None
        collection_time_only = None
        if trip.get("collection_time"):
            dt_obj = datetime.fromisoformat(trip["collection_time"].replace('Z', '+00:00'))
            collection_date = dt_obj.strftime("%Y-%m-%d")
            collection_time_only = dt_obj.strftime("%H:%M:%S")
        
        # Ensure expense fields exist with default values
        fuel_expense = float(trip.get("fuel_expense", 0) or 0)
        repair_expense = float(trip.get("repair_expense", 0) or 0)
        other_expense = float(trip.get("other_expense", 0) or 0)
        total_trip_expense = fuel_expense + repair_expense + other_expense
        
        # Create enriched trip object
        enriched_trip = {
            **trip,
            "driver_name": driver_response.data[0]["name"] if driver_response.data else "Unknown",
            "vehicle_registration": vehicle_response.data[0]["reg_no"] if vehicle_response.data else "Unknown",
            "route_name": route_response.data[0]["name"] if route_response and route_response.data else None,
            "origin": route_response.data[0]["origin"] if route_response and route_response.data else None,
            "destination": route_response.data[0]["destination"] if route_response and route_response.data else None,
            "efficiency": efficiency,
            "collection_date": collection_date,
            "collection_time_only": collection_time_only,
            "fuel_expense": fuel_expense,
            "repair_expense": repair_expense,
            "other_expense": other_expense,
            "total_expense": total_trip_expense
        }
        
        enriched_trips.append(enriched_trip)
    
    return enriched_trips

def process_daily_performance(trips):
    """Process trips to get daily performance data"""
    daily_data = {}
    
    for trip in trips:
        if not trip.get("collection_date"):
            continue
            
        date_str = trip["collection_date"]
        
        if date_str not in daily_data:
            daily_data[date_str] = {
                "date": date_str,
                "collections": 0,
                "expenses": 0,
                "trips": 0
            }
        
        # Add data
        daily_data[date_str]["collections"] += float(trip.get("collected_amount", 0) or 0)
        daily_data[date_str]["expenses"] += float(trip.get("total_expense", 0) or 0)
        daily_data[date_str]["trips"] += 1
    
    # Convert to sorted list
    result = [v for k, v in sorted(daily_data.items())]
    return result

@router.get("/driver/{driver_id}", response_class=StreamingResponse)
async def generate_driver_report(
    driver_id: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    format: ReportFormat = Query(ReportFormat.PDF, description="Report format (pdf or html)"),
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Generate a detailed performance report for a specific driver.
    
    Returns a formatted document containing:
    - Trip counts, collections, and efficiency metrics
    - Vehicles used by the driver
    - Daily performance breakdown
    - Complete trip logs
    """
    try:
        # Parse date strings if provided
        today = date.today()
        
        # Default to last 30 days if no dates provided
        if not start_date:
            parsed_start_date = today - timedelta(days=29)
        else:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
        
        if not end_date:
            parsed_end_date = today
        else:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Check if driver exists
        driver_response = supabase.table("drivers").select("*").eq("id", driver_id).execute()
        
        if not driver_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver not found"
            )
        
        driver = driver_response.data[0]
        
        # Get and enrich trip data
        trips = fetch_trip_data(parsed_start_date, parsed_end_date, driver_id=driver_id)
        enriched_trips = enrich_trip_data(trips)
        
        # Process driver performance metrics
        total_collections = 0
        total_expected = 0
        total_expenses = 0
        trip_count = len(enriched_trips)
        vehicles_data = {}
        routes_data = {}
        
        for trip in enriched_trips:
            # Get basic metrics
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            expected_amount = float(trip.get("expected_amount", 0) or 0)
            trip_expenses = float(trip.get("total_expense", 0) or 0)
            
            total_collections += collected_amount
            total_expected += expected_amount
            total_expenses += trip_expenses
            
            # Track vehicles
            vehicle_id = trip.get("vehicle_id")
            vehicle_reg = trip.get("vehicle_registration")
            
            if vehicle_id and vehicle_reg:
                if vehicle_id not in vehicles_data:
                    vehicles_data[vehicle_id] = {
                        "vehicle_id": vehicle_id,
                        "registration": vehicle_reg,
                        "trip_count": 0,
                        "total_collections": 0
                    }
                
                vehicles_data[vehicle_id]["trip_count"] += 1
                vehicles_data[vehicle_id]["total_collections"] += collected_amount
            
            # Track routes
            route_id = trip.get("route_id")
            route_name = trip.get("route_name")
            
            if route_id and route_name:
                if route_id not in routes_data:
                    routes_data[route_id] = {
                        "route_id": route_id,
                        "name": route_name,
                        "trip_count": 0,
                        "total_collections": 0,
                        "total_expected": 0
                    }
                
                routes_data[route_id]["trip_count"] += 1
                routes_data[route_id]["total_collections"] += collected_amount
                routes_data[route_id]["total_expected"] += expected_amount
        
        # Calculate derived metrics
        avg_per_trip = total_collections / trip_count if trip_count > 0 else 0
        collection_efficiency = (total_collections / total_expected * 100) if total_expected > 0 else 0
        net_profit = total_collections - total_expenses
        
        # Calculate route efficiency
        for route_id in routes_data:
            route = routes_data[route_id]
            if route["total_expected"] > 0:
                route["efficiency"] = (route["total_collections"] / route["total_expected"]) * 100
            else:
                route["efficiency"] = 0
        
        # Prepare driver performance data
        driver_performance = {
            **driver,
            "total_collections": total_collections,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
            "trip_count": trip_count,
            "avg_per_trip": avg_per_trip,
            "collection_efficiency": collection_efficiency,
            "vehicles_driven": list(vehicles_data.values()),
            "routes_served": list(routes_data.values())
        }
        
        # Process daily performance
        daily_data = process_daily_performance(enriched_trips)
        
        # Prepare the report context
        context = {
            "driver": driver_performance,
            "trips": enriched_trips,
            "daily_data": daily_data,
            "start_date": parsed_start_date.strftime("%Y-%m-%d"),
            "end_date": parsed_end_date.strftime("%Y-%m-%d"),
            "report_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Generate the report in the specified format
        if format == ReportFormat.HTML:
            # Render the HTML template directly
            template = template_env.get_template("driver_report.html")
            html_content = template.render(**context)
            
            # Return HTML response
            filename = f"driver_report_{driver['name'].replace(' ', '_')}_{parsed_start_date.strftime('%Y%m%d')}.html"
            
            return StreamingResponse(
                io.StringIO(html_content),
                media_type="text/html",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        else:
            # Render PDF
            pdf_content = render_template_to_pdf("driver_report.html", context)
            filename = f"driver_report_{driver['name'].replace(' ', '_')}_{parsed_start_date.strftime('%Y%m%d')}.pdf"
            
            return StreamingResponse(
                pdf_content,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating driver report: {str(e)}"
        )

@router.get("/vehicle/{vehicle_id}", response_class=StreamingResponse)
async def generate_vehicle_report(
    vehicle_id: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    format: ReportFormat = Query(ReportFormat.PDF, description="Report format (pdf or html)"),
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Generate a detailed performance report for a specific vehicle.
    
    Returns a formatted document containing:
    - Collections, expenses, and profit metrics
    - Expense breakdown by category
    - Driver performance with this vehicle
    - Daily performance breakdown
    - Complete trip logs
    """
    try:
        # Parse date strings if provided
        today = date.today()
        
        # Default to last 30 days if no dates provided
        if not start_date:
            parsed_start_date = today - timedelta(days=29)
        else:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
        
        if not end_date:
            parsed_end_date = today
        else:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Check if vehicle exists
        vehicle_response = supabase.table("vehicles").select("*").eq("id", vehicle_id).execute()
        
        if not vehicle_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
        
        vehicle_base = vehicle_response.data[0]
        
        # Get and enrich trip data
        trips = fetch_trip_data(parsed_start_date, parsed_end_date, vehicle_id=vehicle_id)
        enriched_trips = enrich_trip_data(trips)
        
        # Process vehicle performance metrics
        total_collections = 0
        fuel_expense = 0
        repair_expense = 0
        other_expense = 0
        total_expenses = 0
        trip_count = len(enriched_trips)
        active_days = set()
        drivers_data = {}
        routes_data = {}
        
        for trip in enriched_trips:
            # Get basic metrics
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            trip_fuel_expense = float(trip.get("fuel_expense", 0) or 0)
            trip_repair_expense = float(trip.get("repair_expense", 0) or 0)
            trip_other_expense = float(trip.get("other_expense", 0) or 0)
            trip_expense = trip_fuel_expense + trip_repair_expense + trip_other_expense
            
            total_collections += collected_amount
            fuel_expense += trip_fuel_expense
            repair_expense += trip_repair_expense
            other_expense += trip_other_expense
            total_expenses += trip_expense
            
            # Track active days
            if trip.get("collection_date"):
                active_days.add(trip["collection_date"])
            
            # Track drivers
            driver_id = trip.get("driver_id")
            driver_name = trip.get("driver_name")
            
            if driver_id and driver_name:
                if driver_id not in drivers_data:
                    drivers_data[driver_id] = {
                        "driver_id": driver_id,
                        "name": driver_name,
                        "trip_count": 0,
                        "total_collections": 0
                    }
                
                drivers_data[driver_id]["trip_count"] += 1
                drivers_data[driver_id]["total_collections"] += collected_amount
            
            # Track routes
            route_id = trip.get("route_id")
            route_name = trip.get("route_name")
            
            if route_id and route_name:
                if route_id not in routes_data:
                    routes_data[route_id] = {
                        "route_id": route_id,
                        "name": route_name,
                        "trip_count": 0,
                        "total_collections": 0
                    }
                
                routes_data[route_id]["trip_count"] += 1
                routes_data[route_id]["total_collections"] += collected_amount
        
        # Calculate derived metrics
        net_profit = total_collections - total_expenses
        profit_per_trip = net_profit / trip_count if trip_count > 0 else 0
        date_range_days = (parsed_end_date - parsed_start_date).days + 1
        utilization_rate = (len(active_days) / date_range_days * 100) if date_range_days > 0 else 0
        
        # Prepare vehicle performance data
        vehicle_performance = {
            **vehicle_base,
            "total_collections": total_collections,
            "fuel_expense": fuel_expense,
            "repair_expense": repair_expense,
            "other_expense": other_expense,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
            "trip_count": trip_count,
            "profit_per_trip": profit_per_trip,
            "utilization_rate": utilization_rate
        }
        
        # Process daily performance
        daily_data = process_daily_performance(enriched_trips)
        
        # Prepare the report context
        context = {
            "vehicle": vehicle_performance,
            "trips": enriched_trips,
            "daily_data": daily_data,
            "vehicle_drivers": list(drivers_data.values()),
            "vehicle_routes": list(routes_data.values()),
            "start_date": parsed_start_date.strftime("%Y-%m-%d"),
            "end_date": parsed_end_date.strftime("%Y-%m-%d"),
            "report_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Generate the report in the specified format
        if format == ReportFormat.HTML:
            # Render the HTML template directly
            template = template_env.get_template("vehicle_report.html")
            html_content = template.render(**context)
            
            # Return HTML response
            filename = f"vehicle_report_{vehicle_base['reg_no'].replace(' ', '_')}_{parsed_start_date.strftime('%Y%m%d')}.html"
            
            return StreamingResponse(
                io.StringIO(html_content),
                media_type="text/html",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        else:
            # Render PDF
            pdf_content = render_template_to_pdf("vehicle_report.html", context)
            filename = f"vehicle_report_{vehicle_base['reg_no'].replace(' ', '_')}_{parsed_start_date.strftime('%Y%m%d')}.pdf"
            
            return StreamingResponse(
                pdf_content,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating vehicle report: {str(e)}"
        )

@router.get("/combined", response_class=StreamingResponse)
async def generate_combined_report(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    vehicle_ids: Optional[str] = Query(None, description="Comma-separated list of vehicle IDs"),
    driver_ids: Optional[str] = Query(None, description="Comma-separated list of driver IDs"),
    format: ReportFormat = Query(ReportFormat.PDF, description="Report format (pdf or html)"),
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Generate a combined performance report for multiple vehicles and/or drivers.
    
    Returns a formatted document containing:
    - Overall summary metrics
    - Vehicle performance breakdown
    - Driver performance breakdown
    - Daily performance breakdown
    - Complete trip logs
    """
    try:
        # Parse vehicle and driver IDs
        vehicle_id_list = vehicle_ids.split(",") if vehicle_ids else None
        driver_id_list = driver_ids.split(",") if driver_ids else None
        
        # Parse date strings if provided
        today = date.today()
        
        # Default to last 30 days if no dates provided
        if not start_date:
            parsed_start_date = today - timedelta(days=29)
        else:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
        
        if not end_date:
            parsed_end_date = today
        else:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Fetch vehicle and driver details
        vehicles_data = {}
        if vehicle_id_list:
            vehicles_response = supabase.table("vehicles").select("*").in_("id", vehicle_id_list).execute()
            for vehicle in vehicles_response.data:
                vehicles_data[vehicle["id"]] = vehicle
        
        drivers_data = {}
        if driver_id_list:
            drivers_response = supabase.table("drivers").select("*").in_("id", driver_id_list).execute()
            for driver in drivers_response.data:
                drivers_data[driver["id"]] = driver
        
        # Get and enrich trip data
        trips = fetch_trip_data(parsed_start_date, parsed_end_date, vehicle_id_list, driver_id_list)
        enriched_trips = enrich_trip_data(trips)
        
        # Process metrics
        total_collections = 0
        total_fuel_expense = 0
        total_repair_expense = 0
        total_other_expense = 0
        total_expenses = 0
        trip_count = len(enriched_trips)
        active_days = set()
        vehicle_metrics = {}
        driver_metrics = {}
        routes_data = {}
        
        # Initialize metrics dictionaries
        for v_id in vehicles_data:
            vehicle_metrics[v_id] = {
                "vehicle_id": v_id,
                "registration": vehicles_data[v_id]["reg_no"],
                "total_collections": 0,
                "fuel_expense": 0,
                "repair_expense": 0,
                "other_expense": 0,
                "total_expenses": 0,
                "trip_count": 0,
                "active_days": set(),
                "drivers": {}
            }
        
        for d_id in drivers_data:
            driver_metrics[d_id] = {
                "driver_id": d_id,
                "name": drivers_data[d_id]["name"],
                "total_collections": 0,
                "total_expected": 0,
                "trip_count": 0,
                "vehicles": {},
                "routes": {}
            }
        
        # Process trip data
        for trip in enriched_trips:
            # Extract basic metrics
            collected_amount = float(trip.get("collected_amount", 0) or 0)
            expected_amount = float(trip.get("expected_amount", 0) or 0)
            fuel_exp = float(trip.get("fuel_expense", 0) or 0)
            repair_exp = float(trip.get("repair_expense", 0) or 0)
            other_exp = float(trip.get("other_expense", 0) or 0)
            total_trip_expense = fuel_exp + repair_exp + other_exp
            
            # Update overall totals
            total_collections += collected_amount
            total_fuel_expense += fuel_exp
            total_repair_expense += repair_exp
            total_other_expense += other_exp
            total_expenses += total_trip_expense
            
            # Track active days
            if trip.get("collection_date"):
                active_days.add(trip["collection_date"])
            
            # Update vehicle metrics
            v_id = trip.get("vehicle_id")
            if v_id and v_id in vehicle_metrics:
                vm = vehicle_metrics[v_id]
                vm["total_collections"] += collected_amount
                vm["fuel_expense"] += fuel_exp
                vm["repair_expense"] += repair_exp
                vm["other_expense"] += other_exp
                vm["total_expenses"] += total_trip_expense
                vm["trip_count"] += 1
                if trip.get("collection_date"):
                    vm["active_days"].add(trip["collection_date"])
                
                # Track drivers for this vehicle
                d_id = trip.get("driver_id")
                if d_id:
                    if d_id not in vm["drivers"]:
                        vm["drivers"][d_id] = {
                            "name": trip.get("driver_name", "Unknown"),
                            "trip_count": 0,
                            "total_collections": 0
                        }
                    vm["drivers"][d_id]["trip_count"] += 1
                    vm["drivers"][d_id]["total_collections"] += collected_amount
            
            # Update driver metrics
            d_id = trip.get("driver_id")
            if d_id and d_id in driver_metrics:
                dm = driver_metrics[d_id]
                dm["total_collections"] += collected_amount
                dm["total_expected"] += expected_amount
                dm["trip_count"] += 1
                
                # Track vehicles for this driver
                if v_id:
                    if v_id not in dm["vehicles"]:
                        dm["vehicles"][v_id] = {
                            "registration": trip.get("vehicle_registration", "Unknown"),
                            "trip_count": 0,
                            "total_collections": 0
                        }
                    dm["vehicles"][v_id]["trip_count"] += 1
                    dm["vehicles"][v_id]["total_collections"] += collected_amount
                
                # Track routes
                route_id = trip.get("route_id")
                route_name = trip.get("route_name")
                if route_id and route_name:
                    if route_id not in dm["routes"]:
                        dm["routes"][route_id] = {
                            "name": route_name,
                            "trip_count": 0,
                            "total_collections": 0,
                            "total_expected": 0
                        }
                    dm["routes"][route_id]["trip_count"] += 1
                    dm["routes"][route_id]["total_collections"] += collected_amount
                    dm["routes"][route_id]["total_expected"] += expected_amount
        
        # Calculate derived metrics
        date_range_days = (parsed_end_date - parsed_start_date).days + 1
        overall_utilization = (len(active_days) / date_range_days * 100) if date_range_days > 0 else 0
        
        # Process vehicle metrics
        vehicles_list = []
        for v_id, vm in vehicle_metrics.items():
            # Calculate utilization rate
            v_utilization = (len(vm["active_days"]) / date_range_days * 100) if date_range_days > 0 else 0
            
            # Convert drivers dict to list
            drivers_list = [{"driver_id": k, **v} for k, v in vm["drivers"].items()]
            drivers_list.sort(key=lambda x: x["trip_count"], reverse=True)
            
            # Create final vehicle metrics
            vehicle_data = {
                **vm,
                "utilization_rate": v_utilization,
                "drivers": drivers_list,
                "active_days": len(vm["active_days"])
            }
            del vehicle_data["active_days"]  # Remove the set
            vehicles_list.append(vehicle_data)
        
        # Sort vehicles by total collections
        vehicles_list.sort(key=lambda x: x["total_collections"], reverse=True)
        
        # Process driver metrics
        drivers_list = []
        for d_id, dm in driver_metrics.items():
            # Calculate efficiency
            efficiency = (dm["total_collections"] / dm["total_expected"] * 100) if dm["total_expected"] > 0 else 0
            
            # Convert vehicles dict to list
            vehicles_list_for_driver = [{"vehicle_id": k, **v} for k, v in dm["vehicles"].items()]
            vehicles_list_for_driver.sort(key=lambda x: x["trip_count"], reverse=True)
            
            # Convert routes dict to list and calculate efficiency
            routes_list = []
            for r_id, r_data in dm["routes"].items():
                route_efficiency = (r_data["total_collections"] / r_data["total_expected"] * 100) if r_data["total_expected"] > 0 else 0
                routes_list.append({
                    "route_id": r_id,
                    **r_data,
                    "efficiency": route_efficiency
                })
            routes_list.sort(key=lambda x: x["trip_count"], reverse=True)
            
            # Create final driver metrics
            driver_data = {
                **dm,
                "collection_efficiency": efficiency,
                "avg_per_trip": dm["total_collections"] / dm["trip_count"] if dm["trip_count"] > 0 else 0,
                "vehicles": vehicles_list_for_driver,
                "routes": routes_list
            }
            del driver_data["total_expected"]
            drivers_list.append(driver_data)
        
        # Sort drivers by total collections
        drivers_list.sort(key=lambda x: x["total_collections"], reverse=True)
        
        # Process daily performance
        daily_data = process_daily_performance(enriched_trips)
        
        # Prepare the report context
        context = {
            "summary": {
                "total_collections": total_collections,
                "total_expenses": total_expenses,
                "fuel_expense": total_fuel_expense,
                "repair_expense": total_repair_expense,
                "other_expense": total_other_expense,
                "net_profit": total_collections - total_expenses,
                "trip_count": trip_count,
                "utilization_rate": overall_utilization,
                "active_days": len(active_days),
                "total_days": date_range_days
            },
            "vehicles": vehicles_list,
            "drivers": drivers_list,
            "daily_data": daily_data,
            "trips": enriched_trips,
            "start_date": parsed_start_date.strftime("%Y-%m-%d"),
            "end_date": parsed_end_date.strftime("%Y-%m-%d"),
            "report_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Generate the report in the specified format
        if format == ReportFormat.HTML:
            # Render the HTML template directly
            template = template_env.get_template("combined_report.html")
            html_content = template.render(**context)
            
            # Return HTML response
            filename = f"combined_report_{parsed_start_date.strftime('%Y%m%d')}.html"
            
            return StreamingResponse(
                io.StringIO(html_content),
                media_type="text/html",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        else:
            # Render PDF
            pdf_content = render_template_to_pdf("combined_report.html", context)
            filename = f"combined_report_{parsed_start_date.strftime('%Y%m%d')}.pdf"
            
            return StreamingResponse(
                pdf_content,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating combined report: {str(e)}"
        ) 