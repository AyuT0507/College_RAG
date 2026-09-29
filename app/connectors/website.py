from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


def crawl(start_url: str, allowed_domains: set[str], max_pages: int = 50) -> list[dict]:
    """Public-page crawler restricted to an explicit domain allowlist."""
    if urlparse(start_url).hostname not in allowed_domains:
        raise ValueError("Start URL host must be on the configured allowlist")
    queue, seen, pages = deque([start_url]), set(), []
    while queue and len(pages) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        try:
            response = requests.get(url, timeout=15, allow_redirects=False,
                                    headers={"User-Agent": "CollegeAIResearchBot/0.1"})
            response.raise_for_status()
        except requests.RequestException:
            continue
        if "text/html" not in response.headers.get("Content-Type", ""):
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup(["script", "style", "nav", "footer", "header"]):
            node.decompose()
        text = " ".join(soup.get_text(" ", strip=True).split())
        if text:
            pages.append({"url": url, "title": soup.title.get_text(strip=True) if soup.title else url, "text": text})
        for anchor in soup.find_all("a", href=True):
            target = urljoin(url, anchor["href"].split("#")[0])
            parsed = urlparse(target)
            if parsed.scheme in {"http", "https"} and parsed.hostname in allowed_domains and target not in seen:
                queue.append(target)
    return pages
