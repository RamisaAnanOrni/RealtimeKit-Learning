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
    print(f"DEBUG shorten_url called with: {long_url[:80]}", flush=True)
    if not getattr(settings, "ENABLE_URL_SHORTENING", True):
        print("DEBUG: ENABLE_URL_SHORTENING is OFF, returning original", flush=True)
        return long_url

    try:
        token = getattr(settings, "BITLY_TOKEN", "").strip()
        print(f"DEBUG: BITLY_TOKEN exists={bool(token)}, preview={token[:6] if token else 'NONE'}", flush=True)
        if not token:
            print("DEBUG: BITLY_TOKEN is empty; skipping shortening", flush=True)
            return long_url
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        print(f"DEBUG: Calling Bitly API with long_url = {long_url[:80]}", flush=True)
        resp = requests.post(
            "https://api-ssl.bitly.com/v4/shorten",
            json={"long_url": long_url},
            headers=headers,
            timeout=5,
        )
        print(f"DEBUG BITLY: status={resp.status_code}, body={resp.text[:200]}", flush=True)
        if resp.status_code in (200, 201):
            data = resp.json()
            link = data.get("link")
            print(f"DEBUG BITLY: link={link}, data_keys={list(data.keys())}", flush=True)
            if link and _looks_like_url(link):
                return link

    except Exception:
        logger.exception("URL shortening failed; falling back to original URL")

    return long_url


def shorten_url_required(long_url: str) -> str:
    """Shorten a URL or raise instead of allowing a raw token URL to persist."""
    shortened_url = shorten_url(long_url)
    if shortened_url == long_url:
        raise RuntimeError(
            "Bitly did not shorten the meeting URL; the meeting was not finalized."
        )
    return shortened_url
