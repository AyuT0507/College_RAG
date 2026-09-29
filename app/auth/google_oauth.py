from google_auth_oauthlib.flow import Flow

from app.config import get_settings


SCOPES = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "drive": ["https://www.googleapis.com/auth/drive.readonly"],
    "classroom": ["https://www.googleapis.com/auth/classroom.courses.readonly",
                  "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
                  "https://www.googleapis.com/auth/classroom.announcements.readonly"],
}


def create_flow(provider: str, state: str | None = None) -> Flow:
    if provider not in SCOPES:
        raise ValueError("Unsupported Google provider")
    flow = Flow.from_client_secrets_file(get_settings().google_client_secrets_file, scopes=SCOPES[provider], state=state)
    flow.redirect_uri = get_settings().google_redirect_uri
    return flow
