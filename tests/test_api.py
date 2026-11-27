import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-12345678"

from app.database import Base, get_db
from app.main import app

# Create a shared in-memory SQLite database for testing using StaticPool
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_and_audit_flow():
    # 1. Bootstrap admin with 24bcs252@iiitdmj.ac.in
    res = client.post(
        "/admin/bootstrap",
        data={
            "email": "24bcs252@iiitdmj.ac.in",
            "password": "AdminPassword123!",
            "key": "test-secret-key-for-unit-tests-12345678",
        },
    )
    assert res.status_code == 201
    assert res.json()["role"] == "admin"
    assert res.json()["email"] == "24bcs252@iiitdmj.ac.in"

    # 2. Login as admin
    login_res = client.post(
        "/auth/login",
        json={"email": "24bcs252@iiitdmj.ac.in", "password": "AdminPassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    assert token is not None

    headers = {"Authorization": f"Bearer {token}"}

    # 3. Create an authorized iiitdmj user
    user_res = client.post(
        "/admin/users",
        headers=headers,
        data={
            "email": "professor@iiitdmj.ac.in",
            "password": "ProfPassword123!",
            "role": "faculty",
            "display_name": "Prof. Sharma",
        },
    )
    assert user_res.status_code == 201

    # 4. Check audit logs (Requirement 7)
    audit_res = client.get("/admin/audit-logs", headers=headers)
    assert audit_res.status_code == 200
    actions = [log["action"] for log in audit_res.json()]
    assert "BOOTSTRAP" in actions
    assert "LOGIN" in actions
    assert "CREATE_USER" in actions


def test_domain_restriction_enforced():
    # Attempting to access or register with a non-iiitdmj.ac.in email must be rejected with 403
    bad_login = client.post(
        "/auth/login",
        json={"email": "attacker@gmail.com", "password": "password"},
    )
    assert bad_login.status_code == 403
    assert "iiitdmj.ac.in" in bad_login.json()["detail"]


def test_feedback_flow():
    # Submit feedback using iiitdmj account
    fb_res = client.post(
        "/feedback",
        headers={"X-User-Email": "24bcs252@iiitdmj.ac.in"},
        json={
            "question": "What is the tuition deadline?",
            "answer": "The indexed sources do not contain enough information.",
            "rating": -1,
            "comment": "Please add the academic calendar 2026-2027.",
        },
    )
    assert fb_res.status_code == 201
    fb_id = fb_res.json()["id"]

    # Review feedback by admin
    admin_fb_res = client.get("/admin/feedback", headers={"X-User-Email": "24bcs252@iiitdmj.ac.in"})
    assert admin_fb_res.status_code == 200
    assert any(fb["id"] == fb_id for fb in admin_fb_res.json())

    # Update review notes
    patch_res = client.patch(
        f"/admin/feedback/{fb_id}",
        headers={"X-User-Email": "24bcs252@iiitdmj.ac.in"},
        json={"reviewed": True, "reviewer_notes": "Added calendar to upload queue"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["reviewed"] is True


def test_fusion_live_sync_flow():
    from unittest.mock import MagicMock, patch
    from app.connectors.fusion_client import FusionRecord

    mock_client = MagicMock()
    mock_client.fetch_records.return_value = (
        [
            FusionRecord(
                category="profile",
                title="Fusion profile",
                external_id="profile",
                text='{"name": "Ayush", "roll_no": "24BCS252", "programme": "B.Tech"}',
                source_url="https://fusion.iiitdmj.ac.in/api/profile/",
            ),
            FusionRecord(
                category="courses",
                title="Current Fusion course registration",
                external_id="courses:current",
                text='{"courses": ["CS101", "MA101", "EC101"]}',
                source_url="https://fusion.iiitdmj.ac.in/academic-procedures/api/stu/current_courseregistration",
            ),
        ],
        {},
    )

    with patch("app.main.FusionClient", return_value=mock_client):
        res = client.post(
            "/connectors/fusion/sync",
            headers={"X-User-Email": "24bcs252@iiitdmj.ac.in"},
            data={"username": "24bcs252", "password": "SamplePassword123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["indexed_count"] == 2
        assert "profile" in data["categories"]
        assert "courses" in data["categories"]
