#!/usr/bin/env python3
"""
Test script to verify SQLAlchemy connection to local PostgreSQL database
"""
import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from sqlalchemy import text
from app.models import engine, SessionLocal, Base
from app.models.models import User, Driver, Vehicle

def test_connection():
    """Test database connection and basic operations."""
    try:
        print("🔍 Testing database connection...")

        # Test engine connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            if row and row[0] == 1:
                print("✅ Database connection successful")
            else:
                print("❌ Database connection failed")
                return False

        # Test session
        db = SessionLocal()
        try:
            # Test if tables exist by counting records
            user_count = db.query(User).count()
            driver_count = db.query(Driver).count()
            vehicle_count = db.query(Vehicle).count()

            print(f"📊 Database contents:")
            print(f"   Users: {user_count}")
            print(f"   Drivers: {driver_count}")
            print(f"   Vehicles: {vehicle_count}")

            print("✅ SQLAlchemy models working correctly")
            return True

        finally:
            db.close()

    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    if success:
        print("\n🎉 Database connection and models are working!")
        print("You can now start converting your API endpoints to use SQLAlchemy.")
    else:
        print("\n🔧 Please check your database configuration and try again.")
    sys.exit(0 if success else 1)
