# KLAUS: final setup checklist

## Implemented in repository
- Scheduled publisher for the 14 configured Telegram channels.
- AI content generation using any configured supported AI provider.
- RSS/Atom ingestion, direct feed video/audio enclosure detection, Wikimedia Commons image lookup with attribution.
- Per-channel randomized content-format rotation among text, image, video, audio, app/tool introduction, and poll. Video/audio are selected only if a configured feed exposes a direct media enclosure.
- Telegram poll publishing and an optional routine to set channel reaction options.
- Long-running worker for conservative discussion-group moderation and an opt-in, allowlisted Telegram channel relay.
- Relay now uses `copyMessage` for media and `sendMessage` for text, so destination posts do not show Telegram's forwarded-from header. It appends the configured KLAUS brand tag and a direct source-post link. It handles new posts only; it cannot fetch historical posts or discover arbitrary Explore/Trending content.
- Relay and moderation actions fail closed unless the deployed `DRY_RUN` file contains exactly `false`. The repository default is `true`.

## Not yet verified
- CI/test success and a complete live end-to-end run.
- Credentials and access permissions for the Telegram bot and AI provider.
- Reaction-setting API permissions on every channel.
- Discussion moderator/relay worker running continuously on a host.
- Platform-specific authenticated adapters (YouTube, Instagram, TikTok, Facebook, X, Reddit). Instagram Reel downloading/reposting is not implemented yet.
- Instagram Explore/Reels automatic discovery or arbitrary Reel downloading.

## Required one-time user setup
1. In GitHub repository Settings > Secrets and variables > Actions, add `GEMINI_API_KEY` (or another supported AI provider key). Keep the key private.
2. Add `TELEGRAM_BOT_TOKEN` as a secret. For publishing, add the bot as administrator to each destination channel and grant posting rights.
3. Configure `KLAUS_SOURCE_FEEDS` as a repository variable with public RSS/Atom feed URLs. The publisher can read feed entries and direct media enclosures exposed by the feed; it does not scrape every social network.
4. For the optional Telegram channel relay, configure the Render worker environment:
   - `TELEGRAM_BOT_TOKEN`: the bot token stored as a secret.
   - `KLAUS_SOURCE_CHANNELS`: comma-separated public usernames of source channels, without `@` if preferred.
   - `KLAUS_RELAY_TARGETS`: comma-separated destination channel usernames/IDs.\n   - `KLAUS_BRAND_TAG`: optional brand tag appended to each relayed post (defaults to `@KLAUS`; change it to your actual channel tag).
   - Add the bot as an administrator in each source channel so Telegram delivers new `channel_post` updates; the bot also needs posting rights in each destination channel.
   - The relay handles new posts after setup only. It cannot read old history from a channel where it has no access, and protected-content channels may reject forwarding.
5. To moderate comments, link a Telegram discussion group to the channel, add the bot as an admin with delete-message permission, and set `KLAUS_DISCUSSION_CHAT_ID` on the same worker. If relay and moderation are both enabled, they share one long-polling process/token; do not run a second poller with the same token.
6. Deploy the worker using the repository Dockerfile. Keep `DRY_RUN=true` during setup and testing. Do not change it to `false` until you explicitly decide to enable live copying/moderation/publishing.
7. For official social APIs, register apps and obtain required scopes. Add tokens only after the corresponding adapter is implemented and tested.

## Known limitations
- Public visibility does not mean unrestricted republication rights. Only relay media/content you are authorized to redistribute.
- The current scheduled publisher does not create spoken voice messages (TTS), compose/edit videos, or generate original music. Those require a chosen TTS/media service and additional implementation.
- Audio/music publishing is only supported for direct audio enclosures surfaced by configured feeds; use only media whose license/permission allows redistribution.
- App/tool introduction is a generated informational post, not an automatic software installation.
- The discussion moderator uses conservative link and flood rules; it is not an AI human-like moderator and needs testing in a real linked group.
- Live actions remain disabled while `DRY_RUN=true`.
