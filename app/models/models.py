from sqlalchemy import Column, Integer, String, DateTime, Date, Numeric, Text, Boolean, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    phone = Column(String)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)  # Added for local authentication
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user")

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="password_reset_tokens")

    # Indexes
    __table_args__ = (
        Index('idx_password_reset_tokens_token', 'token'),
        Index('idx_password_reset_tokens_user_id', 'user_id'),
    )

class Route(Base):
    __tablename__ = "routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    origin = Column(String(100), nullable=False)
    destination = Column(String(100), nullable=False)
    distance = Column(Numeric(8, 2))
    estimated_duration = Column(Integer)
    fare_amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), nullable=False, default='active')
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships (vehicles don't reference routes in actual schema)
    # trips = relationship("Trip", back_populates="route")  # Commented out since route is TEXT, not FK

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reg_no = Column(String, unique=True, nullable=False)  # Changed from registration to reg_no
    model = Column(String, nullable=False)
    owner = Column(String, default='NO_OWNER_RECORDED')
    status = Column(String, nullable=False, default='active')
    insurance_expiry = Column(Date, nullable=False)
    tlb_expiry = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    passenger_capacity = Column(Numeric, default=14)
    inspection_expiry = Column(Date)
    speed_governor_expiry = Column(Date, nullable=False, server_default=func.now())

    # Relationships (no route relationship in actual schema)
    trips = relationship("Trip", back_populates="vehicle")
    daily_summaries = relationship("DailySummary", back_populates="vehicle")

    # Indexes
    __table_args__ = (
        Index('idx_vehicles_status', 'status'),
    )

class Driver(Base):
    __tablename__ = "drivers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    license_no = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=False)
    status = Column(String, nullable=False, default='active')
    experience = Column(String)
    rating = Column(Numeric(3, 1), default=0.0)
    photo_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    cancelled = Column(Boolean, nullable=False, default=False)

    # Relationships
    trips = relationship("Trip", back_populates="driver")
    locations = relationship("Location", back_populates="driver")
    daily_summaries = relationship("DailySummary", back_populates="driver")

    # Indexes
    __table_args__ = (
        Index('idx_drivers_status', 'status'),
    )

class Trip(Base):
    __tablename__ = "trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id = Column(UUID(as_uuid=True), ForeignKey('drivers.id'))
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey('vehicles.id'))
    collection_time = Column(DateTime(timezone=True))
    route = Column(Text)  # Changed from route_id to route as TEXT
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    collected_amount = Column(Integer, nullable=False, default=0)  # Changed to Integer/BIGINT
    repair_expense = Column(Numeric, default=0)  # Changed from fuel_cost/other_expenses
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    status = Column(String, nullable=False)

    # Relationships
    vehicle = relationship("Vehicle", back_populates="trips")
    driver = relationship("Driver", back_populates="trips")
    creator = relationship("User", foreign_keys=[created_by])

    # Indexes
    __table_args__ = (
        Index('idx_trips_driver_id', 'driver_id'),
        Index('idx_trips_vehicle_id', 'vehicle_id'),
        Index('idx_trips_status', 'status'),
    )

class Location(Base):
    __tablename__ = "locations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id = Column(UUID(as_uuid=True), ForeignKey('drivers.id'), nullable=False)
    latitude = Column(Numeric(10, 6), nullable=False)
    longitude = Column(Numeric(10, 6), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    driver = relationship("Driver", back_populates="locations")

    # Indexes
    __table_args__ = (
        Index('idx_locations_driver_id', 'driver_id'),
    )

class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey('vehicles.id'), nullable=False)
    driver_id = Column(UUID(as_uuid=True), ForeignKey('drivers.id'), nullable=True)
    date = Column(Date, nullable=False)
    trip_count = Column(Integer, nullable=False, default=0)
    total_passengers = Column(Integer, nullable=False, default=0)
    total_expected_amount = Column(Numeric(10, 2), nullable=False, default=0)
    total_collected_amount = Column(Numeric(10, 2), nullable=False, default=0)
    total_expenses = Column(Numeric(10, 2), nullable=False, default=0)
    net_profit = Column(Numeric(10, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    vehicle = relationship("Vehicle", back_populates="daily_summaries")
    driver = relationship("Driver", back_populates="daily_summaries")

    # Unique constraint
    __table_args__ = (
        {'schema': None},  # This ensures unique constraint works
    )

class Deficit(Base):
    __tablename__ = "deficits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    driver = Column(UUID(as_uuid=True), ForeignKey('drivers.id'), nullable=False)
    vehicle = Column(UUID(as_uuid=True), ForeignKey('vehicles.id'), nullable=False)
    amount = Column(Integer, nullable=False, default=0)
    deficit_type = Column(String, nullable=False, default='deficit')

    # Relationships
    driver_rel = relationship("Driver", foreign_keys=[driver])
    vehicle_rel = relationship("Vehicle", foreign_keys=[vehicle])

# Note: We don't need to define the unique constraint in __table_args__ for this simple case
# The database will handle the UNIQUE(vehicle_id, date) constraint we created in the schema
