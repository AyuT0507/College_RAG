try:
    from google_auth_oauthlib.flow import Flow
except ImportError:
    Flow = None

from app.config import get_settings

SCOPES = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "drive": ["https://www.googleapis.com/auth/drive.readonly"],
    "classroom": [
        "https://www.googleapis.com/auth/classroom.courses.readonly",
        "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
        "https://www.googleapis.com/auth/classroom.announcements.readonly",
    ],
}


def create_flow(provider: str, state: str | None = None):
    if Flow is None:
        raise ValueError("google-auth-oauthlib is not installed. Run 'pip install google-auth-oauthlib'.")
    if provider not in SCOPES:
        raise ValueError("Unsupported Google provider")
    flow = Flow.from_client_secrets_file(get_settings().google_client_secrets_file, scopes=SCOPES[provider], state=state)
    flow.redirect_uri = get_settings().google_redirect_uri
    return flow
