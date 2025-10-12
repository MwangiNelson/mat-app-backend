import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_SERVER', 'localhost'),
        database='postgres',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', 'D4Cheap1411!&')
    )
    conn.autocommit = True
    cursor = conn.cursor()

    # Terminate connections and drop/recreate database
    cursor.execute("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = 'risen_db';
    """)

    cursor.execute('DROP DATABASE IF EXISTS risen_db;')
    cursor.execute('CREATE DATABASE risen_db;')

    cursor.close()
    conn.close()
    print('Database reset completed successfully!')

except Exception as e:
    print(f'Error: {e}')
