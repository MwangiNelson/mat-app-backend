from pydantic import BaseModel, Field, validator
from typing import Optional, Union
from datetime import datetime, date
from enum import Enum

class VehicleStatus(str, Enum):
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    INACTIVE = "inactive"

def parse_date_string(date_str: str) -> date:
    """Parse a date string in either DD-MM-YYYY or YYYY-MM-DD format to a date object"""
    try:
        if isinstance(date_str, date):
            return date_str
            
        # Try to handle ISO 8601 format with time component (e.g., 2025-04-22T21:00:00.000Z)
        if 'T' in date_str:
            # Extract just the date part (before the T)
            date_part = date_str.split('T')[0]
            parts = date_part.split('-')
            if len(parts) == 3:
                year, month, day = map(int, parts)
                return date(year, month, day)
            
        # Check if it's in ISO format (YYYY-MM-DD)
        parts = date_str.split('-')
        if len(parts) == 3:
            if len(parts[0]) == 4:  # First part is 4 digits (year)
                # ISO format (YYYY-MM-DD)
                year, month, day = map(int, parts)
                return date(year, month, day)
            else:
                # DD-MM-YYYY format
                day, month, year = map(int, parts)
                return date(year, month, day)
        raise ValueError(f"Invalid date format: {date_str}")
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date format: {date_str}. Please use DD-MM-YYYY or YYYY-MM-DD format.")

class VehicleBase(BaseModel):
    registration: str = Field(alias="reg_no")
    model: str
    owner: str
    status: VehicleStatus = VehicleStatus.ACTIVE
    insurance_expiry: Union[str, date]
    tlb_expiry: Union[str, date]
    speed_governor_expiry: Union[str, date]
    inspection_expiry: Union[str, date]
    passenger_capacity: int = 0

    
    class Config:
        populate_by_name = True
        # Remove ISO format encoder to avoid conflict
        
    @validator('insurance_expiry', 'tlb_expiry', 'speed_governor_expiry', 'inspection_expiry', pre=True)
    def validate_dates(cls, value):
        """Parse dates from strings, supporting both DB and user formats"""
        if isinstance(value, str):
            try:
                return parse_date_string(value)
            except ValueError:
                raise ValueError(f"Invalid date format: {value}. Please use DD-MM-YYYY format.")
        return value

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    model: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[VehicleStatus] = None
    insurance_expiry: Optional[Union[str, date]] = None
    tlb_expiry: Optional[Union[str, date]] = None
    speed_governor_expiry: Optional[Union[str, date]] = None
    inspection_expiry: Optional[Union[str, date]] = None
    passenger_capacity: Optional[int] = None
    route_id: Optional[str] = None
    
    @validator('insurance_expiry', 'tlb_expiry', 'speed_governor_expiry', 'inspection_expiry', pre=True)
    def validate_dates(cls, value):
        """Parse dates from strings, supporting both DB and user formats"""
        if value is not None and isinstance(value, str):
            try:
                return parse_date_string(value)
            except ValueError:
                raise ValueError(f"Invalid date format: {value}. Please use DD-MM-YYYY format.")
        return value

class VehicleInDB(VehicleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class VehicleResponse(VehicleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.strftime('%d-%m-%Y')
        }
        
    @validator('insurance_expiry', 'tlb_expiry', 'speed_governor_expiry', 'inspection_expiry')
    def format_dates(cls, value):
        """Ensure dates are properly formatted for client consumption"""
        if isinstance(value, date):
            # Format as DD-MM-YYYY for client
            return value.strftime('%d-%m-%Y')
        elif isinstance(value, str):
            # If already a string, make sure it's in DD-MM-YYYY format
            try:
                # Try parsing as a date first
                d = parse_date_string(value)
                return d.strftime('%d-%m-%Y')
            except ValueError:
                # Return as is if we can't parse it
                return value
        return value

class VehicleDetail(VehicleResponse):
    route_name: Optional[str] = None 