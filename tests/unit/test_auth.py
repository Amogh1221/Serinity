from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from persistence.user_store import SQLiteUserStore

def test_request_signup_otp(client: TestClient, user_store: SQLiteUserStore):
    response = client.post(
        "/api/auth/signup/request-otp",
        json={"email": "test@example.com", "username": "testuser"}
    )
    assert response.status_code == 200
    assert response.json() == {"message": "OTP has been sent to your email."}
    
    otp_record = user_store.get_otp("test@example.com")
    assert otp_record is not None
    assert len(otp_record["otp_code"]) == 6

def test_signup(client: TestClient, user_store: SQLiteUserStore):
    # Pre-populate OTP
    otp_code = "123456"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    user_store.store_otp("testsignup@example.com", otp_code, expires_at)
    
    response = client.post(
        "/api/auth/signup",
        json={
            "name": "Test User",
            "username": "testsignup",
            "email": "testsignup@example.com",
            "password": "strongpassword123",
            "otp_code": otp_code,
            "age": 30,
            "gender": "Male",
            "nationality": "US",
            "primary_concern": "Anxiety"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "user_id" in data
    
    # Verify user exists
    user = user_store.get_user_by_email("testsignup@example.com")
    assert user is not None
    assert user["username"] == "testsignup"

def test_login(client: TestClient, user_store: SQLiteUserStore):
    # Create user first
    from services.auth_service import get_password_hash
    user_store.create_user(
        username="loginuser",
        email="login@example.com",
        password_hash=get_password_hash("password123")
    )
    
    # Test valid login
    response = client.post(
        "/api/auth/login",
        json={"username": "loginuser", "password": "password123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    
    # Test invalid login
    response = client.post(
        "/api/auth/login",
        json={"username": "loginuser", "password": "wrongpassword"}
    )
    assert response.status_code == 401

def test_forgot_password_flow(client: TestClient, user_store: SQLiteUserStore):
    # Create user
    from services.auth_service import get_password_hash
    user_store.create_user(
        username="forgotuser",
        email="forgot@example.com",
        password_hash=get_password_hash("oldpassword")
    )
    
    # Request OTP
    response = client.post(
        "/api/auth/forgot-password",
        json={"email": "forgot@example.com"}
    )
    assert response.status_code == 200
    
    otp_record = user_store.get_otp("forgot@example.com")
    assert otp_record is not None
    otp_code = otp_record["otp_code"]
    
    # Verify OTP only
    response = client.post(
        "/api/auth/verify-otp",
        json={"email": "forgot@example.com", "otp_code": otp_code}
    )
    assert response.status_code == 200
    
    # Re-store OTP since verify-otp might delete or we might need it for reset
    # Wait, looking at verify_otp_only, it doesn't delete it.
    # Let's reset password
    response = client.post(
        "/api/auth/reset-password",
        json={"email": "forgot@example.com", "otp_code": otp_code, "new_password": "newpassword123"}
    )
    assert response.status_code == 200
    
    # Verify login with new password
    response = client.post(
        "/api/auth/login",
        json={"username": "forgotuser", "password": "newpassword123"}
    )
    assert response.status_code == 200

def test_delete_account_flow(client: TestClient, user_store: SQLiteUserStore):
    from services.auth_service import get_password_hash
    user_store.create_user(
        username="deleteuser",
        email="delete@example.com",
        password_hash=get_password_hash("password123")
    )
    
    # Login to get token
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "deleteuser", "password": "password123"}
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Request delete OTP
    resp1 = client.post("/api/auth/delete-account/request-otp", headers=headers)
    assert resp1.status_code == 200
    
    otp_record = user_store.get_otp("delete@example.com")
    otp_code = otp_record["otp_code"]
    
    # Verify delete
    resp2 = client.post(
        "/api/auth/delete-account/verify",
        json={"otp_code": otp_code},
        headers=headers
    )
    assert resp2.status_code == 200
    
    # Verify user is gone
    assert user_store.get_user_by_email("delete@example.com") is None
