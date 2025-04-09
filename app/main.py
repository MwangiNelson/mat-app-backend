from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api import auth, vehicles, drivers, operations, locations, routes, trips, reports, dashboard
from app.schemas.user import ErrorResponse
from app.core.utils import DateTimeEncoder
import json
from datetime import datetime

class CustomJSONResponse(JSONResponse):
    """Custom JSONResponse that handles datetime serialization"""
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            cls=DateTimeEncoder,
            separators=(",", ":"),
        ).encode("utf-8")

app = FastAPI(
    title="Matatu Management API",
    description="Backend API for the Matatu Management System",
    version="1.0.0",
    default_response_class=CustomJSONResponse,  # Use our custom response class by default
)

# Custom OpenAPI schema for better API documentation
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Customize security definitions
    openapi_schema["components"]["securitySchemes"] = {
        "EmailPassword": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT bearer token authentication. Get token from /api/auth/login endpoint."
        }
    }
    
    # Set global security
    openapi_schema["security"] = [{"EmailPassword": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Custom exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with standard format"""
    status_code = exc.status_code
    detail = exc.detail
    
    # If detail is already a dict (from create_auth_error), use it directly
    if isinstance(detail, dict) and "status" in detail and "code" in detail and "message" in detail:
        return CustomJSONResponse(status_code=status_code, content=detail)
    
    # Special handling for 404 errors
    if status_code == 404:
        return CustomJSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                status="error",
                code=status_code,
                message="Resource not found",
                details={"path": request.url.path},
                errors=[{"type": "not_found", "message": str(detail)}]
            ).dict()
        )
    
    return CustomJSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            status="error",
            code=status_code,
            message=str(detail),
            details={"path": request.url.path}
        ).dict()
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed feedback"""
    errors = []
    for error in exc.errors():
        error_obj = {
            "type": error["type"],
            "field": ".".join(str(loc) for loc in error["loc"]) if error["loc"] else None,
            "message": error["msg"]
        }
        errors.append(error_obj)
    
    return CustomJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            status="error",
            code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Validation error",
            details={"path": request.url.path},
            errors=errors
        ).dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    return CustomJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            status="error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Internal server error",
            details={"path": request.url.path}
        ).dict()
    )

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with specific frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(vehicles.router, prefix="/api/vehicles", tags=["Vehicles"])
app.include_router(drivers.router, prefix="/api/drivers", tags=["Drivers"])
app.include_router(routes.router, prefix="/api/routes", tags=["Routes"])
app.include_router(trips.router, prefix="/api/trips", tags=["Trips"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(operations.router, prefix="/api/operations", tags=["Operations"])
app.include_router(locations.router, prefix="/api/locations", tags=["Locations"])

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Matatu Management API",
        "docs": "/docs",
        "redoc": "/redoc"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 