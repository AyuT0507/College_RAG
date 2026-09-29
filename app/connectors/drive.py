from app.connectors.google_common import service


def list_files(token_json: str, limit: int = 100) -> list[dict]:
    api = service(token_json, "drive", "v3")
    result = api.files().list(pageSize=min(limit, 1000), q="trashed = false",
                              fields="files(id,name,mimeType,modifiedTime,webViewLink)").execute()
    return result.get("files", [])
