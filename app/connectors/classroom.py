from app.connectors.google_common import service


def list_courses(token_json: str, limit: int = 100) -> list[dict]:
    api = service(token_json, "classroom", "v1")
    return api.courses().list(pageSize=min(limit, 100)).execute().get("courses", [])


def list_coursework(token_json: str, course_id: str, limit: int = 100) -> list[dict]:
    api = service(token_json, "classroom", "v1")
    return api.courses().courseWork().list(courseId=course_id, pageSize=min(limit, 100)).execute().get("courseWork", [])
