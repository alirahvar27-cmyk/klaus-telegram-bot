# KLAUS Source Integration Plan

KLAUS is intended to use one source-ingestion pipeline with platform-specific adapters. Do not add every platform as an RSS URL and do not duplicate source configuration across channels.

## Current status

- Implemented: configurable RSS/Atom ingestion through `KLAUS_SOURCE_FEEDS`.
- Implemented: shared normalized source-item schema (`source_id`, platform, source name, canonical URL, publication time, media type, video URL, and rights status).
- Implemented: unit tests for schema normalization, stable IDs, and URL validation.
- Implemented: direct video enclosure detection from RSS/Atom and guarded temporary downloads, subject to source configuration and rights.
- Not implemented yet: dedicated authenticated API adapters for YouTube, Instagram, TikTok, Facebook, X, Reddit API, and other social platforms.
- Safety: `DRY_RUN` must remain `true` until the user explicitly authorizes live posting.

## Target source catalog

Treat this as a roadmap, not a claim that all integrations are active.

### General web and publisher feeds
- RSS and Atom feeds from news publishers, specialist websites, blogs, public research sources, and official organization feeds.
- Public sitemaps/pages only where automated access is permitted and technically safe.

### Social and community platforms
- YouTube Data API / authorized feeds.
- Instagram Graph API for eligible professional accounts and approved permissions.
- TikTok official APIs, subject to app review, scopes, and posting/content access requirements.
- Facebook Graph API for eligible Pages and approved permissions.
- X API, subject to plan/access entitlement.
- Reddit API using OAuth and applicable developer/data terms.
- Other services only after checking official API availability, access approval, and terms.

### Other media and discovery sources
- Public podcast RSS feeds and media enclosures.
- Official publisher video feeds and authorized direct media URLs.
- Public research, science, technology, finance, travel, food, entertainment, humor, and education feeds.

## Integration rules

1. A single normalized item schema should carry source platform, source account/feed, title, text/summary, canonical URL, publish timestamp, media metadata, permissions/usage notes, and stable source ID.
2. Platform adapters should normalize into that schema; channel logic should not contain per-platform scraping.
3. Use official APIs or documented public feeds where available. Do not bypass logins, DRM, rate limits, access controls, or platform restrictions.
4. API keys/tokens belong only in GitHub Actions Secrets, never in source code or chat.
5. API access does not itself grant copyright or reposting permission. Only download/reuse media where permitted.
6. Add per-platform rate limits, retry/backoff, duplicate detection, provenance logging, and source health reporting.
7. Keep all actual publishing behind the existing `DRY_RUN` safety gate. No live posting without explicit user approval.
8. Build and test adapters one at a time; mark each as active only after tests and credentials are confirmed.

## Planned activation order

1. Validate the existing RSS/Atom pipeline and initial feed list.
2. Add official API adapters for platforms the user wants and is eligible to access.
3. Add media preparation and licensing/permission checks.
4. Verify Telegram destination credentials and permissions.
5. Run dry-run tests and review logs.
6. Enable live publishing only after explicit user approval.


See also [KLAUS final setup checklist](FINAL_SETUP.md) for current implementation boundaries, required credentials, and deployment steps.
