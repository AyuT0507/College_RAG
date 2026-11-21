from functools import lru_cache

from app.config import get_settings


@lru_cache
def collection():
    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    except ImportError:
        return None

    client = chromadb.PersistentClient(path=get_settings().chroma_path)
    embedder = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    return client.get_or_create_collection("college_documents", embedding_function=embedder)


def upsert_document(doc_id: int, owner_id: int | None, visibility: str, allowed_roles: str, pieces: list[str]):
    col = collection()
    if col is None:
        return  # Vector storage disabled if chromadb is not installed
    col.delete(where={"document_id": str(doc_id)})
    if pieces:
        ids = [f"{doc_id}:{i}" for i in range(len(pieces))]
        metadata = [
            {
                "document_id": str(doc_id),
                "owner_id": str(owner_id or ""),
                "visibility": visibility,
                "allowed_roles": allowed_roles,
                "chunk": i,
            }
            for i in range(len(pieces))
        ]
        col.add(ids=ids, documents=pieces, metadatas=metadata)


def search(query: str, doc_ids: set[int], limit: int = 8) -> list[dict]:
    if not doc_ids:
        return []
    col = collection()
    if col is None:
        return []
    found = col.query(query_texts=[query], n_results=min(50, max(limit * 4, limit)))
    result = []
    for text, meta, distance in zip(found["documents"][0], found["metadatas"][0], found["distances"][0]):
        if int(meta["document_id"]) in doc_ids:
            result.append({"text": text, "document_id": int(meta["document_id"]), "distance": distance})
        if len(result) == limit:
            break
    return result
