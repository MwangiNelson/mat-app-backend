from fastapi import APIRouter, Depends, HTTPException, Security
from starlette import status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from datetime import timedelta, datetime
from typing import Any, Dict, List

# from app.core.db import supabase  # Removed Supabase dependency
from app.models import get_db  # Add SQLAlchemy dependency
from app.models.models import User, PasswordResetToken  # Add User and PasswordResetToken models
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
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
    PasswordResetRequest,
    PasswordResetConfirm,
    ErrorResponse
)
from app.core.utils import DateTimeEncoder
from app.core.email import email_service
import json
import secrets
import logging
from datetime import timezone
from jose import jwt

logger = logging.getLogger(__name__)

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
async def register(user_in: UserCreate, db: Session = Depends(get_db)) -> Any:
    """
    Register a new user.
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
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

    # Create user in local database
    try:
        # Hash the password
        hashed_password = get_password_hash(user_in.password)

        # Create new user
        new_user = User(
            full_name=user_in.full_name,
            email=user_in.email,
            password_hash=hashed_password,
            role=user_in.role,
            phone=user_in.phone
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return UserResponse(
            id=str(new_user.id),
            full_name=new_user.full_name,
            email=new_user.email,
            role=new_user.role,
            phone=new_user.phone,
            created_at=new_user.created_at,
            updated_at=new_user.updated_at
        )

    except IntegrityError as e:
        db.rollback()
        raise create_auth_error(
            status_code=status.HTTP_409_CONFLICT,
            message="An account with this email already exists.",
            error_type="account_exists",
            details={"email": user_in.email}
        )
    except Exception as e:
        db.rollback()
        raise create_auth_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Registration failed. Please try again later.",
            error_type="registration_failed",
            details={"error": str(e)}
        )

@router.post("/login", response_model=Token, operation_id="login")
async def login(login_data: LoginRequest, db: Session = Depends(get_db)) -> Any:
    """
    Login with email and password to get access token.

    Returns a token object containing:
    - access_token: JWT token for API access
    - refresh_token: Token to get new access tokens
    - token_type: Type of token (bearer)
    """
    try:
        # Check if user exists in our database
        user = db.query(User).filter(User.email == login_data.email).first()

        # Verify password (only if user exists and has a valid password hash)
        if not user or not user.password_hash:
            # Generic error message for security - don't reveal if account exists
            raise create_auth_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Invalid email or password. Please try again.",
                error_type="invalid_credentials"
            )

        # Verify password with error handling
        try:
            password_valid = verify_password(login_data.password, user.password_hash)
            if not password_valid:
                raise create_auth_error(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    message="Invalid email or password. Please try again.",
                    error_type="invalid_credentials"
                )
        except Exception as password_error:
            # Handle corrupted hash or other password verification errors
            logger.error(f"Password verification error for user {login_data.email}: {str(password_error)}")
            raise create_auth_error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Invalid email or password. Please try again.",
                error_type="invalid_credentials"
            )

        # Create JWT tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "role": user.role},
            expires_delta=access_token_expires,
        )

        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "role": user.role}
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
async def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)) -> Any:
    """
    Request password reset by generating a token and sending email.
    Always returns success for security reasons, regardless of whether email exists.
    """
    try:
        # Check if user exists
        user = db.query(User).filter(User.email == request.email).first()

        if user:
            # Generate a simple 6-digit reset code
            reset_token = f"{secrets.randbelow(900000) + 100000:06d}"

            # Calculate expiration time
            expires_at = datetime.utcnow() + timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)

            # Create password reset token record
            reset_token_record = PasswordResetToken(
                user_id=user.id,
                token=reset_token,
                expires_at=expires_at
            )

            db.add(reset_token_record)
            db.commit()

            # Try to send email (but don't fail if email fails)
            email_sent = await email_service.send_password_reset_email(
                email_to=user.email,
                reset_token=reset_token
            )

            if not email_sent:
                # Log that email failed but continue (token is still stored)
                # User can manually enter the token
                pass  # Email service already logs the error

        # Always return success for security reasons
        return {
            "message": "If your email is registered, you will receive a password reset code shortly. Please check your email.",
            "note": "If you don't receive an email, you can manually enter the 6-digit reset code that was generated."
        }

    except Exception as e:
        # Log the error but still return success for security
        # Don't reveal whether the email exists or not
        return {
            "message": "If your email is registered, you will receive a password reset code shortly. Please check your email.",
            "note": "If you don't receive an email, you can manually enter the 6-digit reset code that was generated."
        }

@router.post("/reset-password")
async def reset_password(request: PasswordResetConfirm, db: Session = Depends(get_db)) -> Any:
    """
    Reset password using a valid 6-digit reset code.
    No authentication required - uses email + token validation.
    """
    try:
        # Validate password strength
        if len(request.new_password) < 8:
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Your new password must be at least 8 characters long",
                error_type="invalid_password"
            )

        # Find the reset token
        reset_token_record = db.query(PasswordResetToken).filter(
            PasswordResetToken.token == request.token
        ).first()

        if not reset_token_record:
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Invalid or expired reset code. Please request a new password reset.",
                error_type="invalid_token"
            )

        # Check if token has expired (use timezone-aware datetime)
        current_time = datetime.now(timezone.utc)
        if current_time > reset_token_record.expires_at:
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Reset code has expired. Please request a new password reset.",
                error_type="expired_token"
            )

        # Check if token has already been used
        if reset_token_record.used_at is not None:
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Reset code has already been used. Please request a new password reset.",
                error_type="used_token"
            )

        # Get the user and verify email matches
        user = db.query(User).filter(User.id == reset_token_record.user_id).first()
        if not user:
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="User not found. Please request a new password reset.",
                error_type="user_not_found"
            )

        # Verify the email matches the user associated with the token
        if user.email.lower() != request.email.lower():
            raise create_auth_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="The reset code doesn't match this email address. Please check your email and try again.",
                error_type="email_mismatch"
            )

        # Hash the new password
        hashed_password = get_password_hash(request.new_password)

        # Update user's password
        user.password_hash = hashed_password
        user.updated_at = datetime.now(timezone.utc)

        # Mark token as used
        reset_token_record.used_at = datetime.now(timezone.utc)

        # Commit changes
        db.commit()

        return {
            "message": "Password has been successfully reset. You can now log in with your new password.",
            "email": request.email
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise create_auth_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="We couldn't reset your password. Please try again or request a new reset link.",
            error_type="password_reset_failed",
            details={"error": str(e)}
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_active_user), db: Session = Depends(get_db)) -> Any:
    """
    Get current user info.
    """
    user = db.query(User).filter(User.id == current_user.user_id).first()

    if not user:
        raise create_auth_error(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            error_type="user_not_found"
        )

    return UserResponse(
        id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        phone=user.phone,
        created_at=user.created_at,
        updated_at=user.updated_at
    )

@router.put("/me", response_model=UserResponse)
async def update_current_user_info(
    user_update: UserUpdate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
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

    # Get user
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user:
        raise create_auth_error(
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            error_type="user_not_found"
        )

    # Update user fields
    for field, value in update_data.items():
        if hasattr(user, field):
            setattr(user, field, value)

    try:
        db.commit()
        db.refresh(user)

        return UserResponse(
            id=str(user.id),
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            phone=user.phone,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    except Exception as e:
        db.rollback()
        raise create_auth_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update user information",
            error_type="update_failed",
            details={"error": str(e)}
        )

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