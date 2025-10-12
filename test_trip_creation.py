from app.models import get_db
from app.models.models import Trip, Vehicle, Driver
from app.schemas.trips import TripCreate

# Test the full trip creation process
try:
    db = next(get_db())

    # Parse the payload like the API does
    payload = {
        'vehicle_id': 'b170f758-ca49-4210-8e45-117b21cf1145',
        'driver_id': 'ea0b7c0b-3fee-49ff-9f9a-8f0070dfc7bf',
        'collection_time': '2025-09-14T20:43:24+03:00',
        'route': None,
        'notes': 'This is a test',
        'collected_amount': 0,
        'repair_expense': 0,
        'status': 'completed'
    }

    trip_data = TripCreate(**payload)
    print('✅ Payload parsed')

    # Check vehicle and driver (like the API does)
    vehicle = db.query(Vehicle).filter(Vehicle.id == trip_data.vehicle_id).first()
    driver = db.query(Driver).filter(Driver.id == trip_data.driver_id).first()

    print(f'✅ Vehicle found: {vehicle is not None}')
    print(f'✅ Driver found: {driver is not None}')
    print(f'✅ Vehicle active: {vehicle.status == "active"}')
    print(f'✅ Driver active: {driver.status == "active"}')

    # Try to create the trip
    new_trip = Trip(
        driver_id=trip_data.driver_id,
        vehicle_id=trip_data.vehicle_id,
        collection_time=trip_data.collection_time,
        route=trip_data.route,
        notes=trip_data.notes,
        collected_amount=trip_data.collected_amount or 0,
        repair_expense=trip_data.repair_expense or 0.0,
        created_by='e0accf82-1469-41e9-97bd-b4c3a2578ae8',  # Mock user ID
        status=trip_data.status or 'completed'
    )

    print('✅ Trip object created')

    db.add(new_trip)
    print('✅ Trip added to session')

    db.commit()
    print('✅ Database commit successful')

    db.refresh(new_trip)
    print(f'✅ Trip created with ID: {new_trip.id}')

    db.close()

except Exception as e:
    print(f'❌ Error during trip creation: {e}')
    import traceback
    traceback.print_exc()
