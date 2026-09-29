from google import genai

from app.config import get_settings


def answer(query: str, evidence: list[dict]) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        return "Gemini is not configured. Retrieved evidence: " + "\n".join(e["text"][:500] for e in evidence)
    client = genai.Client(api_key=settings.gemini_api_key)
    context = "\n\n".join(f"[Document {e['document_id']}] {e['text']}" for e in evidence)
    response = client.models.generate_content(model=settings.gemini_model,
        contents=f"Answer using only the supplied college evidence. If it is insufficient, say so. Cite document IDs.\n\nQuestion: {query}\n\nEvidence:\n{context}")
    return response.text or "I could not produce an answer from the available evidence."
