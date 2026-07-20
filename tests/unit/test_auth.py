from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from persistence.user_store import SQLiteUserStore



def test_signup(client: TestClient, user_store: SQLiteUserStore):
    response = client.post(
        "/api/auth/signup",
        json={
            "name": "Test User",
            "username": "testsignup",
            "email": "testsignup@example.com",
            "password": "strongpassword123",
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
    
    # Let's reset password directly
    response = client.post(
        "/api/auth/reset-password",
        json={"email": "forgot@example.com", "new_password": "newpassword123"}
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
    
    # Verify delete
    resp2 = client.post(
        "/api/auth/delete-account",
        headers=headers
    )
    assert resp2.status_code == 200
    
    # Verify user is gone
    assert user_store.get_user_by_email("delete@example.com") is None
