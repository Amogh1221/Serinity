from fastapi.testclient import TestClient

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_patient_routes(client: TestClient, user_store, profile_store):
    # Login and get token
    from services.auth_service import get_password_hash, create_access_token
    user_id = user_store.create_user(
        username="routeuser",
        email="route@example.com",
        password_hash=get_password_hash("password123")
    )
    token = create_access_token(data={"sub": user_id, "username": "routeuser"})
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get patients
    response = client.get("/patients", headers=headers)
    assert response.status_code == 200
    # Should auto-create one since empty
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "routeuser"
    
    # Create new patient
    response = client.post(
        "/patients/create",
        json={"name": "New Patient", "age": 25, "gender": "Female", "primary_concern": "Stress"},
        headers=headers
    )
    assert response.status_code == 200
    patient_id = response.json()["patient_id"]
    
    # Check dashboard
    response = client.get(f"/patients/{patient_id}/dashboard", headers=headers)
    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["patient"]["name"] == "New Patient"

def test_chat_routes(client: TestClient, user_store):
    # Setup token
    from services.auth_service import get_password_hash, create_access_token
    user_id = user_store.create_user(
        username="chatuser",
        email="chat@example.com",
        password_hash=get_password_hash("password123")
    )
    token = create_access_token(data={"sub": user_id, "username": "chatuser"})
    headers = {"Authorization": f"Bearer {token}"}
    
    # Start session
    response = client.post("/start", headers=headers)
    assert response.status_code == 200
    data = response.json()
    session_id = data["session_id"]
    patient_id = data["patient_id"]
    assert data["assistant_message"] == "Mocked response from LLM1"
    
    # Send message
    response = client.post(
        "/chat_text",
        json={"session_id": session_id, "patient_id": patient_id, "message": "I feel anxious"},
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "CONTINUE"
    assert "Mocked response from LLM1" in data["assistant_message"]
    
    # End session
    response = client.post(
        "/end_session",
        json={"session_id": session_id, "patient_id": patient_id},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ended"}
