"""
Automated Fusion Export Uploader (Option 2 Client Script)
---------------------------------------------------------
Automatically authenticates with College_RAG and uploads Fusion export files
(CSV, XLSX, PDF, DOCX, TXT, HTML) directly into the AI index via API.

Usage:
    # Upload a single file:
    python scripts/sync_fusion_export.py "C:\\path\\to\\grades.csv"

    # Upload all exports in a folder:
    python scripts/sync_fusion_export.py "C:\\Users\\AYUSH\\Downloads"

    # Run in continuous watch mode (monitors a folder and auto-uploads):
    python scripts/sync_fusion_export.py "C:\\Users\\AYUSH\\Downloads" --watch
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

DEFAULT_API_URL = os.environ.get("COLLEGE_RAG_API_URL", "http://127.0.0.1:8000")
DEFAULT_EMAIL = os.environ.get("COLLEGE_RAG_EMAIL", "24bcs252@iiitdmj.ac.in")
DEFAULT_PASSWORD = os.environ.get("COLLEGE_RAG_PASSWORD", "Ayush@2005")

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf", ".docx", ".txt", ".html", ".md"}


def get_auth_token(api_url: str, email: str, password: str) -> str:
    """Authenticate and obtain a Bearer access token."""
    login_url = f"{api_url.rstrip('/')}/auth/login"
    try:
        res = requests.post(
            login_url,
            json={"email": email, "password": password},
            timeout=10,
        )
        if res.status_code == 200:
            token = res.json().get("access_token")
            print(f"[Auth] Logged in successfully as {email}")
            return token
        else:
            raise RuntimeError(f"Login failed ({res.status_code}): {res.text}")
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not connect to {api_url}: {exc}")


def upload_file(api_url: str, token: str, file_path: Path, visibility: str = "roles") -> dict:
    """Upload a single file to POST /ingestion/fusion/upload."""
    upload_url = f"{api_url.rstrip('/')}/ingestion/fusion/upload"
    headers = {"Authorization": f"Bearer {token}"}
    
    with file_path.open("rb") as f:
        files = {"file": (file_path.name, f)}
        data = {
            "visibility": visibility,
            "roles": "student,faculty,management,admin",
        }
        res = requests.post(upload_url, headers=headers, files=files, data=data, timeout=60)
        
    if res.status_code in {200, 201}:
        data = res.json()
        print(f"[Success] Indexed: {file_path.name} (Doc ID: {data.get('id')}, Version: {data.get('version')})")
        return data
    else:
        print(f"[Error] Failed to index {file_path.name} ({res.status_code}): {res.text}")
        return {}


def process_target(api_url: str, token: str, target: Path):
    """Process a single file or directory of files."""
    if target.is_file():
        if target.suffix.lower() in ALLOWED_EXTENSIONS:
            upload_file(api_url, token, target)
        else:
            print(f"[Skip] Unsupported file type: {target.suffix} ({target.name})")
    elif target.is_dir():
        count = 0
        for f in target.rglob("*"):
            if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
                upload_file(api_url, token, f)
                count += 1
        print(f"[Complete] Processed {count} files in directory: {target}")
    else:
        print(f"[Error] Target not found: {target}")


def main():
    parser = argparse.ArgumentParser(description="Automated Fusion Export Uploader")
    parser.add_argument("target", nargs="?", default="./data/fusion", help="File or folder path to upload")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Base API URL (default: http://127.0.0.1:8000)")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Admin/Faculty email")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password")
    parser.add_argument("--watch", action="store_true", help="Continuously watch folder and auto-upload new files")
    parser.add_argument("--interval", type=int, default=5, help="Watch interval in seconds (default: 5)")

    args = parser.parse_args()
    target_path = Path(args.target).resolve()

    print(f"Connecting to College_RAG at {args.api_url}...")
    token = get_auth_token(args.api_url, args.email, args.password)

    if not args.watch:
        process_target(args.api_url, token, target_path)
    else:
        print(f"[Watch Mode] Watching {target_path} every {args.interval} seconds... (Press Ctrl+C to stop)")
        seen_files: set[str] = set()
        while True:
            if target_path.exists():
                for f in target_path.rglob("*"):
                    if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
                        mtime = f.stat().st_mtime
                        file_key = f"{f.resolve()}_{mtime}"
                        if file_key not in seen_files:
                            seen_files.add(file_key)
                            upload_file(args.api_url, token, f)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
