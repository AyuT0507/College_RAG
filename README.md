# College AI Assistant (College_RAG)

A production-ready, privacy-first Retrieval-Augmented Generation (RAG) assistant for colleges and universities.

It combines SQLite/SQLAlchemy metadata and structured search with ChromaDB semantic retrieval, routes questions intelligently, provides verified source citations with versioning, enforces role-based access control, tracks audit logs, and handles user feedback.

---

## 📋 Requirements & Implementation Matrix

| Requirement | Implementation Details | Status |
|---|---|---|
| **1. Multi-Source Ingestion** | Staff file uploads (`/documents/upload`), public website crawler (`/admin/website/crawl`), Fusion export folder sync (`/ingestion/fusion/sync`), and authorized Google connectors for Gmail, Drive, and Classroom (`/connectors/google/{provider}/sync`). | ✅ **Fully Satisfied** |
| **2. Dual Search (Structured & Vector)** | Structured CSV and Excel rows are indexed into `StructuredRecord` and queried via SQL ILIKE and COUNT aggregations. Document text (PDF, DOCX, TXT, MD, HTML) is chunked and searched via ChromaDB semantic embeddings. | ✅ **Fully Satisfied** |
| **3. Intelligent Query Routing** | `route_query()` in `app/retrieval/router.py` automatically routes questions to SQL, vector retrieval, or both based on natural-language intent, then combines the retrieved evidence. | ✅ **Fully Satisfied** |
| **4. Roles & Privacy Permissions** | Roles (`student`, `faculty`, `management`, `admin`). Strict per-document visibility (`private`, `roles`, `public`) enforced directly in database queries so private data is never leaked. Production-grade token authentication (`/auth/login`) with PBKDF2 password hashing. | ✅ **Fully Satisfied** |
| **5. Citations, Links & Versioning** | SHA-256 content hashing detects updates and increments `current_version` without duplicating documents. All `/ask` responses return structured source citations with titles, versions, external links, and excerpts. | ✅ **Fully Satisfied** |
| **6. No-Hallucination Fallback & Feedback** | Strict fallback behavior: if indexed sources lack sufficient facts, the assistant explicitly states so instead of making up answers. Users can submit ratings/comments via `POST /feedback`, and staff can review them via `GET /admin/feedback`. | ✅ **Fully Satisfied** |
| **7. Audit Logging** | `AuditLog` records critical operations: logins (`LOGIN`), file uploads (`UPLOAD`), Google/Fusion/Website syncs (`SYNC_*`), and user queries (`QUERY`), with IP addresses and timestamps for compliance (`GET /admin/audit-logs`). | ✅ **Fully Satisfied** |

---

## 🛠️ Tech Stack

- **Framework**: FastAPI (Python 3.11+)
- **Database**: SQLite (SQLAlchemy 2.0 ORM)
- **Vector DB**: ChromaDB with `all-MiniLM-L6-v2` embeddings
- **AI Model**: Google Gemini (`google-genai`)
- **Authentication**: PBKDF2-HMAC-SHA256 password hashing + HMAC signed Bearer tokens
- **File Processors**: PyMuPDF (`fitz`), python-docx, pandas, openpyxl, BeautifulSoup4

---

## 🚀 Getting Started

### 1. Clone & Set Up Virtual Environment

```bash
cd College_RAG
python -m venv venv

# Windows:
.\venv\Scripts\Activate.ps1

# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure Environment (`.env`)

Generate a Fernet encryption key and secret key:
```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print('TOKEN_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Add your `GEMINI_API_KEY` from Google AI Studio.

### 3. Run the Server

```bash
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` in your browser for the interactive Swagger UI!

---

## 🧪 Running Tests

The test suite validates chunking, routing, authentication, permissions, audit logging, feedback, and API endpoints:

```bash
pytest tests/
```

---

## 🌐 API Overview

### Authentication & Users
- `POST /admin/bootstrap` - Create initial administrator account with your secret key.
- `POST /auth/login` - Authenticate with email/password and obtain a Bearer token.
- `POST /admin/users` - Create student, faculty, or management accounts (Admin only).

### Ingestion & Connectors
- `POST /documents/upload` - Upload PDF, DOCX, CSV, Excel, TXT, or Markdown documents with privacy settings.
- `POST /admin/website/crawl` - Crawl public college website URLs within allowed domains.
- `POST /ingestion/fusion/sync` - Ingest authorized Fusion export files from `./data/fusion`.
- `GET /auth/google/{provider}/start` - Initiate OAuth for `gmail`, `drive`, or `classroom`.
- `POST /connectors/google/{provider}/sync` - Sync and index emails, Drive files, or coursework into private student/staff accounts.

### Search & RAG
- `POST /ask` - Ask a natural language question. Routes to SQL, ChromaDB, or both and returns answer with verified citations.
- `GET /documents` - List all documents visible to the current user.

### Feedback & Auditing
- `POST /feedback` - Submit helpful/unhelpful rating and feedback on an answer.
- `GET /admin/feedback` - Review user feedback submissions (Staff/Admin).
- `PATCH /admin/feedback/{id}` - Mark feedback as reviewed and add staff notes.
- `GET /admin/audit-logs` - Query historical audit logs for compliance (Admin only).

---

## 🚢 Deployment Guide

### Option 1: Render (Recommended - Free & Easiest)
Because College_RAG uses SQLite and a persistent local ChromaDB vector directory, deploying as a containerized web service with a persistent disk is ideal:

1. Push your repository to GitHub.
2. Sign in to [Render](https://render.com) and click **New > Blueprint**.
3. Select your repository. Render automatically reads `render.yaml` and deploys the `Dockerfile` with a persistent volume mounted at `/app/data`.
4. Add your `GEMINI_API_KEY` in the Render dashboard environment settings.

### Option 2: Railway
1. Sign in to [Railway](https://railway.app).
2. Click **New Project > Deploy from GitHub repo**.
3. Add a persistent volume for `/app/data` and set environment variables.

### Option 3: Docker (Run Anywhere)
```bash
docker build -t college-rag .
docker run -p 8000:8000 --env-file .env college-rag
```

### Option 4: Vercel (Serverless Note)
A `vercel.json` and `api/index.py` are included. Note: Vercel serverless functions have ephemeral (temporary) file storage, so local SQLite and ChromaDB files reset across cold starts. For production on Vercel, point `DATABASE_URL` to an external PostgreSQL database (such as Neon or Supabase) and use an external vector service.
