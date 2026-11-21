import json


def service(token_json: str, api: str, version: str):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise ValueError("Google client libraries are not installed. Run 'pip install google-api-python-client google-auth'.")

    return build(api, version, credentials=Credentials.from_authorized_user_info(json.loads(token_json)))
