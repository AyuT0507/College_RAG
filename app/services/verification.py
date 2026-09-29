def verify_evidence(evidence: list[dict]) -> list[dict]:
    """Evidence is retained with its document ID for answer citations and audit."""
    return [item for item in evidence if item.get("text", "").strip() and item.get("document_id") is not None]
