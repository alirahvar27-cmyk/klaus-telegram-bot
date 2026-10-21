# KLAUS: final setup checklist

## Implemented in repository
- Scheduled publisher for the 14 configured Telegram channels.
- AI content generation using any configured supported AI provider.
- RSS/Atom ingestion, direct feed video/audio enclosure detection, Wikimedia Commons image lookup with attribution.
- Per-channel randomized content-format rotation among text, image, video, audio, app/tool introduction, and poll. Video/audio are selected only if a configured feed exposes a direct media enclosure.
- Telegram poll publishing and an optional routine to set channel reaction options.
- A separate conservative discussion-group moderator (moderation_bot.py) for link spam and message floods.
- DRY_RUN safety gate; current file should remain "true".

## Not yet verified
- CI/test success and a complete live end-to-end run.
- Credentials and access permissions for the Telegram bot and AI provider.
- Reaction-setting API permissions on every channel.
- Discussion-group moderator running continuously on a host.
- Platform-specific authenticated adapters (YouTube, Instagram, TikTok, Facebook, X, Reddit).

## Required one-time user setup
1. In GitHub repository Settings > Secrets and variables > Actions, add GEMINI_API_KEY (or another supported AI provider key). Keep the key private.
2. Add TELEGRAM_BOT_TOKEN as a secret and add the bot as an administrator to each target channel. Grant posting rights; grant reaction-setting rights if Telegram requires them.
3. Configure KLAUS_SOURCE_FEEDS as a repository variable with public RSS/Atom feed URLs whose content/media reuse terms allow the intended use. Do not add social media profile URLs as if they were RSS feeds.
4. To moderate comments, create a Telegram group, link it to the channel(s) in Telegram, add the bot as an admin with delete-message permission, and set KLAUS_DISCUSSION_CHAT_ID on the always-on moderator host.
5. Deploy the moderator as a continuously running worker using the repository Dockerfile. Do not run two long-polling copies with the same bot token.
6. For official social APIs, register apps and obtain the access/scopes each platform requires. Add tokens to GitHub Secrets only after the corresponding adapter is implemented and tested.

## Known limitations
- The current scheduled workflow does not create spoken voice messages (TTS), compose/edit videos, or generate original music. Those require a chosen TTS/media service and additional implementation.
- Audio/music publishing is only supported for direct audio enclosures surfaced by configured feeds; use only media whose license/permission allows redistribution.
- App/tool introduction is a generated informational post, not an automatic software installation.
- The discussion moderator uses conservative link and flood rules; it is not an AI human-like moderator and needs testing in a real linked group.
- API access alone does not grant permission to repost copyrighted media.
- Live publishing remains disabled while DRY_RUN=true.
