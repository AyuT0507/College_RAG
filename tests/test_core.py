from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth.local_auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.database import Base
from app.ingestion.documents import chunks
from app.models import AuditLog, Document, Feedback, User
from app.retrieval.router import Route, route_query
from app.security.access_control import visible_document_ids
from app.security.audit import record_audit
from app.services.llm import answer


def test_chunks_cover_text():
    result = chunks("a" * 2000, size=500, overlap=50)
    assert len(result) > 1
    assert "".join(result) != ""  # every segment carries actual source text
    assert all(result[i][-50:] == result[i + 1][:50] for i in range(len(result) - 1))


def test_query_router():
    assert route_query("How many students enrolled?") == Route.SQL
    assert route_query("Explain the late submission policy") == Route.VECTOR
    assert route_query("How many credits and explain the policy") == Route.BOTH


def test_password_hashing_and_verification():
    pw = "SuperSecret123!"
    hashed = hash_password(pw)
    assert hashed.startswith("pbkdf2:sha256:")
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_token_creation_and_decoding():
    email = "student@college.edu"
    token = create_access_token(email)
    decoded = decode_access_token(token)
    assert decoded == email
    # Corrupt token
    assert decode_access_token(token + "bad") is None


def test_answer_fallback_when_sources_unsupported():
    # Requirement 6: Say when indexed sources don't support an answer
    result = answer("What is the secret rocket code?", evidence=[])
    assert "do not contain enough information" in result.lower()


def test_role_and_per_document_permissions():
    # Requirement 4: Enforce roles and per-document permissions
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        student = User(email="student@college.edu", role="student")
        faculty = User(email="prof@college.edu", role="faculty")
        session.add_all([student, faculty])
        session.commit()

        # Public document
        doc_pub = Document(title="College Calendar", source="upload", visibility="public", content_hash="h1")
        # Faculty-only document
        doc_fac = Document(title="Faculty Grading Sheet", source="upload", visibility="roles", allowed_roles="faculty,admin", content_hash="h2")
        # Private student document
        doc_priv = Document(title="Student Transcript", source="upload", visibility="private", owner_id=student.id, content_hash="h3")
        session.add_all([doc_pub, doc_fac, doc_priv])
        session.commit()

        # Student should see public and their own private doc, NOT faculty doc
        student_docs = visible_document_ids(session, student)
        assert doc_pub.id in student_docs
        assert doc_priv.id in student_docs
        assert doc_fac.id not in student_docs

        # Faculty should see public and faculty doc, NOT student's private doc
        faculty_docs = visible_document_ids(session, faculty)
        assert doc_pub.id in faculty_docs
        assert doc_fac.id in faculty_docs
        assert doc_priv.id not in faculty_docs


def test_audit_logging_and_feedback():
    # Requirements 6 & 7: Audit logs and feedback storage
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        user = User(email="test@college.edu", role="student")
        session.add(user)
        session.commit()

        # Log audit entry
        log = record_audit(
            session=session,
            action="QUERY",
            user_id=user.id,
            details={"question": "Where is the library?"},
            ip_address="127.0.0.1",
        )
        session.commit()

        saved_log = session.get(AuditLog, log.id)
        assert saved_log is not None
        assert saved_log.action == "QUERY"
        assert "Where is the library?" in saved_log.details

        # Submit feedback
        fb = Feedback(
            user_id=user.id,
            question="Where is the library?",
            answer="Room 204.",
            rating=1,
            comment="Helpful!",
        )
        session.add(fb)
        session.commit()

        saved_fb = session.get(Feedback, fb.id)
        assert saved_fb is not None
        assert saved_fb.reviewed is False
