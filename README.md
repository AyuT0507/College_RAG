# College AI Assistant

A modular first draft of a college information assistant. It combines SQLite/SQLAlchemy metadata and structured search with ChromaDB semantic retrieval, routes questions to SQL/vector/both, and provides source excerpts with answers. It includes role-based upload visibility, version records, a public-site crawler, Google OAuth/API connector modules, and a Fusion export-folder path.

## What is implemented

- FastAPI API with user bootstrap, role-based user creation, document upload/list, and `/ask`.
- SQLAlchemy models for users, documents, immutable document versions, per-user OAuth credentials, and structured CSV/Excel rows.
- PDF, DOCX, TXT, Markdown, CSV, and Excel ingestion; CSV and Excel rows are searchable in SQL while all supported document text is chunked into persistent ChromaDB embeddings.
- SQL/vector/both routing and checks that restrict retrieval to documents visible to the requesting user.
- Admin, management, faculty, and student roles. Faculty/management/admin can upload. Documents may be private, public, or visible to selected roles.
- Content hash based update detection and document version history.
- Allowlist-limited public website crawler.
- Gmail, Drive, and Classroom OAuth scopes and API helper functions.
- Fusion exported-file discovery/readers. No undocumented Fusion endpoint, login automation, or access bypass is used.

## Setup (Windows PowerShell)

```powershell
cd C:\Users\AYUSH\IIITDMJ_RAG
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`, replace `SECRET_KEY` with a long random value, and set `TOKEN_ENCRYPTION_KEY` to a Fernet key. Generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Add `GEMINI_API_KEY` for generated answers; without it the API returns retrieved evidence. Keep `.env` private and back up the token encryption key securely; Google tokens cannot be recovered if it is lost.

Start the API:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API reference. Health check: `GET /health`.

## Initial local account

Create the first administrator using `POST /admin/bootstrap` with form fields `email` and `key` (`key` must equal the private `SECRET_KEY` from `.env`). This first draft uses `X-User-Email` as a local identity selector, not production authentication. Anyone able to send requests can impersonate a seeded account; only run on localhost until real sign-in/session validation is added. Never expose this server to a network as-is.

Create additional users with `POST /admin/users` while sending `X-User-Email` for an administrator. Then upload documents with `POST /documents/upload`, selecting private/public/roles visibility. The document list and retrieval apply those visibility rules.

## Google connectors

Create an OAuth client in Google Cloud, enable Gmail API, Drive API, and Classroom API, configure the OAuth consent screen and local redirect URI, and save the downloaded client secret as `credentials/google-client-secret.json`. Add the exact callback URL from `.env` to the OAuth client's authorized redirect URIs. Sign-in endpoints are `/auth/google/{gmail|drive|classroom}/start`; they return a Google authorization URL. The scopes are read-only. Use a dedicated test account and review the current consent-screen/testing restrictions in Google Cloud.

The connector modules expose Gmail message listing, Drive file listing, Classroom course/coursework listing. Connector sync into the assistant's index is an extension point and is not wired into `/ask` yet. OAuth tokens are encrypted in the local database. Add account revocation and secure user authentication before production use.

## Website and Fusion sources

`app/connectors/website.py` crawls public HTML pages only on an explicit hostname allowlist. Respect the college website's terms and robots guidance, use a conservative page limit, and review collected text before indexing it. The crawler is a module, not yet exposed as an admin API workflow.

For Fusion, export/download only records you are authorized to access through your own logged-in account and place them in `data/fusion/`. The readers support CSV, Excel, PDF, DOCX, TXT, and HTML. Do not put private student records in a public repository. The Fusion reader is not yet connected to an authenticated ingestion endpoint.

## Database and deployment notes

SQLite and a local Chroma directory are suitable for a local prototype. They are excluded from Git. Set appropriate backup, retention, encryption, authentication, and access policies before using real institutional or personal data. OAuth token encryption, stronger login sessions, production database migrations, LLM evidence-claim verification, and admin UI remain production work.

Run basic tests with `pytest`. The tests cover chunk overlap and router decisions; they do not validate live Google/Gemini accounts.
