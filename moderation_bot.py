"""Optional always-on Telegram discussion-group moderator for KLAUS.

Run as a separate long-lived process. The scheduled publisher must not also
call getUpdates. The bot needs administrator permission to delete messages in
the linked discussion group. Configure KLAUS_DISCUSSION_CHAT_ID with that group
ID. This intentionally uses conservative anti-spam rules only.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections import defaultdict, deque

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("KLAUS_DISCUSSION_CHAT_ID", "").strip()
BLOCK_LINKS = os.getenv("KLAUS_MOD_BLOCK_LINKS", "true").lower() == "true"
MAX_MESSAGES_PER_MINUTE = max(5, int(os.getenv("KLAUS_MOD_MAX_PER_MINUTE", "12")))
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "KLAUS-Discussion-Moderator/1.0"})
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger("KLAUS-MOD")
LINK_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/|[\w.-]+\.[a-z]{2,}/)", re.I)
message_times: dict[int, deque[float]] = defaultdict(deque)


def api(method: str, payload: dict, timeout: int = 40):
    response = HTTP.post(f"{API}/{method}", json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data.get("result)


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
    if any(entity.get("type") in {"url", "text_link"} for entity in entities):
        if BLOCK_LINKS:
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


def main():
    if not TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN environment variable.")
    if not CHAT_ID:
        raise SystemExit("Missing KLAUS_DISCUSSION_CHAT_ID environment variable.")
    webhook = api("getWebhookInfo", {})
    if webhook.get("url"):
        raise SystemExit(
            "A Telegram webhook is configured for this bot. Disable it deliberately "
            "before running the long-polling moderator; this process will not change it automatically."
        )
    offset = 0
    LOG.info("KLAUS moderator started for configured discussion group.")
    while True:
        try:
            updates = api("getUpdates", {
                "offset": offset,
                "timeout": 25,
                "allowed_updates": ["message", "edited_message"],
            }, timeout=35)
            for update in updates:
                offset = max(offset, int(update.get("update_id", 0)) + 1)
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                delete, reason = should_delete(message)
                if delete:
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
