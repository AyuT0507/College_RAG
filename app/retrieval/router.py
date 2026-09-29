import re
from enum import StrEnum


class Route(StrEnum):
    SQL = "sql"
    VECTOR = "vector"
    BOTH = "both"


def route_query(query: str) -> Route:
    q = query.lower()
    structured = bool(re.search(r"\b(how many|count|list all|which students|enrolled|attendance|grade|gpa|credits|course code)\b", q))
    semantic = bool(re.search(r"\b(explain|summarize|what does|policy|describe|how do i|why|requirements)\b", q))
    if structured and semantic:
        return Route.BOTH
    if structured:
        return Route.SQL
    if semantic:
        return Route.VECTOR
    return Route.BOTH
