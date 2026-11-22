import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.google_oauth import create_flow
from app.auth.local_auth import (
    create_access_token,
    hash_password,
    resolve_user,
    validate_domain,
    verify_password,
)
from app.config import get_settings
from app.connectors.fusion import sync_fusion_directory
from app.connectors.google_sync import sync_google_provider
from app.connectors.website import crawl
from app.database import Base, engine, get_db
from app.ingestion.pipeline import ingest_file
from app.models import AuditLog, Document, Feedback, OAuthCredential, User
from app.retrieval.router import Route, route_query
from app.retrieval.sql import search_documents, search_structured_records
from app.retrieval.vector import search as vector_search
from app.security.access_control import can_upload, visible_document_ids
from app.security.audit import record_audit
from app.security.token_crypto import encrypt_token
from app.services.fusion_watcher import fusion_watchdog
from app.services.llm import answer
from app.services.verification import verify_evidence

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan handler to start and gracefully stop the background Fusion watchdog."""
    try:
        fusion_watchdog.start()
    except Exception:
        pass
    yield
    try:
        fusion_watchdog.stop()
    except Exception:
        pass


app = FastAPI(title=get_settings().app_name, version="0.2.0", lifespan=lifespan)
oauth_states: dict[str, tuple[str, int]] = {}


def user_dependency(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate user via Bearer token (production) or X-User-Email (local dev fallback)."""
    return resolve_user(db, authorization=authorization, x_user_email=x_user_email)


# ============================================================================
# Request Models
# ============================================================================

class AskRequest(BaseModel):
    question: str


class LoginRequest(BaseModel):
    email: str
    password: str


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: int = 0
    comment: str = ""


class FeedbackReviewRequest(BaseModel):
    reviewed: bool = True
    reviewer_notes: str = ""


# ============================================================================
# Health & Status
# ============================================================================

@app.get("/health")
def health():
    return {"status": "ok", "app": get_settings().app_name, "version": "0.2.0"}


# ============================================================================
# Authentication (Requirement 4 & 7)
# ============================================================================

@app.post("/auth/login")
def login(request: LoginRequest, req: Request, db: Session = Depends(get_db)):
    """Authenticate user with email/password and issue a secure session token."""
    validate_domain(request.email)
    user = db.scalar(select(User).where(User.email == request.email.strip().lower()))
    if not user or not user.is_active or not verify_password(request.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    token = create_access_token(user.email)
    ip_addr = req.client.host if req.client else ""
    record_audit(db, action="LOGIN", user_id=user.id, details={"email": user.email, "role": user.role}, ip_address=ip_addr)
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "email": user.email,
        "role": user.role,
        "display_name": user.display_name,
    }


# ============================================================================
# User Administration
# ============================================================================

@app.post("/admin/users", status_code=201)
def create_user(
    email: str = Form(...),
    password: str = Form("changeme123"),
    role: str = Form("student"),
    display_name: str = Form(""),
    req: Request = None,
    db: Session = Depends(get_db),
    admin: User = Depends(user_dependency),
):
    if admin.role != "admin":
        raise HTTPException(403, "Admin role required")
    validate_domain(email)
    if role not in {"student", "faculty", "management", "admin"}:
        raise HTTPException(400, "Invalid role")
    if db.scalar(select(User).where(User.email == email.lower())):
        raise HTTPException(409, "User already exists")

    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        role=role,
        display_name=display_name,
    )
    db.add(user)
    db.flush()

    ip_addr = req.client.host if (req and req.client) else ""
    record_audit(db, action="CREATE_USER", user_id=admin.id, details={"new_user_email": user.email, "role": role}, ip_address=ip_addr)
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@app.post("/admin/bootstrap", status_code=201)
def bootstrap_admin(
    email: str = Form(...),
    password: str = Form("admin123"),
    key: str = Form(...),
    req: Request = None,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    validate_domain(email)
    if settings.secret_key == "development-only-change-me" or not secrets.compare_digest(key, settings.secret_key):
        raise HTTPException(403, "Set a private SECRET_KEY in .env before bootstrap")
    if db.scalar(select(User).where(User.role == "admin")):
        raise HTTPException(409, "An admin already exists")

    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        role="admin",
        display_name="Administrator",
    )
    db.add(user)
    db.flush()

    ip_addr = req.client.host if (req and req.client) else ""
    record_audit(db, action="BOOTSTRAP", user_id=user.id, details={"email": user.email}, ip_address=ip_addr)
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


# ============================================================================
# Document Ingestion (Staff Uploads, Fusion, Website, Google) - Requirement 1
# ============================================================================

@app.post("/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    visibility: str = Form("private"),
    roles: str = Form(""),
    req: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    if not can_upload(user):
        raise HTTPException(403, "Faculty, management, or admin role required")
    if visibility not in {"private", "public", "roles"}:
        raise HTTPException(400, "visibility must be private, public, or roles")
    if visibility == "roles" and not roles.strip():
        raise HTTPException(400, "Provide a comma-separated roles list")

    settings = get_settings()
    target_dir = Path(settings.upload_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "upload").name
    temp = target_dir / f"pending_{secrets.token_hex(8)}_{name}"
    size = 0

    try:
        with temp.open("wb") as out:
            while data := await file.read(1024 * 1024):
                size += len(data)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Upload exceeds configured size limit")
                out.write(data)
        try:
            doc = ingest_file(
                db,
                temp,
                title=name,
                source="upload",
                owner=user,
                visibility=visibility,
                allowed_roles=[r.strip() for r in roles.split(",") if r.strip()],
                external_id=name,
            )
            ip_addr = req.client.host if (req and req.client) else ""
            record_audit(
                db,
                action="UPLOAD",
                user_id=user.id,
                details={"doc_id": doc.id, "title": doc.title, "version": doc.current_version, "size": size},
                ip_address=ip_addr,
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            raise HTTPException(415, str(exc)) from exc
        return {"id": doc.id, "title": doc.title, "version": doc.current_version, "source": doc.source}
    finally:
        temp.unlink(missing_ok=True)


@app.post("/ingestion/fusion/sync", status_code=200)
def sync_fusion(
    folder_path: str = Form("./data/fusion"),
    visibility: str = Form("roles"),
    roles: str = Form("faculty,management,admin"),
    req: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    """Sync authorized Fusion exported files into document and structured database."""
    if not can_upload(user):
        raise HTTPException(403, "Faculty, management, or admin role required")

    directory = Path(folder_path).resolve()
    if not directory.exists():
        raise HTTPException(404, f"Fusion directory not found at: {folder_path}")

    allowed_roles_list = [r.strip() for r in roles.split(",") if r.strip()]
    synced = sync_fusion_directory(
        session=db,
        directory=directory,
        owner=user,
        visibility=visibility,
        allowed_roles=allowed_roles_list,
    )
    db.commit()

    ip_addr = req.client.host if (req and req.client) else ""
    record_audit(
        db,
        action="SYNC_FUSION",
        user_id=user.id,
        details={"directory": str(folder_path), "synced_count": len(synced)},
        ip_address=ip_addr,
    )
    db.commit()

    return {
        "status": "success",
        "synced_count": len(synced),
        "documents": [{"id": d.id, "title": d.title, "version": d.current_version} for d in synced],
    }


@app.post("/ingestion/fusion/upload", status_code=201)
async def upload_fusion_file(
    file: UploadFile = File(...),
    visibility: str = Form("roles"),
    roles: str = Form("student,faculty,management,admin"),
    req: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    """Direct API upload endpoint for automated scripts and integration pipelines (Option 2)."""
    if not can_upload(user):
        raise HTTPException(403, "Faculty, management, or admin role required")
    settings = get_settings()
    fusion_dir = Path("./data/fusion").resolve()
    fusion_dir.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "fusion_export").name
    temp = fusion_dir / f"api_{secrets.token_hex(6)}_{name}"
    size = 0

    try:
        with temp.open("wb") as out:
            while data := await file.read(1024 * 1024):
                size += len(data)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Upload exceeds configured size limit")
                out.write(data)
        try:
            doc = ingest_file(
                db,
                temp,
                title=f"Fusion: {name}",
                source="fusion",
                owner=user,
                visibility=visibility,
                allowed_roles=[r.strip() for r in roles.split(",") if r.strip()],
                external_id=f"fusion:{name}",
            )
            ip_addr = req.client.host if (req and req.client) else ""
            record_audit(
                db,
                action="UPLOAD_FUSION_API",
                user_id=user.id,
                details={"doc_id": doc.id, "title": doc.title, "size_bytes": size},
                ip_address=ip_addr,
            )
            db.commit()
            return {"id": doc.id, "title": doc.title, "version": doc.current_version, "status": "indexed"}
        except ValueError as exc:
            db.rollback()
            raise HTTPException(415, str(exc)) from exc
    finally:
        temp.unlink(missing_ok=True)


@app.get("/admin/watchdog/status")
def watchdog_status(user: User = Depends(user_dependency)):
    """Check background watchdog file watcher status."""
    if user.role not in {"admin", "management"}:
        raise HTTPException(403, "Admin or management role required")
    return {
        "watchdog_active": fusion_watchdog.is_running,
        "watch_dir": str(fusion_watchdog.watch_dir),
    }


@app.post("/admin/website/crawl")
def ingest_public_website(
    start_url: str = Form(...),
    max_pages: int = Form(20),
    req: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    if user.role not in {"admin", "management"}:
        raise HTTPException(403, "Admin or management role required")
    domains = {host.strip().lower() for host in get_settings().website_allowed_domains.split(",") if host.strip()}
    if not domains:
        raise HTTPException(400, "Configure WEBSITE_ALLOWED_DOMAINS first")
    try:
        pages = crawl(start_url, domains, max_pages=max(1, min(max_pages, 100)))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    base = Path("./data/website").resolve()
    base.mkdir(parents=True, exist_ok=True)
    added = []
    for index, page in enumerate(pages):
        temp = base / f"page_{index}.txt"
        temp.write_text(page["text"], encoding="utf-8")
        try:
            document = ingest_file(
                db,
                temp,
                title=page["title"],
                source="website",
                owner=None,
                visibility="public",
                external_id=page["url"],
            )
            added.append(document.id)
        finally:
            temp.unlink(missing_ok=True)

    ip_addr = req.client.host if (req and req.client) else ""
    record_audit(
        db,
        action="SYNC_WEBSITE",
        user_id=user.id,
        details={"start_url": start_url, "pages_crawled": len(added), "document_ids": added},
        ip_address=ip_addr,
    )
    db.commit()
    return {"indexed": len(added), "document_ids": added}


# ============================================================================
# Google Connectors & Sync (Requirement 1)
# ============================================================================

@app.get("/auth/google/{provider}/start")
def google_start(provider: str, user: User = Depends(user_dependency)):
    if not get_settings().token_encryption_key:
        raise HTTPException(400, "Configure TOKEN_ENCRYPTION_KEY before connecting Google accounts")
    try:
        flow = create_flow(provider)
        state = secrets.token_urlsafe(32)
        oauth_states[state] = (provider, user.id)
        auth_kwargs = {"access_type": "offline", "include_granted_scopes": "true", "state": state, "prompt": "consent"}
        if get_settings().allowed_email_domain:
            auth_kwargs["hd"] = get_settings().allowed_email_domain
        url, _ = flow.authorization_url(**auth_kwargs)
        return {"authorization_url": url, "state": state}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/auth/google/callback")
def google_callback(state: str, code: str, db: Session = Depends(get_db)):
    entry = oauth_states.pop(state, None)
    if not entry:
        raise HTTPException(400, "Invalid or expired OAuth state")
    provider, user_id = entry
    flow = create_flow(provider, state=state)
    flow.fetch_token(code=code)
    credential = db.scalar(
        select(OAuthCredential).where(OAuthCredential.user_id == user_id, OAuthCredential.provider == provider)
    )
    serialized = encrypt_token(flow.credentials.to_json())
    if credential:
        credential.token_json_encrypted = serialized
    else:
        db.add(OAuthCredential(user_id=user_id, provider=provider, token_json_encrypted=serialized))
    db.commit()
    return {"connected": provider, "message": "OAuth complete. Tokens are encrypted in the local database."}


@app.post("/connectors/google/{provider}/sync")
def sync_google(
    provider: str,
    req: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    """Sync authorized Google records (Gmail messages, Drive files, or Classroom coursework)."""
    try:
        synced = sync_google_provider(db, user, provider)
        ip_addr = req.client.host if (req and req.client) else ""
        record_audit(
            db,
            action="SYNC_GOOGLE",
            user_id=user.id,
            details={"provider": provider, "synced_count": len(synced)},
            ip_address=ip_addr,
        )
        db.commit()
        return {
            "status": "success",
            "provider": provider,
            "synced_count": len(synced),
            "documents": [{"id": d.id, "title": d.title, "external_id": d.external_id} for d in synced],
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ============================================================================
# Question Answering & Retrieval (Requirements 2, 3, 5, 6, 7)
# ============================================================================

@app.post("/ask")
def ask(
    request: AskRequest,
    req: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    # 1. Route query (Requirement 3)
    route = route_query(request.question)
    doc_ids = visible_document_ids(db, user)
    evidence: list[dict] = []

    # 2. Vector search over documents (Requirement 2)
    if route in {Route.VECTOR, Route.BOTH}:
        evidence.extend(vector_search(request.question, doc_ids))

    # 3. SQL search over structured CSV/Excel records (Requirement 2)
    if route in {Route.SQL, Route.BOTH}:
        evidence.extend(search_structured_records(db, user, request.question))
        docs = search_documents(db, user, request.question)
        known = {item["document_id"] for item in evidence}
        for doc in docs:
            if doc.id not in known:
                evidence.append({"document_id": doc.id, "text": f"Document title: {doc.title}", "distance": None})

    # 4. Verify evidence retains document citations
    evidence = verify_evidence(evidence)

    # 5. Enrich evidence with document metadata (title, version, source, external URL) (Requirement 5)
    matched_ids = {e["document_id"] for e in evidence if e["document_id"] > 0}
    doc_map: dict[int, Document] = {}
    if matched_ids:
        found_docs = db.scalars(select(Document).where(Document.id.in_(matched_ids))).all()
        doc_map = {d.id: d for d in found_docs}

    sources = []
    for e in evidence:
        doc = doc_map.get(e["document_id"])
        if doc:
            e["title"] = doc.title
            e["version"] = doc.current_version
            e["source"] = doc.source
            e["url"] = doc.external_id
            sources.append({
                "document_id": doc.id,
                "title": doc.title,
                "source": doc.source,
                "version": doc.current_version,
                "url": doc.external_id,
                "excerpt": e["text"][:300],
            })
        else:
            sources.append({
                "document_id": e["document_id"],
                "title": "Structured Record / Aggregation",
                "source": "sql_record",
                "version": 1,
                "url": "",
                "excerpt": e["text"][:300],
            })

    # 6. Generate answer (Requirement 6 - Fallback if unsupported)
    answer_text = answer(request.question, evidence)

    # 7. Audit query action (Requirement 7)
    ip_addr = req.client.host if (req and req.client) else ""
    record_audit(
        db,
        action="QUERY",
        user_id=user.id,
        details={
            "question": request.question,
            "route": route.value,
            "matched_documents": list(matched_ids),
        },
        ip_address=ip_addr,
    )
    db.commit()

    return {
        "route": route.value,
        "answer": answer_text,
        "sources": sources,
    }


@app.get("/documents")
def list_documents(db: Session = Depends(get_db), user: User = Depends(user_dependency)):
    docs = db.scalars(select(Document).where(Document.id.in_(visible_document_ids(db, user)))).all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "source": d.source,
            "version": d.current_version,
            "url": d.external_id,
            "visibility": d.visibility,
        }
        for d in docs
    ]


# ============================================================================
# User Feedback System (Requirement 6)
# ============================================================================

@app.post("/feedback", status_code=201)
def submit_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    """Allow users to submit feedback on answers for staff review."""
    entry = Feedback(
        user_id=user.id,
        question=request.question,
        answer=request.answer,
        rating=request.rating,
        comment=request.comment,
    )
    db.add(entry)
    db.commit()
    return {
        "id": entry.id,
        "status": "submitted",
        "message": "Feedback submitted successfully for staff review.",
    }


@app.get("/admin/feedback")
def list_feedback(
    reviewed: bool | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    """Staff review endpoint for user feedback."""
    if user.role not in {"admin", "management"}:
        raise HTTPException(403, "Admin or management role required")
    stmt = select(Feedback)
    if reviewed is not None:
        stmt = stmt.where(Feedback.reviewed == reviewed)
    return db.scalars(stmt.order_by(Feedback.created_at.desc()).limit(limit)).all()


@app.patch("/admin/feedback/{feedback_id}")
def review_feedback(
    feedback_id: int,
    request: FeedbackReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    """Mark feedback as reviewed and record staff response."""
    if user.role not in {"admin", "management"}:
        raise HTTPException(403, "Admin or management role required")
    item = db.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(404, "Feedback entry not found")
    item.reviewed = request.reviewed
    item.reviewer_notes = request.reviewer_notes
    db.commit()
    return {"id": item.id, "reviewed": item.reviewed, "reviewer_notes": item.reviewer_notes}


# ============================================================================
# Audit Logs (Requirement 7)
# ============================================================================

@app.get("/admin/audit-logs")
def list_audit_logs(
    action: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(user_dependency),
):
    """Retrieve audit log history for compliance and monitoring."""
    if user.role not in {"admin", "management"}:
        raise HTTPException(403, "Admin or management role required")
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action.upper())
    logs = db.scalars(stmt.order_by(AuditLog.timestamp.desc()).limit(limit)).all()
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "details": log.details,
            "ip_address": log.ip_address,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]
