# College AI Assistant (College_RAG)

A production-ready, privacy-first Retrieval-Augmented Generation (RAG) assistant customized for **PDPM Indian Institute of Information Technology, Design and Manufacturing (IIITDM) Jabalpur** (`@iiitdmj.ac.in`).

It combines SQLite/SQLAlchemy metadata and structured search with ChromaDB semantic retrieval, routes questions intelligently, provides verified source citations with versioning, enforces role-based access control, tracks audit logs, and handles user feedback.

---

## 📋 Requirements & Implementation Matrix

| Requirement | Implementation Details | Status |
|---|---|---|
| **1. Multi-Source Ingestion** | Staff file uploads (`/documents/upload`), live IIITDMJ website crawler (`/admin/website/crawl`), background Watchdog file monitor (`data/fusion/`), direct Fusion API upload (`/ingestion/fusion/upload`), and authorized Google connectors for Gmail, Drive, and Classroom (`/connectors/google/{provider}/sync`). | ✅ **Fully Satisfied** |
| **2. Dual Search (Structured & Vector)** | Structured CSV and Excel rows are indexed into `StructuredRecord` and queried via SQL `ILIKE` and `COUNT` aggregations. Document text (PDF, DOCX, TXT, MD, HTML) is chunked and searched via ChromaDB semantic embeddings. | ✅ **Fully Satisfied** |
| **3. Intelligent Query Routing** | `route_query()` in `app/retrieval/router.py` automatically routes questions to SQL, vector retrieval, or both based on natural-language intent, then combines the retrieved evidence. | ✅ **Fully Satisfied** |
| **4. Roles & Privacy Permissions** | Strict institutional domain authorization (`@iiitdmj.ac.in` only; non-institute emails are rejected). Roles: `student`, `faculty`, `management`, `admin`. Per-document visibility (`private`, `roles`, `public`) enforced at SQL query level. Token-based auth (`/auth/login`) with PBKDF2 password hashing. | ✅ **Fully Satisfied** |
| **5. Citations, Links & Versioning** | SHA-256 content hashing detects updates and increments `current_version` without duplicating documents. All `/ask` responses return structured source citations with titles, versions, external links, and excerpts. | ✅ **Fully Satisfied** |
| **6. No-Hallucination Fallback & Feedback** | Strict fallback behavior: if indexed sources lack sufficient facts, the assistant explicitly states so instead of making up answers. Users can submit ratings/comments via `POST /feedback`, and staff can review them via `GET /admin/feedback`. | ✅ **Fully Satisfied** |
| **7. Audit Logging** | `AuditLog` records critical operations: logins (`LOGIN`), file uploads (`UPLOAD`), Google/Fusion/Website syncs (`SYNC_*`), and user queries (`QUERY`), with IP addresses and timestamps for compliance (`GET /admin/audit-logs`). | ✅ **Fully Satisfied** |

---

## 🏛️ IIITDMJ Specific Configuration

- **Allowed Email Domain**: `@iiitdmj.ac.in` (Strictly enforced on login, registration, and Google OAuth `hd`).
- **Default Administrator**: `24bcs252@iiitdmj.ac.in`
- **Allowed Website Domains**: `https://www.iiitdmj.ac.in/` and all departmental subdomains (`*.iiitdmj.ac.in`).

---

## 🔄 Fusion Ingestion Workflows

Because Fusion is an internal university portal, three automated pathways are provided to ingest Fusion data:

1. **Zero-Click Watchdog (Automatic)**:
   The server monitors `data/fusion/` in real time using the `watchdog` library. Any file (`.csv`, `.xlsx`, `.pdf`, `.docx`, etc.) dropped or downloaded into this folder is automatically detected, parsed, versioned, and indexed with zero clicks.
2. **Direct API Upload Endpoint**:
   `POST /ingestion/fusion/upload` allows any external script, portal webhook, or tool to push Fusion reports directly over HTTP.
3. **Automated Client Script**:
   [`scripts/sync_fusion_export.py`](scripts/sync_fusion_export.py) automatically authenticates as admin and uploads files or directories:
   ```bash
   # Upload a single file
   python scripts/sync_fusion_export.py "C:\path\to\grades.csv"

   # Upload all exports in your Downloads folder
   python scripts/sync_fusion_export.py "C:\Users\AYUSH\Downloads"

   # Continuously watch Downloads and auto-upload any new Fusion download:
   python scripts/sync_fusion_export.py "C:\Users\AYUSH\Downloads" --watch
   ```

---

## 🛠️ Tech Stack

- **Framework**: FastAPI (Python 3.11+) with modern `lifespan` architecture
- **Database**: SQLite (SQLAlchemy 2.0 ORM)
- **Vector DB**: ChromaDB with `all-MiniLM-L6-v2` embeddings
- **AI Model**: Google Gemini (`google-genai`)
- **Authentication**: PBKDF2-HMAC-SHA256 password hashing + HMAC signed Bearer tokens
- **File Processors**: PyMuPDF (`fitz`), python-docx, pandas, openpyxl, BeautifulSoup4
- **Monitoring**: Python `watchdog` file observer

---

## 🚀 Getting Started Locally

### 1. Set Up Environment

```powershell
cd C:\Users\AYUSH\College_RAG

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)

The `.env` file is pre-configured with generated cryptographic keys:
```env
SECRET_KEY=0ebf4c4aa47ffe59f41255f453bcd7c7262556a20d10094e876b15876b117786
TOKEN_ENCRYPTION_KEY=-Km9IOYutfXEgSoEj134utOO1s9q_AgsKsj3as8Jx8I=
DATABASE_URL=sqlite:///./data/college_ai.db
CHROMA_PATH=./chroma_db
UPLOAD_DIR=./data/uploads
GEMINI_API_KEY=your_key_from_aistudio
GEMINI_MODEL=gemini-2.5-flash
WEBSITE_ALLOWED_DOMAINS=iiitdmj.ac.in,www.iiitdmj.ac.in
ALLOWED_EMAIL_DOMAIN=iiitdmj.ac.in
```

### 3. Seed / Reset Admin Account

To seed or reset your admin credentials:
```powershell
python scripts/seed_admin.py "YourPasswordHere"
```
*(Default: `24bcs252@iiitdmj.ac.in` / `Ayush@2005`)*

### 4. Run the Server

```powershell
uvicorn app.main:app --reload --port 8000
```

Open **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)** for the interactive API reference!

---

## 🧪 Running Automated Tests

Run the comprehensive test suite (all 11 tests validate chunking, routing, auth, domain restrictions, watchdog, feedback, and audit logs):

```powershell
pytest tests/
```

---

## 🌐 API Endpoints Reference

### Authentication & Users
- `POST /admin/bootstrap` - Create initial administrator account (requires `SECRET_KEY`).
- `POST /auth/login` - Authenticate (`@iiitdmj.ac.in` only) and receive a Bearer session token.
- `POST /admin/users` - Create student, faculty, or management accounts (Admin only).

### Ingestion & Sources
- `POST /documents/upload` - Upload PDF, DOCX, CSV, Excel, TXT, or Markdown documents with privacy settings.
- `POST /admin/website/crawl` - Crawl public institute pages (`https://www.iiitdmj.ac.in/`).
- `POST /ingestion/fusion/upload` - Direct API upload endpoint for automated scripts.
- `POST /ingestion/fusion/sync` - Ingest all files placed in `./data/fusion`.
- `GET /admin/watchdog/status` - Check background file monitor status.
- `GET /auth/google/{provider}/start` - Initiate OAuth for `gmail`, `drive`, or `classroom`.
- `POST /connectors/google/{provider}/sync` - Sync and index emails, Drive files, or coursework into private user accounts.

### Search & Retrieval
- `POST /ask` - Ask a natural language question. Routes to SQL, ChromaDB, or both and returns answer with verified citations and version numbers.
- `GET /documents` - List all documents visible to the authenticated user.

### Feedback & Auditing
- `POST /feedback` - Submit helpful/unhelpful rating and comments on an answer.
- `GET /admin/feedback` - Review user feedback queue (Staff/Admin).
- `PATCH /admin/feedback/{id}` - Mark feedback as reviewed and record staff response.
- `GET /admin/audit-logs` - Query historical audit trail records (Admin only).

---

## 🚢 Cloud Deployment

### Option 1: Render (Recommended - Free Tier)
1. Sign in to [Render](https://render.com) with GitHub.
2. Click **New +** &rarr; **Blueprint** &rarr; Select `AyuT0507/College_RAG`.
3. Render automatically detects [`render.yaml`](render.yaml) and builds your Docker container.
4. Add your `GEMINI_API_KEY` in environment settings and click **Apply**.

### Option 2: Docker
```bash
docker build -t college-rag .
docker run -p 8000:8000 --env-file .env college-rag
```

### Option 3: Vercel
A [`vercel.json`](vercel.json) and [`api/index.py`](api/index.py) are included. For serverless deployments, point `DATABASE_URL` to an external cloud database (e.g. Neon PostgreSQL or Supabase) for persistent storage.
