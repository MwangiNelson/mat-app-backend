# Deficits API Documentation

The Deficits API provides endpoints for managing driver and vehicle deficit records. This includes creating new deficit entries, repayment records, and retrieving deficit information with detailed breakdowns.

## Endpoints

### Create Deficit

```httpS
POST /api/deficits/
```

Create a new deficit or repayment record for a driver and vehicle.

#### Request Body

| Field        | Type   | Description                                          |
|--------------|--------|------------------------------------------------------|
| driver       | UUID   | ID of the driver associated with the deficit         |
| vehicle      | UUID   | ID of the vehicle associated with the deficit        |
| amount       | integer| Amount of the deficit or repayment (in cents/pence)  |
| deficit_type | string | Type of record: "deficit" or "repayment"             |

#### Example Request

```json
{
  "driver": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "vehicle": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "amount": 5000,
  "deficit_type": "deficit"
}
```

#### Response

| Field        | Type     | Description                                          |
|--------------|----------|------------------------------------------------------|
| id           | UUID     | Unique identifier for the deficit record             |
| created_at   | datetime | Timestamp when the record was created                |
| driver       | UUID     | ID of the driver associated with the deficit         |
| vehicle      | UUID     | ID of the vehicle associated with the deficit        |
| amount       | integer  | Amount of the deficit or repayment                   |
| deficit_type | string   | Type of record: "deficit" or "repayment"             |

#### Example Response

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa7",
  "created_at": "2023-05-20T12:34:56.789Z",
  "driver": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "vehicle": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "amount": 5000,
  "deficit_type": "deficit"
}
```

#### Status Codes

- `201 Created`: Deficit record created successfully
- `404 Not Found`: Driver or vehicle not found
- `422 Unprocessable Entity`: Invalid request body

### Get Deficits

```http
GET /api/deficits/
```

Retrieve a list of all deficits with totals and breakdowns by driver and vehicle.

#### Query Parameters

| Parameter  | Type | Description                               | Required |
|------------|------|-------------------------------------------|----------|
| driver_id  | UUID | Filter deficits by specific driver        | No       |
| vehicle_id | UUID | Filter deficits by specific vehicle       | No       |

#### Example Requests

```http
GET /api/deficits/                                            # Get all deficits
GET /api/deficits/?driver_id=3fa85f64-5717-4562-b3fc-2c963f66afa6   # Filter by driver
GET /api/deficits/?vehicle_id=3fa85f64-5717-4562-b3fc-2c963f66afa6  # Filter by vehicle
GET /api/deficits/?driver_id=3fa85f64-5717-4562-b3fc-2c963f66afa6&vehicle_id=3fa85f64-5717-4562-b3fc-2c963f66afa6  # Filter by both
```

#### Response

The response contains a detailed summary of all relevant deficit records, including:

1. Overall totals
   - Total deficit amount
   - Total repaid amount
   - Current balance

2. Breakdown by driver
   - Driver information
   - Total deficit amount per driver
   - Total repaid amount per driver
   - Current balance per driver

3. Breakdown by vehicle
   - Vehicle information
   - Total deficit amount per vehicle
   - Total repaid amount per vehicle
   - Current balance per vehicle

4. List of individual deficit records

#### Example Response

```json
{
  "overall": {
    "total_deficit": 8000,
    "total_repaid": 3000,
    "balance": 5000
  },
  "by_driver": [
    {
      "driver_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "driver_name": "John Doe",
      "total_deficit": 8000,
      "total_repaid": 3000,
      "balance": 5000
    }
  ],
  "by_vehicle": [
    {
      "vehicle_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "vehicle_registration": "KAA 123B",
      "total_deficit": 8000,
      "total_repaid": 3000,
      "balance": 5000
    }
  ],
  "deficits": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa7",
      "created_at": "2023-05-20T12:34:56.789Z",
      "driver": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "vehicle": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "amount": 5000,
      "deficit_type": "deficit"
    },
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa8",
      "created_at": "2023-05-21T10:24:36.123Z",
      "driver": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "vehicle": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "amount": 3000,
      "deficit_type": "deficit"
    },
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa9",
      "created_at": "2023-05-22T09:15:42.456Z",
      "driver": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "vehicle": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "amount": 3000,
      "deficit_type": "repayment"
    }
  ]
}
```

## Frontend Integration

### Example: Creating a New Deficit

```typescript
// Function to create a new deficit record
async function createDeficit(deficit: {
  driver: string;
  vehicle: string;
  amount: number;
  deficit_type: 'deficit' | 'repayment';
}) {
  const response = await fetch('/api/deficits/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}` // Include auth token if required
    },
    body: JSON.stringify(deficit)
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create deficit');
  }

  return await response.json();
}

// Usage example
try {
  const newDeficit = await createDeficit({
    driver: '3fa85f64-5717-4562-b3fc-2c963f66afa6',
    vehicle: '3fa85f64-5717-4562-b3fc-2c963f66afa6',
    amount: 5000,
    deficit_type: 'deficit'
  });
  console.log('Deficit created:', newDeficit);
} catch (error) {
  console.error('Error creating deficit:', error);
}
```

### Example: Fetching Deficit Data

```typescript
// Function to fetch deficits with optional filtering
async function getDeficits(params?: {
  driver_id?: string;
  vehicle_id?: string;
}) {
  const queryParams = new URLSearchParams();
  
  if (params?.driver_id) {
    queryParams.set('driver_id', params.driver_id);
  }
  
  if (params?.vehicle_id) {
    queryParams.set('vehicle_id', params.vehicle_id);
  }
  
  const url = `/api/deficits/${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
  
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${token}` // Include auth token if required
    }
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch deficits');
  }
  
  return await response.json();
}

// Example usage: Get all deficits
try {
  const allDeficits = await getDeficits();
  console.log('All deficits:', allDeficits);
  
  // Access overall totals
  console.log('Overall balance:', allDeficits.overall.balance);
  
  // Access driver-specific data
  const driverSummaries = allDeficits.by_driver;
  console.log('Driver summaries:', driverSummaries);
  
  // Access vehicle-specific data
  const vehicleSummaries = allDeficits.by_vehicle;
  console.log('Vehicle summaries:', vehicleSummaries);
} catch (error) {
  console.error('Error fetching deficits:', error);
}

// Example usage: Get deficits for a specific driver
try {
  const driverDeficits = await getDeficits({
    driver_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6'
  });
  console.log('Driver deficits:', driverDeficits);
} catch (error) {
  console.error('Error fetching driver deficits:', error);
}
```

## Error Handling

The API returns standard HTTP error codes:

- `400 Bad Request`: Invalid request format
- `404 Not Found`: Driver or vehicle not found
- `422 Unprocessable Entity`: Validation error in request data
- `500 Internal Server Error`: Server-side error

Error responses include a detail message explaining the error:

```json
{
  "status": "error",
  "code": 404,
  "message": "Driver not found",
  "details": {
    "path": "/api/deficits/"
  }
}
``` 