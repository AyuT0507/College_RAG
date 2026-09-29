import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.google_oauth import create_flow
from app.config import get_settings
from app.connectors.website import crawl
from app.database import Base, engine, get_db
from app.ingestion.pipeline import ingest_file
from app.models import Document, OAuthCredential, User
from app.retrieval.router import Route, route_query
from app.retrieval.sql import search_documents, search_structured_records
from app.retrieval.vector import search as vector_search
from app.security.access_control import can_upload, visible_document_ids
from app.security.token_crypto import encrypt_token
from app.services.llm import answer
from app.services.verification import verify_evidence

Base.metadata.create_all(bind=engine)
app = FastAPI(title=get_settings().app_name, version="0.1.0")
oauth_states: dict[str, tuple[str, int]] = {}


def user_dependency(x_user_email: str | None = Header(default=None, alias="X-User-Email"), db: Session = Depends(get_db)) -> User:
    if not x_user_email:
        raise HTTPException(401, "Set X-User-Email to an account seeded by an administrator")
    user = db.scalar(select(User).where(User.email == x_user_email.lower()))
    if not user or not user.is_active:
        raise HTTPException(401, "Unknown or inactive user")
    return user


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/admin/users", status_code=201)
def create_user(email: str = Form(...), role: str = Form("student"), display_name: str = Form(""),
                db: Session = Depends(get_db), admin: User = Depends(user_dependency)):
    if admin.role != "admin":
        raise HTTPException(403, "Admin role required")
    if role not in {"student", "faculty", "management", "admin"}:
        raise HTTPException(400, "Invalid role")
    if db.scalar(select(User).where(User.email == email.lower())):
        raise HTTPException(409, "User already exists")
    user = User(email=email.lower(), role=role, display_name=display_name)
    db.add(user)
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@app.post("/admin/bootstrap", status_code=201)
def bootstrap_admin(email: str = Form(...), key: str = Form(...), db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.secret_key == "development-only-change-me" or not secrets.compare_digest(key, settings.secret_key):
        raise HTTPException(403, "Set a private SECRET_KEY in .env before bootstrap")
    if db.scalar(select(User).where(User.role == "admin")):
        raise HTTPException(409, "An admin already exists")
    user = User(email=email.lower(), role="admin", display_name="Administrator")
    db.add(user); db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@app.post("/documents/upload", status_code=201)
async def upload_document(file: UploadFile = File(...), visibility: str = Form("private"),
                          roles: str = Form(""), db: Session = Depends(get_db), user: User = Depends(user_dependency)):
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
            doc = ingest_file(db, temp, title=name, source="upload", owner=user, visibility=visibility,
                              allowed_roles=[r.strip() for r in roles.split(",") if r.strip()])
            db.commit()
        except ValueError as exc:
            db.rollback(); raise HTTPException(415, str(exc)) from exc
        return {"id": doc.id, "title": doc.title, "version": doc.current_version}
    finally:
        temp.unlink(missing_ok=True)


@app.post("/ask")
def ask(request: AskRequest, db: Session = Depends(get_db), user: User = Depends(user_dependency)):
    route = route_query(request.question)
    doc_ids = visible_document_ids(db, user)
    evidence = []
    if route in {Route.VECTOR, Route.BOTH}:
        evidence.extend(vector_search(request.question, doc_ids))
    if route in {Route.SQL, Route.BOTH}:
        evidence.extend(search_structured_records(db, user, request.question))
        docs = search_documents(db, user, request.question)
        known = {item["document_id"] for item in evidence}
        for doc in docs:
            if doc.id not in known:
                evidence.append({"document_id": doc.id, "text": f"Document title: {doc.title}", "distance": None})
    evidence = verify_evidence(evidence)
    return {"route": route.value, "answer": answer(request.question, evidence),
            "sources": [{"document_id": e["document_id"], "excerpt": e["text"][:300]} for e in evidence]}


@app.get("/documents")
def list_documents(db: Session = Depends(get_db), user: User = Depends(user_dependency)):
    docs = db.scalars(select(Document).where(Document.id.in_(visible_document_ids(db, user)))).all()
    return [{"id": d.id, "title": d.title, "source": d.source, "version": d.current_version} for d in docs]


@app.get("/auth/google/{provider}/start")
def google_start(provider: str, user: User = Depends(user_dependency)):
    if not get_settings().token_encryption_key:
        raise HTTPException(400, "Configure TOKEN_ENCRYPTION_KEY before connecting Google accounts")
    try:
        flow = create_flow(provider)
        state = secrets.token_urlsafe(32)
        oauth_states[state] = (provider, user.id)
        url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", state=state, prompt="consent")
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
    credential = db.scalar(select(OAuthCredential).where(OAuthCredential.user_id == user_id,
                                                           OAuthCredential.provider == provider))
    import json
    serialized = encrypt_token(flow.credentials.to_json())
    if credential:
        credential.token_json_encrypted = serialized
    else:
        db.add(OAuthCredential(user_id=user_id, provider=provider, token_json_encrypted=serialized))
    db.commit()
    return {"connected": provider, "message": "OAuth complete. Tokens are encrypted in the local database."}


@app.post("/admin/website/crawl")
def ingest_public_website(start_url: str = Form(...), max_pages: int = Form(20),
                          db: Session = Depends(get_db), user: User = Depends(user_dependency)):
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
            document = ingest_file(db, temp, title=page["title"], source="website", owner=None,
                                   visibility="public", external_id=page["url"])
            added.append(document.id)
        finally:
            temp.unlink(missing_ok=True)
    db.commit()
    return {"indexed": len(added), "document_ids": added}
