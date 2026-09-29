import base64

from app.connectors.google_common import service


def list_messages(token_json: str, query: str = "newer_than:1y", limit: int = 50) -> list[dict]:
    api = service(token_json, "gmail", "v1")
    items = api.users().messages().list(userId="me", q=query, maxResults=limit).execute().get("messages", [])
    output = []
    for item in items:
        msg = api.users().messages().get(userId="me", id=item["id"], format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = msg.get("snippet", "")
        payload = msg.get("payload", {})
        parts = payload.get("parts", [payload])
        for part in parts:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"] + "==").decode("utf-8", "replace")
                break
        output.append({"id": item["id"], "subject": headers.get("subject", ""), "from": headers.get("from", ""), "body": body})
    return output
