import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from typing import List
from urllib.parse import quote

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "Matatu Management API"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "risen_db")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")

    # Database URL
    @property
    def DATABASE_URL(self) -> str:
        # URL-encode the password to handle special characters like &
        encoded_password = quote(self.POSTGRES_PASSWORD)
        return f"postgresql://{self.POSTGRES_USER}:{encoded_password}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Supabase (for backward compatibility)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # Email/SMTP Configuration
    # For Gmail/Outlook (port 587): SMTP_TLS=True, SMTP_SSL=False
    # For SSL-only providers (port 465): SMTP_TLS=False, SMTP_SSL=True
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "True").lower() == "true"
    SMTP_SSL: bool = os.getenv("SMTP_SSL", "False").lower() == "true"
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAILS_FROM_EMAIL: str = os.getenv("EMAILS_FROM_EMAIL", "")
    EMAILS_FROM_NAME: str = os.getenv("EMAILS_FROM_NAME", PROJECT_NAME)

    # Password Reset Configuration
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = int(os.getenv("EMAIL_RESET_TOKEN_EXPIRE_HOURS", "24"))
    EMAIL_TEMPLATES_DIR: str = "app/templates"

    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_SSL: bool = os.getenv("REDIS_SSL", "False").lower() == "true"

    # Cache Configuration
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "3600"))  # Default 1 hour
    CACHE_PREFIX: str = os.getenv("CACHE_PREFIX", "matatu:")

    # Redis URL for different connection methods
    @property
    def REDIS_URL(self) -> str:
        """Redis URL for redis-py"""
        password_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        ssl_part = "?ssl=true" if self.REDIS_SSL else ""
        return f"redis://redis{self.REDIS_DB}{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}{ssl_part}"

    class Config:
        case_sensitive = True

# Create settings instance
settings = Settings() 