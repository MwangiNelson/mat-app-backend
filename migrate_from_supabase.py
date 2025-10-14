import os
from dotenv import load_dotenv
import psycopg2
from supabase import create_client, Client
import uuid
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

def create_schema(cursor):
    """Create the database schema in local PostgreSQL."""
    print("Creating database schema...")

    schema_sql = """
    -- Enable the UUID extension
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    -- Users table (matching app/models/models.py)
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        phone TEXT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Routes table to define standard routes
    CREATE TABLE IF NOT EXISTS routes (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name VARCHAR(100) NOT NULL,
        origin VARCHAR(100) NOT NULL,
        destination VARCHAR(100) NOT NULL,
        distance DECIMAL(8, 2), -- in kilometers
        estimated_duration INT, -- in minutes
        fare_amount DECIMAL(10, 2) NOT NULL, -- standard fare per person
        status VARCHAR(20) NOT NULL DEFAULT 'active', -- active, inactive
        description TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Vehicles table (matching app/models/models.py)
    CREATE TABLE IF NOT EXISTS vehicles (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        reg_no TEXT UNIQUE NOT NULL,
        model TEXT NOT NULL,
        owner TEXT DEFAULT 'NO_OWNER_RECORDED',
        status TEXT NOT NULL DEFAULT 'active',
        insurance_expiry DATE NOT NULL,
        tlb_expiry DATE NOT NULL,
        passenger_capacity NUMERIC DEFAULT 14,
        inspection_expiry DATE,
        speed_governor_expiry DATE NOT NULL DEFAULT NOW(),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Drivers table (matching app/models/models.py)
    CREATE TABLE IF NOT EXISTS drivers (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name TEXT NOT NULL,
        license_no TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        experience TEXT,
        rating NUMERIC(3,1) DEFAULT 0.0,
        photo_url TEXT,
        cancelled BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Trips table (matching app/models/models.py)
    CREATE TABLE IF NOT EXISTS trips (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        driver_id UUID REFERENCES drivers(id),
        vehicle_id UUID REFERENCES vehicles(id),
        collection_time TIMESTAMP WITH TIME ZONE,
        route TEXT,
        notes TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        collected_amount INTEGER NOT NULL DEFAULT 0,
        repair_expense NUMERIC DEFAULT 0,
        created_by UUID NOT NULL REFERENCES users(id),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        status TEXT NOT NULL
    );

    -- Location tracking table
    CREATE TABLE IF NOT EXISTS locations (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        driver_id UUID REFERENCES drivers(id) ON DELETE CASCADE,
        latitude NUMERIC(10,6) NOT NULL,
        longitude NUMERIC(10,6) NOT NULL,
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Daily summaries for reporting (aggregates trip data)
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

    -- Password reset tokens table
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id UUID NOT NULL REFERENCES users(id),
        token TEXT UNIQUE NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        used_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Deficits table
    CREATE TABLE IF NOT EXISTS deficits (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
        driver UUID NOT NULL REFERENCES drivers(id),
        vehicle UUID NOT NULL REFERENCES vehicles(id),
        amount INTEGER NOT NULL DEFAULT 0,
        deficit_type TEXT NOT NULL DEFAULT 'deficit'
    );

    -- Create indexes for better query performance
    CREATE INDEX IF NOT EXISTS idx_vehicles_status ON vehicles(status);
    CREATE INDEX IF NOT EXISTS idx_drivers_status ON drivers(status);
    CREATE INDEX IF NOT EXISTS idx_locations_driver_id ON locations(driver_id);
    CREATE INDEX IF NOT EXISTS idx_trips_driver_id ON trips(driver_id);
    CREATE INDEX IF NOT EXISTS idx_trips_vehicle_id ON trips(vehicle_id);
    CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);
    CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
    CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);

    -- Set up a function to update the updated_at timestamp
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    -- Drop triggers if they exist (to avoid conflicts)
    DROP TRIGGER IF EXISTS update_users_updated_at ON users;
    DROP TRIGGER IF EXISTS update_vehicles_updated_at ON vehicles;
    DROP TRIGGER IF EXISTS update_drivers_updated_at ON drivers;
    DROP TRIGGER IF EXISTS update_trips_modtime ON trips;
    DROP TRIGGER IF EXISTS update_routes_modtime ON routes;
    DROP TRIGGER IF EXISTS update_daily_summaries_modtime ON daily_summaries;

    -- Create triggers to automatically update the updated_at column
    CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

    CREATE TRIGGER update_vehicles_updated_at
    BEFORE UPDATE ON vehicles
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

    CREATE TRIGGER update_drivers_updated_at
    BEFORE UPDATE ON drivers
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

    CREATE TRIGGER update_trips_modtime
    BEFORE UPDATE ON trips
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

    CREATE TRIGGER update_routes_modtime
    BEFORE UPDATE ON routes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

    CREATE TRIGGER update_daily_summaries_modtime
    BEFORE UPDATE ON daily_summaries
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
    """

    cursor.execute(schema_sql)
    print("Schema created successfully!")

def migrate_table(supabase_client, local_cursor, local_conn, table_name, columns):
    """Migrate data from a Supabase table to local PostgreSQL."""
    print(f"Starting migration for table: {table_name}...")

    # Create log files for this table
    log_file = f"migration_{table_name}_summary.txt"
    error_file = f"migration_{table_name}_errors.txt"

    try:
        # Fetch all data from Supabase (handle pagination for large tables)
        all_rows = []
        offset = 0
        limit = 1000  # Supabase default limit

        while True:
            response = supabase_client.table(table_name).select('*').range(offset, offset + limit - 1).execute()
            rows = response.data

            if not rows:
                break

            all_rows.extend(rows)
            offset += limit

            # Safety check to prevent infinite loops
            if len(rows) < limit:
                break

        rows = all_rows
        total_rows = len(rows) if rows else 0

        if not rows:
            with open(log_file, 'w') as f:
                f.write(f"Table: {table_name}\n")
                f.write(f"Total records in Supabase: 0\n")
                f.write("No data to migrate\n")
            print(f"No data found in {table_name}")
            return

        # Prepare INSERT statement
        column_names = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"

        # Insert data into local database, handling errors gracefully
        success_count = 0
        error_count = 0
        error_details = []

        for i, row in enumerate(rows):
            try:
                values = []
                for col in columns:
                    val = row.get(col)
                    # Handle special cases for missing required fields
                    if col == 'password_hash' and val is None:
                        # Generate a default password hash for users without one
                        val = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPjYQmHqU5tO"  # Default: "password123"
                    values.append(val)

                local_cursor.execute(insert_sql, values)
                # Commit each successful insert to avoid transaction abortion issues
                local_conn.commit()
                success_count += 1
            except Exception as row_error:
                error_count += 1
                # Rollback on error to clear the aborted transaction state
                local_conn.rollback()
                error_details.append(f"Row {i+1} (ID: {row.get('id', 'N/A')}): {str(row_error)}")

        # Write summary to file
        with open(log_file, 'w') as f:
            f.write(f"Table: {table_name}\n")
            f.write(f"Total records in Supabase: {total_rows}\n")
            f.write(f"Successfully migrated: {success_count}\n")
            f.write(f"Errors/Skipped: {error_count}\n")
            f.write(f"Success rate: {success_count/total_rows*100:.1f}%\n")
        # Write detailed errors to separate file
        if error_details:
            with open(error_file, 'w') as f:
                f.write(f"Error details for table: {table_name}\n")
                f.write("=" * 50 + "\n")
                for error in error_details:
                    f.write(f"{error}\n")
                f.write("\n")

        print(f"Completed migration for {table_name}: {success_count} success, {error_count} errors")

    except Exception as e:
        with open(log_file, 'w') as f:
            f.write(f"Table: {table_name}\n")
            f.write(f"CRITICAL ERROR: {str(e)}\n")
        print(f"Critical error migrating {table_name}: {e}")

def reset_database():
    """Reset the local database by dropping and recreating it."""
    try:
        # Connect to default postgres database
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_SERVER", "localhost"),
            database="postgres",
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "D4Cheap1411!&")
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Terminate active connections and drop database
        cursor.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = 'risen_db';
        """)

        cursor.execute("DROP DATABASE IF EXISTS risen_db;")
        cursor.execute("CREATE DATABASE risen_db;")

        cursor.close()
        conn.close()
        print("Database reset completed.")
        return True
    except Exception as e:
        print(f"Error resetting database: {e}")
        return False

def reset_tables(cursor, conn):
    """Drop all existing tables to ensure clean migration."""
    # Drop in reverse dependency order to avoid CASCADE issues
    tables = ['daily_summaries', 'locations', 'trips', 'drivers', 'vehicles', 'routes', 'users']

    for table in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            conn.commit()  # Commit each drop individually
            print(f"Dropped table: {table}")
        except Exception as e:
            print(f"Error dropping {table}: {e}")
            conn.rollback()  # Rollback on error to clear transaction state

def get_fresh_connection():
    """Get a fresh connection to the risen_db."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_SERVER", "localhost"),
        database=os.getenv("POSTGRES_DB", "risen_db"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "D4Cheap1411!&")
    )

def main(reset_db=False):
    """Main migration function."""
    try:
        if reset_db:
            print("Resetting database...")
            if reset_database():
                print("Database reset successful.")
            else:
                print("Database reset failed.")
                return

        # Connect to Supabase
        print("Connecting to Supabase...")
        supabase = get_supabase_client()

        # Connect to local PostgreSQL
        print("Connecting to local PostgreSQL...")
        local_conn = get_local_db_connection()
        local_cursor = local_conn.cursor()

        # Create schema
        create_schema(local_cursor)
        local_conn.commit()

        # Define table columns for migration (matching app/models/models.py)
        table_columns = {
            'users': ['id', 'full_name', 'role', 'phone', 'email', 'password_hash', 'created_at', 'updated_at'],
            'routes': ['id', 'name', 'origin', 'destination', 'distance', 'estimated_duration', 'fare_amount', 'status', 'description', 'created_at', 'updated_at'],
            'vehicles': ['id', 'reg_no', 'model', 'owner', 'status', 'insurance_expiry', 'tlb_expiry', 'passenger_capacity', 'inspection_expiry', 'speed_governor_expiry', 'created_at', 'updated_at'],
            'drivers': ['id', 'name', 'license_no', 'phone', 'status', 'experience', 'rating', 'photo_url', 'cancelled', 'created_at', 'updated_at'],
            'trips': ['id', 'driver_id', 'vehicle_id', 'collection_time', 'route', 'notes', 'created_at', 'collected_amount', 'repair_expense', 'created_by', 'updated_at', 'status'],
            'locations': ['id', 'driver_id', 'latitude', 'longitude', 'timestamp'],
            'daily_summaries': ['id', 'vehicle_id', 'driver_id', 'date', 'trip_count', 'total_passengers', 'total_expected_amount', 'total_collected_amount', 'total_expenses', 'net_profit', 'created_at', 'updated_at'],
            'password_reset_tokens': ['id', 'user_id', 'token', 'expires_at', 'used_at', 'created_at'],
            'deficits': ['id', 'created_at', 'driver', 'vehicle', 'amount', 'deficit_type']
        }

        # Migrate each table
        for table_name, columns in table_columns.items():
            migrate_table(supabase, local_cursor, local_conn, table_name, columns)
            # Note: commits are now handled within migrate_table function

        # Create overall migration summary
        create_migration_summary()

        # Close connections
        local_cursor.close()
        local_conn.close()

        print("Migration completed! Check the summary files for detailed results.")

    except Exception as e:
        print(f"Migration failed: {e}")
        raise

def create_migration_summary():
    """Create an overall migration summary."""
    try:
        with open("migration_overall_summary.txt", 'w') as f:
            f.write("MIGRATION SUMMARY REPORT\n")
            f.write("=" * 50 + "\n\n")

            tables = ['users', 'routes', 'vehicles', 'drivers', 'trips', 'locations', 'daily_summaries', 'password_reset_tokens', 'deficits']
            total_original = 0
            total_migrated = 0
            total_errors = 0

            for table in tables:
                log_file = f"migration_{table}_summary.txt"
                if os.path.exists(log_file):
                    with open(log_file, 'r') as lf:
                        content = lf.read()
                        f.write(f"TABLE: {table.upper()}\n")
                        f.write("-" * 20 + "\n")
                        f.write(content)
                        f.write("\n")

                        # Extract numbers for totals
                        lines = content.split('\n')
                        for line in lines:
                            if line.startswith("Total records in Supabase:"):
                                total_original += int(line.split(": ")[1])
                            elif line.startswith("Successfully migrated:"):
                                total_migrated += int(line.split(": ")[1])
                            elif line.startswith("Errors/Skipped:"):
                                total_errors += int(line.split(": ")[1])

            f.write("OVERALL SUMMARY\n")
            f.write("=" * 20 + "\n")
            f.write(f"Total records in Supabase: {total_original}\n")
            f.write(f"Total successfully migrated: {total_migrated}\n")
            f.write(f"Total errors/skipped: {total_errors}\n")
            if total_original > 0:
                f.write(f"Overall success rate: {total_migrated/total_original*100:.1f}%\n")
            f.write("\nMigration completed at: " + str(datetime.now()))

        print("Overall migration summary created: migration_overall_summary.txt")

    except Exception as e:
        print(f"Error creating summary: {e}")

if __name__ == "__main__":
    import sys
    reset_db = "--reset" in sys.argv
    main(reset_db=reset_db)
