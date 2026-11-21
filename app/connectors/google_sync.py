import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.classroom import list_courses, list_coursework
from app.connectors.drive import list_files
from app.connectors.gmail import list_messages
from app.ingestion.pipeline import ingest_file
from app.models import Document, OAuthCredential, User
from app.security.token_crypto import decrypt_token


def sync_google_provider(session: Session, user: User, provider: str) -> list[Document]:
    """
    Sync authorized Google resources (Gmail, Drive, or Classroom) for the requesting user
    and index them into the document database with per-user private permissions.
    """
    credential = session.scalar(
        select(OAuthCredential).where(
            OAuthCredential.user_id == user.id,
            OAuthCredential.provider == provider,
        )
    )
    if not credential:
        raise ValueError(f"No connected Google account found for provider '{provider}'. Please authorize first.")

    token_json = decrypt_token(credential.token_json_encrypted)
    synced_docs: list[Document] = []

    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        if provider == "gmail":
            messages = list_messages(token_json, limit=25)
            for msg in messages:
                content = (
                    f"Subject: {msg.get('subject', 'No Subject')}\n"
                    f"From: {msg.get('from', 'Unknown')}\n\n"
                    f"{msg.get('body', '')}"
                )
                file_path = tmp_path / f"gmail_{msg['id']}.txt"
                file_path.write_text(content, encoding="utf-8")

                doc = ingest_file(
                    session=session,
                    path=file_path,
                    title=f"Email: {msg.get('subject') or 'No Subject'}",
                    source="google_gmail",
                    owner=user,
                    visibility="private",
                    external_id=f"https://mail.google.com/mail/u/0/#inbox/{msg['id']}",
                )
                synced_docs.append(doc)

        elif provider == "drive":
            files = list_files(token_json, limit=25)
            for f in files:
                file_name = f.get("name", "Untitled")
                web_link = f.get("webViewLink", f"https://drive.google.com/file/d/{f['id']}")
                content = (
                    f"Drive File Name: {file_name}\n"
                    f"MIME Type: {f.get('mimeType', 'unknown')}\n"
                    f"Last Modified: {f.get('modifiedTime', 'unknown')}\n"
                    f"Link: {web_link}"
                )
                file_path = tmp_path / f"drive_{f['id']}.txt"
                file_path.write_text(content, encoding="utf-8")

                doc = ingest_file(
                    session=session,
                    path=file_path,
                    title=f"Drive: {file_name}",
                    source="google_drive",
                    owner=user,
                    visibility="private",
                    external_id=web_link,
                )
                synced_docs.append(doc)

        elif provider == "classroom":
            courses = list_courses(token_json, limit=20)
            for course in courses:
                course_id = course["id"]
                course_name = course.get("name", "Course")
                section = course.get("section", "")
                room = course.get("room", "")

                coursework = list_coursework(token_json, course_id, limit=30)
                work_items = "\n".join(
                    f"- {item.get('title')}: {item.get('description', '')} (Due: {item.get('dueDate', 'No due date')})"
                    for item in coursework
                )

                content = (
                    f"Course: {course_name}\n"
                    f"Section: {section}\n"
                    f"Room: {room}\n\n"
                    f"Coursework & Assignments:\n"
                    f"{work_items or 'No coursework listed.'}"
                )
                file_path = tmp_path / f"classroom_{course_id}.txt"
                file_path.write_text(content, encoding="utf-8")

                doc = ingest_file(
                    session=session,
                    path=file_path,
                    title=f"Classroom: {course_name}",
                    source="google_classroom",
                    owner=user,
                    visibility="private",
                    external_id=f"https://classroom.google.com/c/{course_id}",
                )
                synced_docs.append(doc)
        else:
            raise ValueError(f"Unknown Google provider: {provider}")

    return synced_docs
