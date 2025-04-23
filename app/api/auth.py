from fastapi import APIRouter, Depends, HTTPException, status, Security
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from datetime import timedelta, datetime
from typing import Any, Dict, List

from app.core.db import supabase
from app.core.security import (
    create_access_token, 
    create_refresh_token, 
    get_current_user, 
    get_current_active_user,
    verify_password,
    get_password_hash,
    check_admin_role,
    email_password_scheme
)
from app.core.config import settings
from app.schemas.user import (
    UserCreate, 
    UserResponse, 
    UserUpdate, 
    Token, 
    RefreshToken,
    TokenPayload,
    LoginRequest,
    ErrorResponse
)
from app.core.utils import DateTimeEncoder
import json
from jose import jwt

router = APIRouter()

def create_auth_error(status_code: int, message: str, error_type: str, details: Dict = None) -> HTTPException:
    """Create standardized authentication error response"""
    # Ensure message is a string
    message = str(message)
    
    error_response = ErrorResponse(
        status="error",
        code=status_code,
        message=message,
        details=details,
        errors=[{"type": error_type, "message": message}]
    )
    
    # Convert datetime to string in ISO format
    content = json.loads(
        json.dumps(error_response.dict(), cls=DateTimeEncoder)
    )
    
    return HTTPException(
        status_code=status_code,
        detail=content
    )

@router.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate) -> Any:
    """
    Register a new user.
    """
    # Check if user already exists
    user_data = supabase.table("users").select("*").eq("email", user_in.email).execute()
    if user_data.data:
        raise create_auth_error(
            status_code=status.HTTP_409_CONFLICT,
            message="An account with this email already exists. Please use a different email or login instead.",
            error_type="account_exists",
            details={"email": user_in.email}
        )
    
    # Validate password strength
    if len(user_in.password) < 8:
        raise create_auth_error(
            status_code=status.HTTP_400_BAD_REQUEST, 
            message="Password must be at least 8 characters long",
            error_type="invalid_password"
        )
    
    # Create user in Supabase Auth
    try:
        auth_user = supabase.auth.sign_up({
            "email": user_in.email,
            "password": user_in.password
        })
        
        user_id = auth_user.user.id
        
        # Create user in users table
        user_data = {
            "id": user_id,
            "full_name": user_in.full_name,
            "email": user_in.email,
            "role": user_in.role,
            "phone": user_in.phone
        }
        
        response = supabase.table("users").insert(user_data).execute()
        
        if not response.data:
            # If users table insertion fails, we should handle this case (could clean up auth user)
            raise create_auth_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="There was a problem creating your account. Please try again later.",
                error_type="profile_creation_failed"
            )
        
        return response.data[0]
    
    except Exception as e:
        error_message = str(e)
        
        # Handle common Supabase auth errors
        if "already registered" in error_message.lower():
            raise create_auth_error(
                status_code=status.HTTP_409_CONFLICT,
                message="This email is already registered. Please use a different email or login instead.",
                error_type="account_exists", 
                details={"email": user_in.email}
            )
        elif "password" in error_message.lower():
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Your password doesn't meet the security requirements. Please choose a stronger password.",
                error_type="invalid_password"
            )
        elif "email" in error_message.lower():
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Please enter a valid email address.",
                error_type="invalid_email",
                details={"email": user_in.email}
            )
        
        # Generic error
        raise create_auth_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Registration failed. Please try again later.",
            error_type="registration_failed",
            details={"error": error_message}
        )

@router.post("/login", response_model=Token, operation_id="login")
async def login(login_data: LoginRequest) -> Any:
    """
    Login with email and password to get access token.
    
    Returns a token object containing:
    - access_token: JWT token for API access
    - refresh_token: Token to get new access tokens
    - token_type: Type of token (bearer)
    """
    try:
        # First check if user exists in our database
        user_check = supabase.table("users").select("*").eq("email", login_data.email).execute()
        if not user_check.data:
            raise create_auth_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="No account found with this email address. Please register first.",
                error_type="account_not_found",
                details={"email": login_data.email}
            )

        # Attempt to authenticate with Supabase
        try:
            auth_response = supabase.auth.sign_in_with_password({
                "email": login_data.email,
                "password": login_data.password
            })
        except Exception as auth_error:
            error_message = str(auth_error).lower()
            
            # Handle specific authentication errors
            if "invalid login" in error_message or "invalid credentials" in error_message:
                raise create_auth_error(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    message="Incorrect email or password. Please try again.",
                    error_type="invalid_credentials"
                )
            elif "not confirmed" in error_message:
                raise create_auth_error(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    message="Your email address has not been verified. Please check your inbox for a verification email and follow the instructions.",
                    error_type="email_not_verified"
                )
            elif "too many requests" in error_message:
                raise create_auth_error(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    message="Too many login attempts. For security reasons, please wait a few minutes before trying again.",
                    error_type="rate_limited"
                )
            
            # Generic authentication error
            raise create_auth_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Login failed. Please check your credentials and try again.",
                error_type="authentication_failed", 
                details={"error": error_message}
            )
        
        user_id = auth_response.user.id
        
        # Get user from database to check role
        user_data = supabase.table("users").select("*").eq("id", user_id).execute()
        
        if not user_data.data:
            raise create_auth_error(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Your account exists but your profile is missing. Please contact support.",
                error_type="profile_not_found"
            )
        
        user = user_data.data[0]
        
        # Create JWT tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user_id, "role": user["role"]},
            expires_delta=access_token_expires,
        )
        
        refresh_token = create_refresh_token(
            data={"sub": user_id, "role": user["role"]}
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        raise create_auth_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Unable to log you in at this time. Please try again later.",
            error_type="login_failed",
            details={"error": str(e)}
        )

@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: RefreshToken) -> Any:
    """
    Refresh access token.
    """
    try:
        payload = jwt.decode(
            refresh_token.refresh_token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        
        # Create new access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": token_data.sub, "role": token_data.role},
            expires_delta=access_token_expires,
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token.refresh_token,
            "token_type": "bearer",
        }
    
    except (jwt.JWTError, ValueError):
        raise create_auth_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Invalid refresh token",
            error_type="invalid_token"
        )

@router.post("/forgot-password")
async def forgot_password(email: str) -> Any:
    """
    Send password reset email.
    """
    try:
        # Check if user exists first
        user_check = supabase.table("users").select("id").eq("email", email).execute()
        if not user_check.data:
            # For security reasons, still return success even if email doesn't exist
            return {"message": "If your email is registered, you will receive a password reset link shortly."}
            
        supabase.auth.reset_password_email(email)
        return {"message": "If your email is registered, you will receive a password reset link shortly."}
    except Exception as e:
        raise create_auth_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="We couldn't send a reset email at this time. Please try again later or contact support.",
            error_type="reset_email_failed",
            details={"error": str(e)}
        )

@router.post("/reset-password")
async def reset_password(new_password: str, token: str) -> Any:
    """
    Reset password with token.
    """
    try:
        # Validate password strength
        if len(new_password) < 8:
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST, 
                message="Your new password must be at least 8 characters long",
                error_type="invalid_password"
            )
            
        supabase.auth.update_user(
            {
                "password": new_password
            }
        )
        return {"message": "Your password has been updated successfully. You can now log in with your new password."}
    except Exception as e:
        error_message = str(e).lower()
        
        if "token" in error_message:
            raise create_auth_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Your password reset link has expired or is invalid. Please request a new one.",
                error_type="invalid_reset_token"
            )
        elif "password" in error_message:
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Your password doesn't meet the security requirements. Please choose a stronger password.",
                error_type="invalid_password"
            )
        else:
            raise create_auth_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="We couldn't reset your password. Please try again or request a new reset link.",
                error_type="password_reset_failed",
                details={"error": str(e)}
            )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_active_user)) -> Any:
    """
    Get current user info.
    """
    user_data = supabase.table("users").select("*").eq("id", current_user.user_id).execute()
    
    if not user_data.data:
        raise create_auth_error(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            error_type="user_not_found"
        )
    
    return user_data.data[0]

@router.put("/me", response_model=UserResponse)
async def update_current_user_info(
    user_update: UserUpdate,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Update current user info.
    """
    # Filter out None values
    update_data = {k: v for k, v in user_update.dict().items() if v is not None}
    
    if not update_data:
        raise create_auth_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="No fields to update",
            error_type="no_update_data"
        )
    
    response = supabase.table("users").update(update_data).eq("id", current_user.user_id).execute()
    
    if not response.data:
        raise create_auth_error(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found or nothing to update",
            error_type="update_failed"
        )
    
    return response.data[0]

@router.get("/test-auth")
async def test_auth(current_user = Depends(get_current_active_user)) -> dict:
    """
    Test endpoint to verify authentication is working.
    This endpoint requires a valid JWT token.
    """
    return {
        "message": "Authentication successful",
        "user_id": current_user.user_id,
        "role": current_user.role
    }

@router.get("/admin-only")
async def admin_only(current_user = Depends(check_admin_role)) -> dict:
    """
    Test endpoint for admin-only access.
    This endpoint requires a valid JWT token AND admin role.
    """
    return {
        "message": "Admin access granted",
        "user_id": current_user.user_id,
        "role": current_user.role
    } 