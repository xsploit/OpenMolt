"""
Serper API client: search, news, scrape. Keys go in bot-config.json (gitignored).
https://serper.dev – Google search, news, and scrape.
"""
import requests

SEARCH_URL = "https://google.serper.dev/search"
NEWS_URL = "https://google.serper.dev/news"
SCRAPE_URL = "https://scrape.serper.dev/"


def _headers(api_key: str) -> dict:
    return {"X-API-KEY": api_key, "Content-Type": "application/json"}


def search(api_key: str, q: str, num: int = 5) -> dict:
    """POST /search – Google search. Returns organic results, etc."""
    if not api_key or not q:
        return {}
    r = requests.post(
        SEARCH_URL,
        headers=_headers(api_key),
        json={"q": q, "num": num},
        timeout=15,
    )
    r.raise_for_status()
    return r.json() if r.text else {}


def news(api_key: str, q: str, num: int = 5) -> dict:
    """POST /news – Google news search."""
    if not api_key or not q:
        return {}
    r = requests.post(
        NEWS_URL,
        headers=_headers(api_key),
        json={"q": q, "num": num},
        timeout=15,
    )
    r.raise_for_status()
    return r.json() if r.text else {}


def scrape(api_key: str, url: str) -> dict:
    """POST scrape.serper.dev – scrape a URL. url must be full https://..."""
    if not api_key or not url or not url.startswith("http"):
        return {}
    r = requests.post(
        SCRAPE_URL,
        headers=_headers(api_key),
        json={"url": url},
        timeout=15,
    )
    r.raise_for_status()
    return r.json() if r.text else {}


def research_summary(api_key: str, query: str, use_news: bool = False) -> str:
    """
    Run search (and optionally news), return a short text block to inject into context.
    Used by the post agent when brain returns research_query.
    """
    lines = []
    try:
        data = search(api_key, query, num=5)
        organic = data.get("organic") or []
        if organic:
            lines.append("Search results:")
            for i, o in enumerate(organic[:5], 1):
                title = o.get("title") or ""
                snippet = o.get("snippet") or ""
                link = o.get("link") or ""
                lines.append(f"{i}. {title}\n   {snippet}\n   {link}")
    except Exception as e:
        lines.append(f"Search error: {e}")
    if use_news:
        try:
            data = news(api_key, query, num=3)
            news_list = data.get("news") or []
            if news_list:
                lines.append("\nNews:")
                for n in news_list[:3]:
                    title = n.get("title") or ""
                    snippet = n.get("snippet") or ""
                    lines.append(f"- {title}\n  {snippet}")
        except Exception as e:
            lines.append(f"News error: {e}")
    return "\n".join(lines) if lines else "(no research results)"
