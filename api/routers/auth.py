"""
Authentication Router
Handles JWT-based authentication, user registration, and OTP flows (signup, password reset, account deletion).
"""

from fastapi import APIRouter, HTTPException, status, Depends
from schemas.auth_schemas import SignupRequest, SignupOtpRequest, LoginRequest, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest, DeleteAccountVerifyRequest, VerifyOtpRequest
from services.auth_service import get_password_hash, verify_password, create_access_token
from services.email_service import send_otp_email
import secrets
from datetime import datetime, timedelta, timezone
from api.dependencies import profile_store, get_user_store, get_current_user
from persistence.user_store import SQLiteUserStore

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup/request-otp")
def request_signup_otp(request: SignupOtpRequest, user_store: SQLiteUserStore = Depends(get_user_store)):
    """
    Check if email and username are available, then generate and send an OTP for signup verification.
    """
    if user_store.get_user_by_email(request.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if user_store.get_user_by_username(request.username):
        raise HTTPException(status_code=400, detail="Username already taken")

    # Generate 6 digit secure OTP
    otp_code = str(secrets.randbelow(1000000)).zfill(6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    user_store.store_otp(request.email, otp_code, expires_at)
    
    send_otp_email(
        to_email=request.email,
        subject="Your Signup Verification Code",
        otp_code=otp_code,
        body_text=f"Your Serinity signup verification code is: {otp_code}\nThis code will expire in 10 minutes."
    )

    return {"message": "OTP has been sent to your email."}

@router.post("/signup", response_model=TokenResponse)
def signup(request: SignupRequest, user_store: SQLiteUserStore = Depends(get_user_store)):
    """
    Register a new user and create an initial patient profile.
    Returns a JWT access token upon successful registration.
    """
    # Verify OTP first
    otp_record = user_store.get_otp(request.email)
    if not otp_record or otp_record["otp_code"] != request.otp_code:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    expires_at = datetime.fromisoformat(otp_record["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        user_store.delete_otp(request.email)
        raise HTTPException(status_code=400, detail="OTP has expired")

    # Check if user exists (double check just in case)
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
    
    # Delete OTP to prevent reuse
    user_store.delete_otp(request.email)

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

@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, user_store: SQLiteUserStore = Depends(get_user_store)):
    """
    Initiates the password reset process by generating a 6-digit OTP code and sending it via email.
    """
    user = user_store.get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=404, detail="No account found with that email address.")

    # Generate 6 digit secure OTP
    otp_code = str(secrets.randbelow(1000000)).zfill(6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    user_store.store_otp(request.email, otp_code, expires_at)

    send_otp_email(
        to_email=request.email,
        subject="Your Password Reset OTP",
        otp_code=otp_code,
        body_text=f"Your verification code to reset your password is: {otp_code}"
    )

    return {"message": "If that email exists, an OTP has been sent."}

@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, user_store: SQLiteUserStore = Depends(get_user_store)):
    otp_record = user_store.get_otp(request.email)
    
    if not otp_record or otp_record["otp_code"] != request.otp_code:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    expires_at = datetime.fromisoformat(otp_record["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        user_store.delete_otp(request.email)
        raise HTTPException(status_code=400, detail="OTP has expired")

    # Hash new password
    hashed_password = get_password_hash(request.new_password)
    user_store.update_password(request.email, hashed_password)

    # Delete OTP to prevent reuse
    user_store.delete_otp(request.email)

@router.post("/verify-otp")
def verify_otp_only(request: VerifyOtpRequest, user_store: SQLiteUserStore = Depends(get_user_store)):
    """Verify OTP only (no password change) — gates the new-password step on the frontend."""
    otp_record = user_store.get_otp(request.email)
    if not otp_record or otp_record["otp_code"] != request.otp_code:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    expires_at = datetime.fromisoformat(otp_record["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        user_store.delete_otp(request.email)
        raise HTTPException(status_code=400, detail="OTP has expired")
    return {"message": "OTP verified. You may now set a new password."}


@router.post("/delete-account/request-otp")
def request_delete_account_otp(
    user_store: SQLiteUserStore = Depends(get_user_store),
    current_user: dict = Depends(get_current_user)
):
    user = user_store.get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp_code = str(secrets.randbelow(1000000)).zfill(6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    user_store.store_otp(user["email"], otp_code, expires_at)

    send_otp_email(
        to_email=user["email"],
        subject="Account Deletion OTP",
        otp_code=otp_code,
        body_text=f"Your verification code to delete your account is: {otp_code}\nIf you did not request this, please ignore this email."
    )

    return {"message": "OTP has been sent to your email."}

@router.post("/delete-account/verify")
def verify_delete_account(
    request: DeleteAccountVerifyRequest,
    user_store: SQLiteUserStore = Depends(get_user_store),
    current_user: dict = Depends(get_current_user)
):
    user = user_store.get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp_record = user_store.get_otp(user["email"])
    if not otp_record or otp_record["otp_code"] != request.otp_code:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    expires_at = datetime.fromisoformat(otp_record["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        user_store.delete_otp(user["email"])
        raise HTTPException(status_code=400, detail="OTP has expired")

    # Delete patient associated with user first
    patients = profile_store.list_patients_for_user(user["id"])
    for p in patients:
        profile_store.delete_patient(p["patient_id"])

    # Delete user
    user_store.delete_user(user["id"])

    # Clear OTP
    user_store.delete_otp(user["email"])

    return {"message": "Account has been successfully deleted."}
