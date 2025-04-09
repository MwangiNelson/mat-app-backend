# Matatu Management System API

A FastAPI backend with Supabase integration for the Matatu Management System.

## Features

- User authentication and management
- Vehicle registration and tracking
- Driver management
- Daily operations recording
- Financial reporting
- Location tracking
- Trip management

## Tech Stack

- **Backend Framework**: FastAPI
- **Database**: Supabase (PostgreSQL)
- **Authentication**: JWT + Supabase Auth
- **APIs**: RESTful

## Setup and Installation

### Prerequisites

- Python 3.8+
- Supabase account

### Setting Up Supabase

1. Create a new Supabase project at [https://supabase.io](https://supabase.io)
2. Execute the SQL in `supabase_schema.sql` in the Supabase SQL Editor to create the database schema
3. Note your Supabase URL and anon key for configuration

### Local Development Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd matatu-app-backend
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

5. Update the `.env` file with your Supabase credentials and other configuration

6. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```

The API will be available at `http://localhost:8000`.

## API Documentation

Once the server is running, you can access the interactive API documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### Authentication

- `POST /api/auth/register` - Register a new user
- `POST /api/auth/login` - User login
- `POST /api/auth/refresh` - Refresh access token
- `GET /api/auth/me` - Get current user info
- `PUT /api/auth/me` - Update current user info

### Vehicles

- `GET /api/vehicles` - List all vehicles
- `POST /api/vehicles` - Create a new vehicle
- `GET /api/vehicles/{id}` - Get vehicle details
- `PUT /api/vehicles/{id}` - Update vehicle
- `DELETE /api/vehicles/{id}` - Delete vehicle
- `GET /api/vehicles/expiring` - Get vehicles with expiring documents

### Drivers

- `GET /api/drivers` - List all drivers
- `POST /api/drivers` - Create a new driver
- `GET /api/drivers/{id}` - Get driver details
- `PUT /api/drivers/{id}` - Update driver
- `DELETE /api/drivers/{id}` - Delete driver
- `GET /api/drivers/{id}/performance` - Get driver performance
- `PUT /api/drivers/{id}/rate` - Rate a driver

### Operations

- `GET /api/operations` - List operations (with filtering)
- `POST /api/operations` - Record new daily operation
- `GET /api/operations/{id}` - Get operation details
- `PUT /api/operations/{id}` - Update operation
- `DELETE /api/operations/{id}` - Delete operation
- `GET /api/operations/summary` - Get summary statistics
- `GET /api/operations/dashboard` - Get dashboard data

### Locations & Trips

- `POST /api/locations` - Update driver location
- `GET /api/locations/drivers` - Get all active drivers' locations
- `GET /api/locations/driver/{id}/history` - Get location history
- `POST /api/locations/trips` - Start a new trip
- `PUT /api/locations/trips/{id}` - Update trip
- `GET /api/locations/trips/active` - Get all active trips
- `GET /api/locations/trips/vehicle/{id}` - Get trips for a vehicle
- `GET /api/locations/trips/driver/{id}` - Get trips for a driver

## Environment Variables

- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_KEY` - Your Supabase anon key
- `SECRET_KEY` - Secret key for JWT generation
- `ALGORITHM` - Algorithm for JWT (default: HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Access token expiry time
- `REFRESH_TOKEN_EXPIRE_DAYS` - Refresh token expiry time

## License

MIT 