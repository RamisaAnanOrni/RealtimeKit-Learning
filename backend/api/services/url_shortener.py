import logging
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _looks_like_url(s: str) -> bool:
    try:
        p = urlparse(s)
        return bool(p.scheme and p.netloc)
    except Exception:
        return False


def shorten_url(long_url: str) -> str:
    """Return a shortened URL for `long_url` using configured provider.

    This is best-effort: on any error, return the original `long_url` so
    callers never fail because of the shortener.
    """
    if not getattr(settings, "ENABLE_URL_SHORTENING", True):
        return long_url

    try:
        # Primary provider: Bitly (requires BITLY_TOKEN in settings)
        token = getattr(settings, "BITLY_TOKEN", "").strip()
        if not token:
            logger.warning("BITLY_TOKEN is not configured; skipping shortening")
            return long_url
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            "https://api-ssl.bitly.com/v4/shorten",
            json={"long_url": long_url},
            headers=headers,
            timeout=5,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            link = data.get("link")
            if link and _looks_like_url(link):
                return link

    except Exception:
        logger.exception("URL shortening failed; falling back to original URL")

    return long_url
