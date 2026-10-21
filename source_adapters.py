"""Shared normalized source schema for KLAUS ingestion adapters.

Platform-specific adapters should return this schema rather than adding
platform-specific fields to channel publishing logic.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse


def _clean(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def stable_source_id(platform: str, url: str, source_id: str = "") -> str:
    """Build a stable non-secret identifier for duplicate tracking."""
    raw_id = _clean(source_id, 500) or _clean(url, 1500)
    raw = f"{_clean(platform, 40).lower()}:{raw_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_source_item(
    *,
    platform: str,
    source_name: str,
    title: str,
    summary: str,
    url: str,
    published: str = "",
    video_url: str = "",
    source_id: str = "",
    media_type: str = "link",
    rights_status: str = "unknown",
) -> dict:
    """Return a predictable, bounded record shared by all source adapters."""
    canonical_url = _clean(url, 1500)
    media_url = _clean(video_url, 1500)
    parsed = urlparse(canonical_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Source item requires an absolute HTTP(S) URL")

    normalized_platform = _clean(platform, 40).lower() or "other"
    normalized_media_type = _clean(media_type, 30).lower() or "link"
    if media_url and normalized_media_type == "link":
        normalized_media_type = "video"

    return {
        "source_id": stable_source_id(normalized_platform, canonical_url, source_id),
        "platform": normalized_platform,
        "category": normalized_platform,
        "source_name": _clean(source_name, 160),
        "feed": _clean(source_name, 160),
        "title": _clean(title, 240),
        "summary": _clean(summary, 700),
        "url": canonical_url,
        "link": canonical_url,
        "published": _clean(published, 80),
        "media_type": normalized_media_type,
        "video_url": media_url,
        # Discovery/API access does not imply permission to republish media.
        "rights_status": _clean(rights_status, 40).lower() or "unknown",
    }
