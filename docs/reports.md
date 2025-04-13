# Reports API Documentation

The Reports API provides endpoints for generating detailed performance reports for vehicles and drivers. Reports can be generated for individual entities or as combined reports for multiple vehicles and drivers.

## Endpoints

### Combined Reports

```http
GET /api/reports/combined
```

Generate a comprehensive performance report for multiple vehicles and/or drivers.

#### Query Parameters

- `start_date` (optional): Start date in YYYY-MM-DD format. Defaults to 30 days ago.
- `end_date` (optional): End date in YYYY-MM-DD format. Defaults to today.
- `vehicle_ids` (optional): Comma-separated list of vehicle IDs to include in the report.
- `driver_ids` (optional): Comma-separated list of driver IDs to include in the report.
- `format` (optional): Report format - either 'pdf' or 'html'. Defaults to 'pdf'.

#### Example Request

```http
GET /api/reports/combined?vehicle_ids=v1,v2&driver_ids=d1,d2&start_date=2024-03-01&end_date=2024-03-31&format=pdf
```

#### Report Contents

The combined report includes:

1. Overall Summary
   - Total collections
   - Total expenses
   - Net profit
   - Trip count
   - Active days
   - Utilization rate
   - Expense breakdown (fuel, repairs, other)

2. Vehicle Performance (for each vehicle)
   - Collections
   - Expenses
   - Trip count
   - Utilization rate
   - Driver performance breakdown

3. Driver Performance (for each driver)
   - Collections
   - Trip count
   - Average per trip
   - Collection efficiency
   - Vehicle usage
   - Route performance

4. Daily Performance
   - Collections per day
   - Expenses per day
   - Trips per day

### Individual Reports

#### Vehicle Report

```http
GET /api/reports/vehicle/{vehicle_id}
```

Generate a detailed report for a single vehicle.

#### Query Parameters

- `start_date` (optional): Start date in YYYY-MM-DD format
- `end_date` (optional): End date in YYYY-MM-DD format
- `format` (optional): Report format - 'pdf' or 'html'

#### Example Request

```http
GET /api/reports/vehicle/v1?start_date=2024-03-01&end_date=2024-03-31&format=pdf
```

#### Driver Report

```http
GET /api/reports/driver/{driver_id}
```

Generate a detailed report for a single driver.

#### Query Parameters

- `start_date` (optional): Start date in YYYY-MM-DD format
- `end_date` (optional): End date in YYYY-MM-DD format
- `format` (optional): Report format - 'pdf' or 'html'

#### Example Request

```http
GET /api/reports/driver/d1?start_date=2024-03-01&end_date=2024-03-31&format=pdf
```

## Frontend Integration

### Example Usage with Fetch API

```typescript
// Generate combined report
async function generateCombinedReport(params: {
  vehicleIds?: string[];
  driverIds?: string[];
  startDate?: string;
  endDate?: string;
  format?: 'pdf' | 'html';
}) {
  const queryParams = new URLSearchParams();
  
  if (params.vehicleIds?.length) {
    queryParams.set('vehicle_ids', params.vehicleIds.join(','));
  }
  if (params.driverIds?.length) {
    queryParams.set('driver_ids', params.driverIds.join(','));
  }
  if (params.startDate) {
    queryParams.set('start_date', params.startDate);
  }
  if (params.endDate) {
    queryParams.set('end_date', params.endDate);
  }
  if (params.format) {
    queryParams.set('format', params.format);
  }

  const response = await fetch(`/api/reports/combined?${queryParams}`);
  
  if (!response.ok) {
    throw new Error('Failed to generate report');
  }

  // For PDF format, create blob and download
  if (params.format === 'pdf') {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'report.pdf';
    a.click();
    window.URL.revokeObjectURL(url);
  } else {
    // For HTML format, you might want to display in a new window
    const html = await response.text();
    const win = window.open('', '_blank');
    win?.document.write(html);
  }
}

// Example usage
generateCombinedReport({
  vehicleIds: ['v1', 'v2'],
  driverIds: ['d1', 'd2'],
  startDate: '2024-03-01',
  endDate: '2024-03-31',
  format: 'pdf'
});
```

### Example Usage with React Query

```typescript
import { useQuery } from '@tanstack/react-query';

interface ReportParams {
  vehicleIds?: string[];
  driverIds?: string[];
  startDate?: string;
  endDate?: string;
  format?: 'pdf' | 'html';
}

function useGenerateReport(params: ReportParams) {
  return useQuery({
    queryKey: ['report', params],
    queryFn: async () => {
      const queryParams = new URLSearchParams();
      
      if (params.vehicleIds?.length) {
        queryParams.set('vehicle_ids', params.vehicleIds.join(','));
      }
      if (params.driverIds?.length) {
        queryParams.set('driver_ids', params.driverIds.join(','));
      }
      if (params.startDate) {
        queryParams.set('start_date', params.startDate);
      }
      if (params.endDate) {
        queryParams.set('end_date', params.endDate);
      }
      if (params.format) {
        queryParams.set('format', params.format);
      }

      const response = await fetch(`/api/reports/combined?${queryParams}`);
      
      if (!response.ok) {
        throw new Error('Failed to generate report');
      }

      return response;
    },
    enabled: false // Only generate when explicitly triggered
  });
}

// Example Component
function ReportGenerator() {
  const [selectedVehicles, setSelectedVehicles] = useState<string[]>([]);
  const [selectedDrivers, setSelectedDrivers] = useState<string[]>([]);
  
  const { refetch: generateReport, isLoading } = useGenerateReport({
    vehicleIds: selectedVehicles,
    driverIds: selectedDrivers,
    format: 'pdf'
  });

  const handleGenerateReport = async () => {
    const { data: response } = await generateReport();
    if (response) {
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'report.pdf';
      a.click();
      window.URL.revokeObjectURL(url);
    }
  };

  return (
    <div>
      {/* Vehicle and Driver selection UI */}
      <button 
        onClick={handleGenerateReport}
        disabled={isLoading}
      >
        {isLoading ? 'Generating...' : 'Generate Report'}
      </button>
    </div>
  );
}
```

## Error Handling

The API returns standard HTTP error codes:

- `400 Bad Request`: Invalid date format or missing required parameters
- `404 Not Found`: Vehicle or driver not found
- `500 Internal Server Error`: Server-side error during report generation

Error responses include a detail message explaining the error:

```json
{
  "detail": "Error message here"
}
``` 