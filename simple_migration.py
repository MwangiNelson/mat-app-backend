import os
from dotenv import load_dotenv
import psycopg2
from supabase import create_client, Client
from datetime import datetime

# Load environment variables
load_dotenv()

def get_supabase_client() -> Client:
    """Create and return a Supabase client instance."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

    return create_client(supabase_url, supabase_key)

def get_local_db_connection():
    """Create connection to local PostgreSQL database."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_SERVER", "localhost"),
        database=os.getenv("POSTGRES_DB", "risen_db"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "D4Cheap1411!&")
    )

def create_tables(cursor):
    """Create all necessary tables."""
    print("Creating tables...")

    tables_sql = """
    -- Enable the UUID extension
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    -- Users table
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'manager', 'staff')),
        phone TEXT,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Routes table
    CREATE TABLE IF NOT EXISTS routes (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name VARCHAR(100) NOT NULL,
        origin VARCHAR(100) NOT NULL,
        destination VARCHAR(100) NOT NULL,
        distance DECIMAL(8, 2),
        estimated_duration INT,
        fare_amount DECIMAL(10, 2) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        description TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Vehicles table (matching Supabase schema)
    CREATE TABLE IF NOT EXISTS vehicles (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        reg_no TEXT UNIQUE NOT NULL,
        model TEXT NOT NULL,
        owner TEXT DEFAULT 'NO_OWNER_RECORDED',
        status TEXT NOT NULL CHECK (status IN ('active', 'maintenance', 'inactive')),
        insurance_expiry DATE NOT NULL,
        tlb_expiry DATE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        passenger_capacity NUMERIC DEFAULT 14,
        inspection_expiry DATE,
        speed_governor_expiry DATE NOT NULL DEFAULT NOW()
    );

    -- Drivers table (matching Supabase schema)
    CREATE TABLE IF NOT EXISTS drivers (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name TEXT NOT NULL,
        license_no TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
        experience TEXT,
        rating NUMERIC(3,1) DEFAULT 0.0,
        photo_url TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        cancelled BOOLEAN NOT NULL DEFAULT false
    );

    -- Trips table (matching actual Supabase schema)
    CREATE TABLE IF NOT EXISTS trips (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        driver_id UUID REFERENCES drivers(id) ON DELETE CASCADE,
        vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
        collection_time TIMESTAMP WITH TIME ZONE,
        route TEXT,
        notes TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        collected_amount BIGINT NOT NULL DEFAULT 0,
        repair_expense NUMERIC DEFAULT 0,
        created_by UUID NOT NULL REFERENCES users(id),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'cancelled'))
    );

    -- Location tracking table
    CREATE TABLE IF NOT EXISTS locations (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        driver_id UUID REFERENCES drivers(id) ON DELETE CASCADE,
        latitude NUMERIC(10,6) NOT NULL,
        longitude NUMERIC(10,6) NOT NULL,
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Daily summaries table
    CREATE TABLE IF NOT EXISTS daily_summaries (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
        driver_id UUID NULL REFERENCES drivers(id) ON DELETE SET NULL,
        date DATE NOT NULL,
        trip_count INT NOT NULL DEFAULT 0,
        total_passengers INT NOT NULL DEFAULT 0,
        total_expected_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
        total_collected_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
        total_expenses DECIMAL(10, 2) NOT NULL DEFAULT 0,
        net_profit DECIMAL(10, 2) NOT NULL DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(vehicle_id, date)
    );

    -- Deficits table (matching Supabase schema)
    CREATE TABLE IF NOT EXISTS deficits (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        driver UUID NOT NULL,
        vehicle UUID NOT NULL,
        amount BIGINT NOT NULL DEFAULT 0,
        deficit_type TEXT NOT NULL DEFAULT 'deficit',
        CONSTRAINT deficits_driver_fkey FOREIGN KEY (driver) REFERENCES drivers(id) ON UPDATE CASCADE,
        CONSTRAINT deficits_vehicle_fkey FOREIGN KEY (vehicle) REFERENCES vehicles(id) ON UPDATE CASCADE
    );

    -- Create indexes
    CREATE INDEX IF NOT EXISTS idx_vehicles_status ON vehicles(status);
    CREATE INDEX IF NOT EXISTS idx_drivers_status ON drivers(status);
    CREATE INDEX IF NOT EXISTS idx_locations_driver_id ON locations(driver_id);
    CREATE INDEX IF NOT EXISTS idx_trips_driver_id ON trips(driver_id);
    CREATE INDEX IF NOT EXISTS idx_trips_vehicle_id ON trips(vehicle_id);
    CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);

    -- Create triggers function
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    -- Create triggers (drop if exist first)
    DROP TRIGGER IF EXISTS update_users_updated_at ON users;
    DROP TRIGGER IF EXISTS update_vehicles_updated_at ON vehicles;
    DROP TRIGGER IF EXISTS update_drivers_updated_at ON drivers;
    DROP TRIGGER IF EXISTS update_trips_modtime ON trips;
    DROP TRIGGER IF EXISTS update_routes_modtime ON routes;
    DROP TRIGGER IF EXISTS update_daily_summaries_modtime ON daily_summaries;

    CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
    CREATE TRIGGER update_vehicles_updated_at BEFORE UPDATE ON vehicles FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
    CREATE TRIGGER update_drivers_updated_at BEFORE UPDATE ON drivers FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
    CREATE TRIGGER update_trips_modtime BEFORE UPDATE ON trips FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    CREATE TRIGGER update_routes_modtime BEFORE UPDATE ON routes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    CREATE TRIGGER update_daily_summaries_modtime BEFORE UPDATE ON daily_summaries FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """

    cursor.execute(tables_sql)
    print("Tables created successfully!")

def migrate_data():
    """Main migration function."""
    print("Starting data migration from Supabase to local PostgreSQL...")

    try:
        # Connect to Supabase
        supabase = get_supabase_client()
        print("✅ Connected to Supabase")

        # Connect to local PostgreSQL
        local_conn = get_local_db_connection()
        local_cursor = local_conn.cursor()
        print("✅ Connected to local PostgreSQL")

        # Create tables
        create_tables(local_cursor)
        local_conn.commit()

        # Define table columns
        table_columns = {
            'users': ['id', 'full_name', 'role', 'phone', 'email', 'created_at', 'updated_at'],
            'routes': ['id', 'name', 'origin', 'destination', 'distance', 'estimated_duration', 'fare_amount', 'status', 'description', 'created_at', 'updated_at'],
            'vehicles': ['id', 'reg_no', 'model', 'owner', 'status', 'insurance_expiry', 'tlb_expiry', 'created_at', 'updated_at', 'passenger_capacity', 'inspection_expiry', 'speed_governor_expiry'],
            'drivers': ['id', 'name', 'license_no', 'phone', 'status', 'experience', 'rating', 'photo_url', 'created_at', 'updated_at', 'cancelled'],
            'trips': ['id', 'driver_id', 'vehicle_id', 'collection_time', 'route', 'notes', 'created_at', 'collected_amount', 'repair_expense', 'created_by', 'updated_at', 'status'],
            'locations': ['id', 'driver_id', 'latitude', 'longitude', 'timestamp'],
            'daily_summaries': ['id', 'vehicle_id', 'driver_id', 'date', 'trip_count', 'total_passengers', 'total_expected_amount', 'total_collected_amount', 'total_expenses', 'net_profit', 'created_at', 'updated_at'],
            'deficits': ['id', 'created_at', 'driver', 'vehicle', 'amount', 'deficit_type']
        }

        total_migrated = 0
        total_errors = 0

        # Migrate each table
        for table_name, columns in table_columns.items():
            print(f"\n📋 Migrating table: {table_name}")

            try:
                # Fetch data from Supabase
                response = supabase.table(table_name).select('*').execute()
                rows = response.data

                if not rows:
                    print(f"  ℹ️  No data found in {table_name}")
                    continue

                print(f"  📊 Found {len(rows)} records in Supabase")

                # Prepare INSERT statement
                column_names = ', '.join(columns)
                placeholders = ', '.join(['%s'] * len(columns))
                insert_sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"

                # Insert data
                success_count = 0
                error_count = 0
                error_details = []

                for i, row in enumerate(rows):
                    try:
                        values = [row.get(col) for col in columns]
                        local_cursor.execute(insert_sql, values)
                        local_conn.commit()
                        success_count += 1
                    except Exception as row_error:
                        error_count += 1
                        # Rollback on error to clear the aborted transaction state
                        local_conn.rollback()
                        error_details.append(f"Row {i+1} (ID: {row.get('id', 'N/A')}): {str(row_error)}")
                        # Print first few errors to console for debugging
                        if error_count <= 3:
                            print(f"  🔍 Error details: {str(row_error)}")

                print(f"  ✅ Successfully migrated: {success_count}")
                if error_count > 0:
                    print(f"  ❌ Errors: {error_count}")

                total_migrated += success_count
                total_errors += error_count

            except Exception as e:
                print(f"  ❌ Error migrating {table_name}: {e}")
                total_errors += 1

        # Create summary
        print("\n🎉 Migration Summary:")
        print(f"   Total records migrated: {total_migrated}")
        print(f"   Total errors: {total_errors}")
        if total_migrated + total_errors > 0:
            success_rate = (total_migrated / (total_migrated + total_errors)) * 100
            print(f"   Success rate: {success_rate:.1f}%")
        # Close connections
        local_cursor.close()
        local_conn.close()

        print("\n✅ Migration completed!")
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = migrate_data()
    if success:
        print("\n🎯 Next steps:")
        print("   1. Update your application to use local PostgreSQL")
        print("   2. Test your API endpoints")
        print("   3. Verify data integrity")
    else:
        print("\n🔧 Troubleshooting:")
        print("   1. Check your .env file has correct SUPABASE_URL and SUPABASE_KEY")
        print("   2. Ensure PostgreSQL is running")
        print("   3. Verify database 'risen_db' exists")
