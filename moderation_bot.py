"""Optional always-on Telegram moderator and authorized channel relay.

The worker uses Telegram long polling, so only one process may call getUpdates
for a given bot token. The scheduled publisher does not poll updates.
For relay, add the bot as an administrator to source channels you control or
are authorized to redistribute, and grant posting rights in destination channels.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("KLAUS_DISCUSSION_CHAT_ID", "").strip()
BLOCK_LINKS = os.getenv("KLAUS_MOD_BLOCK_LINKS", "true").lower() == "true"
MAX_MESSAGES_PER_MINUTE = max(5, int(os.getenv("KLAUS_MOD_MAX_PER_MINUTE", "12")))
SOURCE_CHANNELS = {
    item.strip().lstrip("@").lower()
    for item in re.split(r"[,;\n]+", os.getenv("KLAUS_SOURCE_CHANNELS", ""))
    if item.strip()
}
RELAY_TARGETS = [
    item.strip() for item in re.split(r"[,;\n]+", os.getenv("KLAUS_RELAY_TARGETS", ""))
    if item.strip()
]
DRY_RUN_FILE = Path(os.getenv("KLAUS_DRY_RUN_FILE", "DRY_RUN"))
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "KLAUS-Discussion-Moderator/1.0"})
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger("KLAUS-MOD")
LINK_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/|[\w.-]+\.[a-z]{2,}/)", re.I)
message_times: dict[int, deque[float]] = defaultdict(deque)


def live_enabled() -> bool:
    """Fail closed: relay/moderation writes stay disabled unless DRY_RUN says false."""
    try:
        return DRY_RUN_FILE.read_text(encoding="utf-8").strip().lower() == "false"
    except OSError:
        return False


def api(method: str, payload: dict, timeout: int = 40):
    response = HTTP.post(f"{API}/{method}", json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data.get("result")


def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = api("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        return member.get("status") in {"creator", "administrator"}
    except Exception as exc:
        LOG.warning("Could not verify sender role; not deleting on role-check failure: %s", exc)
        return True


def should_delete(message: dict) -> tuple[bool, str]:
    chat = message.get("chat", {})
    if CHAT_ID and str(chat.get("id")) != CHAT_ID:
        return False, ""
    if chat.get("type") not in {"group", "supergroup"}:
        return False, ""
    sender = message.get("from", {})
    user_id = sender.get("id")
    if not user_id or sender.get("is_bot") or is_admin(chat["id"], user_id):
        return False, ""
    text = str(message.get("text") or message.get("caption") or "")
    entities = message.get("entities", []) + message.get("caption_entities", [])
    if any(entity.get("type") in {"url", "text_link"} for entity in entities) and BLOCK_LINKS:
        return True, "link in discussion group"
    if BLOCK_LINKS and LINK_RE.search(text):
        return True, "link-like spam in discussion group"
    now = time.monotonic()
    times = message_times[user_id]
    while times and now - times[0] > 60:
        times.popleft()
    times.append(now)
    if len(times) > MAX_MESSAGES_PER_MINUTE:
        return True, "message flood"
    return False, ""


def relay_channel_post(message: dict) -> None:
    """Forward new posts from explicitly configured source channels, preserving attribution."""
    if not SOURCE_CHANNELS or not RELAY_TARGETS:
        return
    chat = message.get("chat", {})
    username = str(chat.get("username", "")).lower()
    if not username or username not in SOURCE_CHANNELS:
        return
    if not live_enabled():
        LOG.info("DRY RUN: eligible source post @%s/%s not forwarded", username, message.get("message_id"))
        return
    message_id = message.get("message_id")
    if not message_id:
        return
    for target in RELAY_TARGETS:
        if target.lstrip("@").lower() == username:
            continue
        try:
            api("forwardMessage", {
                "chat_id": target,
                "from_chat_id": chat.get("id"),
                "message_id": message_id,
            })
            LOG.info("Forwarded @%s/%s to %s", username, message_id, target)
        except Exception as exc:
            LOG.warning("Could not forward @%s/%s to %s: %s", username, message_id, target, exc)


def main():
    if not TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN environment variable.")
    if not CHAT_ID and not (SOURCE_CHANNELS and RELAY_TARGETS):
        raise SystemExit(
            "Configure KLAUS_DISCUSSION_CHAT_ID for moderation, or both "
            "KLAUS_SOURCE_CHANNELS and KLAUS_RELAY_TARGETS for channel relay."
        )
    webhook = api("getWebhookInfo", {})
    if webhook.get("url"):
        raise SystemExit(
            "A Telegram webhook is configured for this bot. Disable it deliberately "
            "before running the long-polling worker; this process will not change it automatically."
        )
    offset = 0
    LOG.info(
        "KLAUS worker started; moderation=%s source_channels=%d relay_targets=%d live=%s",
        bool(CHAT_ID), len(SOURCE_CHANNELS), len(RELAY_TARGETS), live_enabled()
    )
    while True:
        try:
            updates = api("getUpdates", {
                "offset": offset,
                "timeout": 25,
                "allowed_updates": ["message", "edited_message", "channel_post", "edited_channel_post"],
            }, timeout=35)
            for update in updates:
                offset = max(offset, int(update.get("update_id", 0)) + 1)
                channel_post = update.get("channel_post") or update.get("edited_channel_post")
                if channel_post:
                    relay_channel_post(channel_post)
                    continue
                message = update.get("message") or update.get("edited_message")
                if not message or not CHAT_ID:
                    continue
                delete, reason = should_delete(message)
                if delete:
                    if not live_enabled():
                        LOG.info("DRY RUN: would delete message %s (%s)", message.get("message_id"), reason)
                        continue
                    try:
                        api("deleteMessage", {
                            "chat_id": message["chat"]["id"],
                            "message_id": message["message_id"],
                        })
                        LOG.info("Deleted message %s (%s)", message["message_id"], reason)
                    except Exception as exc:
                        LOG.warning("Could not delete message: %s", exc)
        except Exception as exc:
            LOG.warning("Polling error; retrying shortly: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
