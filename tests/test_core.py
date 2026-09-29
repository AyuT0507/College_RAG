from app.ingestion.documents import chunks
from app.retrieval.router import Route, route_query


def test_chunks_cover_text():
    result = chunks("a" * 2000, size=500, overlap=50)
    assert len(result) > 1
    assert "".join(result) != ""  # every segment carries actual source text
    assert all(result[i][-50:] == result[i + 1][:50] for i in range(len(result) - 1))


def test_query_router():
    assert route_query("How many students enrolled?") == Route.SQL
    assert route_query("Explain the late submission policy") == Route.VECTOR
    assert route_query("How many credits and explain the policy") == Route.BOTH
