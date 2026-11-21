try:
    from google import genai
except ImportError:
    genai = None

from app.config import get_settings


def answer(query: str, evidence: list[dict]) -> str:
    """
    Generate an answer grounded strictly in verified college evidence.
    If evidence is missing or insufficient, states so clearly (Requirement 6).
    """
    if not evidence:
        return (
            "The indexed college sources do not contain enough information to answer this question. "
            "Please refine your query or submit feedback for staff review."
        )

    settings = get_settings()
    if not settings.gemini_api_key:
        lines = ["Gemini API key is not configured. Retrieved sources:\n"]
        for e in evidence:
            doc_label = f"Document {e.get('document_id')}"
            if e.get("title"):
                doc_label += f" ({e['title']})"
            lines.append(f"• [{doc_label}]: {e['text'][:300]}...")
        return "\n".join(lines)

    if not genai:
        return "google-genai package is not installed. Run 'pip install google-genai'."
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        formatted_evidence = []
        for e in evidence:
            doc_id = e.get("document_id")
            title = e.get("title", "Document")
            version = e.get("version", 1)
            formatted_evidence.append(f"[{title} (ID: {doc_id}, v{version})]: {e['text']}")

        context = "\n\n".join(formatted_evidence)
        prompt = (
            "You are an authoritative college information assistant. "
            "Answer the question using ONLY the provided verified college evidence below. "
            "Rules:\n"
            "1. If the provided evidence does not contain sufficient facts to answer the question, "
            "explicitly state: 'The indexed college sources do not contain enough information to answer this question.'\n"
            "2. Never hallucinate or assume institutional policies, grades, or requirements not present in evidence.\n"
            "3. Cite the document names and IDs in your answer so users can verify the source.\n\n"
            f"Question: {query}\n\n"
            f"Verified Evidence:\n{context}"
        )

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        return response.text or "The indexed college sources do not contain enough information to answer this question."
    except Exception as exc:
        return f"Error contacting AI service: {exc}. Please check your GEMINI_API_KEY."
