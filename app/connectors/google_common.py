from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def service(token_json: str, api: str, version: str):
    return build(api, version, credentials=Credentials.from_authorized_user_info(__import__("json").loads(token_json)))
