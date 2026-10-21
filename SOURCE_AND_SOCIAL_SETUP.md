# KLAUS web sources and social network roadmap

## Current implementation

- KLAUS can read public RSS/Atom feeds configured through the GitHub Actions repository variable `KLAUS_SOURCE_FEEDS`.
- The feed reader runs once per scheduled execution, limits each feed to 12 entries and the total to 100 entries, ranks items with lightweight keyword matching, and adds a small set of relevant links as context for the AI.
- A source being listed does not mean its claims are verified. KLAUS is instructed to treat feed content as untrusted input, not copy it, and include a source link when using a specific news item.
- With no configured feeds, KLAUS continues with its existing evergreen prompt behavior.
- Real posting remains guarded by the root `DRY_RUN` file. Keep its contents as `true`.
- The video pipeline only recognizes explicit HTTPS video enclosures in configured feeds (RSS `enclosures` / Media RSS `media_content`). It does not scrape platform pages, bypass login/DRM, or use third-party downloader sites.
- Video downloads are limited to 50 MB maximum and require an HTTP `Content-Type` beginning with `video/`. In dry-run mode, a matching direct video can be downloaded into a temporary directory for validation, logged, and then deleted; Telegram uploads are skipped.
- YouTube links are used as source context, not downloaded as video files. YouTube's API policies prohibit downloading/storing audiovisual content without prior written approval. Instagram/TikTok/Reddit platform page URLs are also not treated as direct file URLs; authorized direct media enclosures may work if a feed provides them.
- Optional workflow variables: `KLAUS_VIDEO_DOWNLOAD_ENABLED` (default true) and `KLAUS_VIDEO_MAX_BYTES` (bounded to 50,000,000 bytes). No new API keys are needed for this feed-enclosure approach.

## Configure feeds

Open **Settings → Secrets and variables → Actions → Variables** in the repository and create a repository variable named `KLAUS_SOURCE_FEEDS`.

Use one feed per line, in this format:

```text
news|https://example.com/news/rss.xml
blogs|https://example.com/blog/feed.xml
reddit|https://www.reddit.com/r/example/.rss
youtube|https://www.youtube.com/feeds/videos.xml?channel_id=YOUR_PUBLIC_CHANNEL_ID
other|https://example.com/atom.xml
```

Replace example URLs with feeds you have checked and want KLAUS to use. Supported labels are `rss`, `news`, `blogs`, `reddit`, `youtube`, and `other`. A URL without a label is also accepted and classified heuristically. Do not put API keys or private tokens in this variable. The feed content is public, but the variable itself is not a secret store.

## Social network integration plan

Social publishing is **not enabled by this change**. KLAUS currently only contains a Telegram publisher, and its global dry-run guard must remain on until the owner explicitly approves live publishing. Each additional network needs its own adapter, credentials stored only as GitHub Actions secrets, platform-specific validation, and a test mode.

| Platform | Official path | Important prerequisites / constraints |
| --- | --- | --- |
| Telegram | Bot API | Bot token and posting rights in each destination; existing publisher only |
| Instagram | Meta Instagram Graph API | Eligible professional account, linked Meta assets, app permissions and review; media publishing has specific requirements |
| X | X API | Developer project/app and access tier; API access may be usage-billed |
| Facebook | Meta Graph API | Page access token, Page permissions and app review as required |
| LinkedIn | LinkedIn API | Member/organization authorization and the relevant sharing permissions/products |
| TikTok | TikTok Content Posting API | Developer app, approved scopes and user authorization; unaudited direct posts may be private-only |

Prefer official APIs and OAuth. Do not use browser automation, scraped private endpoints, password collection, or other methods that bypass platform controls. For each platform, implement publishing only after its credential requirements and current access terms are confirmed. Until then, keep those adapters unavailable and do not claim posts have been sent.

## Recommended rollout

1. Configure a few trusted RSS feeds and verify that the Actions logs show entries loaded.
2. Run with `DRY_RUN=true`; inspect the generated previews and source links.
3. Add Reddit and YouTube feeds as normal RSS sources where available; use official APIs only if a feed is insufficient.
4. Implement and validate each social publishing adapter separately, starting with the easiest platform where official access is available.
5. Keep all live publishing off until the owner explicitly authorizes it.
