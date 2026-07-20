from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class SignupOtpRequest(BaseModel):
    email: EmailStr
    username: str

class SignupRequest(BaseModel):
    name: str
    username: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    otp_code: str
    age: Optional[int] = Field(None, ge=5, le=99)
    gender: str
    nationality: str
    primary_concern: str
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp_code: str
    new_password: str = Field(..., min_length=8)

class DeleteAccountVerifyRequest(BaseModel):
    otp_code: str

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp_code: str
