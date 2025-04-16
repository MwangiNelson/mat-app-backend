from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from uuid import UUID


class DeficitType(str, Enum):
    """Type of deficit record"""
    DEFICIT = "deficit"  # New deficit
    REPAYMENT = "repayment"  # Repayment of existing deficit


class DeficitBase(BaseModel):
    """Base model for deficit operations"""
    driver: UUID
    vehicle: UUID
    amount: int
    deficit_type: DeficitType = DeficitType.DEFICIT


class DeficitCreate(DeficitBase):
    """Model for creating a new deficit record"""
    pass


class Deficit(DeficitBase):
    """Model for deficit responses"""
    id: UUID
    created_at: datetime

    class Config:
        orm_mode = True


class DeficitTotals(BaseModel):
    """Model for deficit totals"""
    total_deficit: int = 0
    total_repaid: int = 0
    balance: int = 0  # total_deficit - total_repaid


class DeficitSummary(BaseModel):
    """Summary model for deficit listings"""
    deficits: List[Deficit]
    totals: DeficitTotals


class DriverDeficitSummary(DeficitTotals):
    """Deficit summary for a specific driver"""
    driver_id: UUID
    driver_name: Optional[str] = None


class VehicleDeficitSummary(DeficitTotals):
    """Deficit summary for a specific vehicle"""
    vehicle_id: UUID
    vehicle_registration: Optional[str] = None


class DeficitDetailedSummary(BaseModel):
    """Detailed summary with breakdowns by driver and vehicle"""
    overall: DeficitTotals
    by_driver: List[DriverDeficitSummary] = []
    by_vehicle: List[VehicleDeficitSummary] = []
    deficits: List[Deficit] 