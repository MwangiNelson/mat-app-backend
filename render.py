import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    # Get port from environment variable or default to 10000
    port = int(os.environ.get("PORT", 10000))
    
    # Start server
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Bind to all network interfaces
        port=port,
        log_level="info"
    ) 