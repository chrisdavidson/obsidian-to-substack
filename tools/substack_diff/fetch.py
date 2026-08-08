"""Fetch published Substack posts, with an on-disk cache.

Substack rejects the default urllib user agent with HTTP 403, so every request
carries a browser UA. Responses are cached so repeated diff runs don't re-hit
the network — the cache is what makes EVID-01 cheap to re-run.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DEFAULT_CACHE = Path(".cache/substack")


class FetchError(RuntimeError):
    """Raised when a post or archive cannot be retrieved."""


def _get(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"Network error fetching {url}: {exc.reason}") from exc


def fetch_archive(publication: str, limit: int = 50) -> list[dict]:
    """Return archive entries (slug, title, post_date) for a publication."""
    url = f"https://{publication}/api/v1/archive?sort=new&limit={limit}"
    try:
        entries = json.loads(_get(url))
    except json.JSONDecodeError as exc:
        raise FetchError(f"Archive response was not JSON: {exc}") from exc

    return [
        {
            "slug": entry.get("slug", ""),
            "title": entry.get("title", ""),
            "post_date": (entry.get("post_date") or "")[:10],
        }
        for entry in entries
    ]


def fetch_post(
    publication: str,
    slug: str,
    cache_dir: Path = DEFAULT_CACHE,
    refresh: bool = False,
) -> str:
    """Return the raw HTML of a published post, using the cache when possible."""
    cache_path = Path(cache_dir) / f"{slug}.html"

    if cache_path.exists() and not refresh:
        logger.debug("cache hit: %s", slug)
        return cache_path.read_text(encoding="utf-8")

    url = f"https://{publication}/p/{slug}"
    logger.info("fetching %s", url)
    html = _get(url).decode("utf-8", errors="replace")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html
