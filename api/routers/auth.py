"""
Authentication Router
Handles JWT-based authentication, user registration, and OTP flows (signup, password reset, account deletion).
"""

from fastapi import APIRouter, HTTPException, status, Depends
from schemas.auth_schemas import SignupRequest, LoginRequest, TokenResponse, ResetPasswordRequest
from services.auth_service import get_password_hash, verify_password, create_access_token
from datetime import datetime, timedelta, timezone
from api.dependencies import profile_store, get_user_store, get_current_user
from persistence.user_store import SQLiteUserStore

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup", response_model=TokenResponse)
def signup(request: SignupRequest, user_store: SQLiteUserStore = Depends(get_user_store)):
    """
    Register a new user and create an initial patient profile.
    Returns a JWT access token upon successful registration.
    """
    # Check if user exists
    if user_store.get_user_by_email(request.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if user_store.get_user_by_username(request.username):
        raise HTTPException(status_code=400, detail="Username already taken")

    # Hash password
    hashed_password = get_password_hash(request.password)

    # Create user
    user_id = user_store.create_user(
        username=request.username,
        email=request.email,
        password_hash=hashed_password,
        nationality=request.nationality,
        emergency_contact_name=request.emergency_contact_name,
        emergency_contact_phone=request.emergency_contact_phone
    )

    # Create patient profile linked to user_id
    patient_id = profile_store.create_patient(
        name=request.name,
        age=request.age,
        gender=request.gender,
        primary_concern=request.primary_concern,
        user_id=user_id
    )

    # Generate token
    access_token = create_access_token(data={"sub": user_id, "username": request.username})
    
    return TokenResponse(access_token=access_token, user_id=user_id)


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, user_store: SQLiteUserStore = Depends(get_user_store)):
    """
    Authenticate a user using username or email and password.
    Returns a JWT access token.
    """
    if "@" in request.username:
        user = user_store.get_user_by_email(request.username)
    else:
        user = user_store.get_user_by_username(request.username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(data={"sub": user["id"], "username": user["username"]})
    return TokenResponse(access_token=access_token, user_id=user["id"])

@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, user_store: SQLiteUserStore = Depends(get_user_store)):
    user = user_store.get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=404, detail="No account found with that email address.")

    # Hash new password
    hashed_password = get_password_hash(request.new_password)
    user_store.update_password(request.email, hashed_password)
    
    return {"message": "Password successfully updated."}


@router.post("/delete-account")
def delete_account(
    user_store: SQLiteUserStore = Depends(get_user_store),
    current_user: dict = Depends(get_current_user)
):
    user = user_store.get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete patient associated with user first
    patients = profile_store.list_patients_for_user(user["id"])
    for p in patients:
        profile_store.delete_patient(p["patient_id"])

    # Delete user
    user_store.delete_user(user["id"])

    return {"message": "Account has been successfully deleted."}
