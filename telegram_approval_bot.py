import json
import os
import re
import time
import logging
from pathlib import Path

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = os.getenv("ADMIN_USER_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
STATE_PATH = Path("telegram_approval_state.json")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "240"))
CHANNELS = {
    "@TechNamaFa": ("تک‌نما", "فناوری و گوشی هوشمند"),
    "@NbzeKhabar": ("نبض خبر", "خبر و سواد خبری"),
    "@Khndedoon": ("خنده‌دون", "سرگرمی و طنز"),
    "@RazKehann": ("راز کیهان", "نجوم و کیهان"),
    "@FilmGardFa": ("فیلم‌گرد", "فیلم و سینما"),
    "@MazeKhoooneh": ("مزه‌خونه", "آشپزی و غذا"),
    "@HaleKhoobDaiily": ("حال خوب", "عادت‌های سالم و حال خوب"),
    "@SafarkadehFa": ("سفرکده", "سفر و گردشگری"),
    "@ZehnAgahh": ("ذهن‌آگاه", "ذهن‌آگاهی و تمرکز"),
    "@PoolBalad": ("پول‌بلد", "سواد مالی"),
    "@LevelUpFa": ("لِوِل‌آپ", "بازی‌های ویدیویی"),
    "@NimeShabHorror": ("نیمه‌شب", "داستان ترسناک"),
    "@TradePulseFa": ("تریدپالس", "آموزش بازار و مدیریت ریسک"),
    "@NetPlusFa": ("نت‌پلاس", "شبکه و امنیت سایبری"),
}
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("KLAUS-Approval")
http = requests.Session()
http.headers.update({"User-Agent": "KLAUS-Approval/1.0"})

def load_state():
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("offset", 0)
            data.setdefault("pending", {})
            data.setdefault("edit_mode", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"offset": 0, "pending": {}, "edit_mode": {}}

STATE = load_state()

def save_state():
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE_PATH)

def api(method, payload=None, timeout=35):
    if not API:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    response = http.post(f"{API}/{method}", json=payload or {}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data}")
    return data["result"]

def is_admin(user_id):
    return bool(ADMIN_ID) and str(user_id) == ADMIN_ID

def send_text(chat_id, text, keyboard=None, entities=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    if entities:
        payload["entities"] = entities
    return api("sendMessage", payload)

def delete_private_message(chat_id, message_id):
    """Delete only a message in the private bot chat; never target channel posts."""
    try:
        api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    except Exception as exc:
        log.warning("Could not delete private chat message %s: %s", message_id, exc)

def cleanup_draft_messages(draft):
    chat_id = draft.get("chat_id")
    if not chat_id:
        return
    for message_id in dict.fromkeys(draft.get("cleanup_message_ids", [])):
        delete_private_message(chat_id, message_id)

def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2

def add_channel_branding(text, entities, channel, limit=None):
    """Preserve the source post verbatim; do not inject channel headers or footers."""
    text = text or ""
    max_text_len = limit if limit is not None else 4096
    # Telegram limits count UTF-16 code units. Avoid silently truncating the post.
    if utf16_len(text) > max_text_len:
        raise ValueError("متن از محدودیت تلگرام طولانی‌تر است؛ برای حفظ متن، انتشار متوقف شد.")
    return text, list(entities or [])

def clean_text_and_entities(text, entities):
    """Remove source ads while preserving Telegram text_link entities on their visible labels."""
    text = text or ""
    entities = entities or []

    def char_index(offset):
        units = 0
        for i, char in enumerate(text):
            if units >= offset:
                return i
            units += len(char.encode("utf-16-le")) // 2
        return len(text)

    spans = []
    for ent in entities:
        start = char_index(int(ent.get("offset", 0)))
        end = char_index(int(ent.get("offset", 0)) + int(ent.get("length", 0)))
        spans.append((start, end, ent))

    kept_parts, kept_entities = [], []
    old_pos, new_units = 0, 0
    promo_line = re.compile(
        r"(?:خرید|فروش).{0,45}(?:فیلترشکن|فیلتر شکن|آی\s*پی|\bip\b)|"
        r"(?:فیلترشکن|فیلتر شکن|وی\s*پی\s*ان|آی\s*پی|\bip\b).{0,35}(?:اختصاصی|اقتصادی|ارزان|خرید|فروش)",
        re.IGNORECASE
    )
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        line_end = old_pos + len(line)
        line_links = [(a, b, e) for a, b, e in spans if a < line_end and b > old_pos and e.get("type") == "text_link"]
        stripped = line.strip()
        is_promo = bool(promo_line.search(stripped))
        ad_words = re.search(
            r"(?i)(تبلیغ|تبلیغات|اسپانسر|حمایت مالی|عضویت در کانال|کانال ما|دنبال کنید|فالو کنید|"
            r"خرید از|سفارش دهید|ثبت سفارش|تخفیف ویژه|کد تخفیف|لینک خرید|برای خرید|"
            r"منبع|source|forwarded from|ارسالی از|کانال اصلی|وب.?سایت ما|سایت ما|"
            r"join us|follow us|subscribe|advertisement|sponsor|promo code)",
            stripped
        )
        is_handle_footer = bool(re.fullmatch(r"[\s✅✔️☑️〰️~—–-]*@[A-Za-z0-9_]{4,}[\s✅✔️☑️〰️~—–-]*", stripped))
        has_proxy_link = any(
            re.search(r"پروکسی|proxy|socks|همراه", text[a:b], re.IGNORECASE)
            for a, b, _ in line_links
        )
        label_only = bool(re.fullmatch(r"[\s•|·،,ـ]*(?:همراه|پروکسی)(?:[\s•|·،,ـ]*(?:همراه|پروکسی))*[\s•|·،,ـ]*", stripped, re.IGNORECASE))
        # Remove any line containing a non-proxy URL, including hidden Telegram text links.
        # Proxy links (Telegram proxy/socks URLs or clearly labelled proxy links) are preserved.
        def is_proxy_url(url):
            return bool(re.search(
                r"(?i)(?:t\.me|telegram\.me)/(?:proxy|socks)(?:[/?#]|$)|"
                r"(?:https?://)?(?:www\.)?[^\s]*\b(?:proxy|socks)\b[^\s]*",
                str(url or "")
            ))

        has_nonproxy_hidden_link = any(
            not is_proxy_url(ent.get("url", ""))
            for _, _, ent in line_links
        )
        visible_urls = re.findall(
            r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/)[^\s<>]+",
            stripped
        )
        has_nonproxy_visible_link = any(not is_proxy_url(url) for url in visible_urls)
        has_blocked_slogan = bool(re.search("اینترنت\\s*آزاد\\s*برای\\s*همه\\s*یا\\s*هیچکس", stripped, re.IGNORECASE))
        if has_blocked_slogan or is_promo or is_handle_footer or (ad_words and (line_links or visible_urls)) or (label_only and not has_proxy_link):
            old_pos += len(raw_line)
            continue
        if re.search(r"(?i)(منبع|source|forwarded from|ارسالی از|کانال اصلی|عضویت در کانال)", stripped):
            old_pos += len(raw_line)
            continue

        # Strip non-allowlisted URLs in-place; do not discard the useful text around them.
        def strip_external_url(match):
            url = match.group(0).rstrip(".,!?،؛:)")
            suffix = match.group(0)[len(url):]
            return ("" if not is_allowed_link(url) else url) + suffix

        cleaned_line = re.sub(
            r"(?i)(?:https?://|www\.)[^\s<>]+|(?:t\.me|telegram\.me)/[^\s<>]+|tg://[^\s<>]+",
            strip_external_url, line
        )
        if cleaned_line != line:
            line = cleaned_line
            line_links = []

        if not line.strip():
            old_pos += len(raw_line)
            continue
        line = line.rstrip()
        if kept_parts:
            kept_parts.append("\n")
            new_units += 1
        kept_parts.append(line)
        line_start_new_units = new_units
        for a, b, ent in line_links:
            if a >= old_pos and b <= old_pos + len(line):
                visible = text[a:b]
                new_ent = {
                    "type": "text_link",
                    "offset": line_start_new_units + utf16_len(text[old_pos:a]),
                    "length": utf16_len(visible),
                    "url": ent.get("url", "")
                }
                if new_ent["url"] and is_allowed_link(new_ent["url"]):
                    kept_entities.append(new_ent)
        new_units += utf16_len(line)
        old_pos += len(raw_line)

    cleaned = "".join(kept_parts).strip()
    if not cleaned:
        return "", []
    # Leading whitespace removal shifts entity offsets; adjust them exactly.
    leading = len("".join(kept_parts)) - len("".join(kept_parts).lstrip())
    if leading:
        shift = utf16_len("".join(kept_parts)[:leading])
        kept_entities = [dict(e, offset=max(0, e["offset"] - shift)) for e in kept_entities]
    return cleaned, sorted(kept_entities, key=lambda e: e["offset"])

def clean_text(text):
    return clean_text_and_entities(text, [])[0]


def is_allowed_link(url):
    """Allow only our own Telegram channels and actual Telegram proxy links."""
    value = str(url or "").strip().rstrip(".,!?،؛:)]}»")
    if not value:
        return True
    if re.match(r"(?i)^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:proxy|socks)(?:[/?#]|$)", value):
        return True
    if re.match(r"(?i)^tg://(?:proxy|socks)(?:[/?#]|$)", value):
        return True
    match = re.match(r"(?i)^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]+)(?:[/?#].*)?$", value)
    return bool(match and ("@" + match.group(1)).casefold() in {name.casefold() for name in CHANNELS})


def message_has_disallowed_link(message):
    """Detect visible URLs, hidden text links, and button URLs."""
    urls = []
    url_pattern = re.compile(
        r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/)[^\s<>]+|"
        r"(?<![@\w.-])(?:[a-z0-9-]+\.)+(?:com|net|org|ir|io|co|me|info|biz|app|dev|xyz|site|online|shop|live|pro|tv|gg|ly|ru|cn|uk|de|fr|us)(?:/[^\s<>]*)?"
    )
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).casefold()
                if normalized in {"url", "button_url", "web_url"} and isinstance(child, str):
                    if child.strip():
                        urls.append(child)
                elif isinstance(child, str) and normalized in {"text", "caption"}:
                    urls.extend(url_pattern.findall(child))
                elif isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(message)
    for key in ("entities", "caption_entities"):
        for entity in message.get(key, []) or []:
            if entity.get("type") == "text_link" and entity.get("url"):
                urls.append(entity["url"])
    return any(not is_allowed_link(url) for url in urls)

def detect_channel(text, media_type):
    t = (text or "").casefold()
    rules = [
        ("@FilmGardFa", ["فیلم", "سینما", "بازیگر", "سریال", "کارگردان", "تریلر", "movie", "cinema"]),
        ("@MazeKhoooneh", ["غذا", "آشپزی", "دستور پخت", "مواد لازم", "کیک", "خوراک", "recipe", "food"]),
        ("@RazKehann", ["فضا", "نجوم", "سیاره", "کهکشان", "ناسا", "کیهان", "تلسکوپ", "space", "nasa"]),
        ("@LevelUpFa", ["بازی", "گیم", "گیمینگ", "کنسول", "پلی‌استیشن", "ایکس‌باکس", "گیم‌پلی", "gaming", "game"]),
        ("@NetPlusFa", ["اینترنت", "شبکه", "vpn", "وی‌پی‌ان", "پروکسی", "dns", "امنیت سایبری", "سرور"]),
        ("@TradePulseFa", ["ترید", "بورس", "فارکس", "کریپتو", "بیت‌کوین", "معامله", "تحلیل تکنیکال", "trading", "bitcoin"]),
        ("@PoolBalad", ["پول", "پس‌انداز", "بودجه", "سرمایه‌گذاری", "تورم", "درآمد", "مالی"]),
        ("@NbzeKhabar", ["خبر", "گزارش", "اعلام شد", "فوری", "راستی‌آزمایی", "انتخابات", "حادثه"]),
        ("@SafarkadehFa", ["سفر", "گردشگری", "هتل", "طبیعت‌گردی", "ایرانگردی", "مسافرت", "جاذبه"]),
        ("@ZehnAgahh", ["تمرکز", "ذهن‌آگاهی", "مدیتیشن", "اضطراب", "تنفس", "mindfulness"]),
        ("@HaleKhoobDaiily", ["سلامتی", "عادت سالم", "خواب", "ورزش", "آرامش", "تندرستی"]),
        ("@TechNamaFa", ["گوشی", "موبایل", "اندروید", "آیفون", "اپل", "سامسونگ", "هوش مصنوعی", "فناوری", "تکنولوژی", "tech"]),
        ("@NimeShabHorror", ["ترسناک", "وحشت", "جن", "روح", "horror", "creepy"]),
        ("@Khndedoon", ["طنز", "خنده", "جوک", "میم", "بامزه", "خنده‌دار", "شوخی", "funny", "meme"]),
    ]
    for channel, words in rules:
        if any(word in t for word in words):
            return channel
    if media_type in {"sticker", "animation", "video_note"}:
        return "@Khndedoon"
    return "@NbzeKhabar" if len(t) > 180 else "@Khndedoon"

def extract_message(msg):
    """Extract ordinary Bot API messages and Telegram's rich_message forward payload."""
    media_kinds = ("photo", "video", "audio", "voice", "document", "animation", "video_note", "sticker")
    raw_text = msg.get("text") or msg.get("caption") or ""
    entities = msg.get("entities") or msg.get("caption_entities") or []
    media = None

    def walk_rich(value, parent_key=""):
        """Best-effort traversal for rich_message payloads whose schema may vary."""
        nonlocal raw_text, entities, media
        if isinstance(value, list):
            # Telegram photo arrays contain multiple sizes; choose the largest last.
            if parent_key == "photo" and value and all(isinstance(x, dict) and x.get("file_id") for x in value):
                media = {"type": "photo", "file_id": value[-1]["file_id"]}
                return
            for item in value:
                walk_rich(item, parent_key)
            return
        if not isinstance(value, dict):
            return

        for text_key in ("text", "caption"):
            candidate = value.get(text_key)
            if isinstance(candidate, str) and candidate.strip() and not raw_text:
                raw_text = candidate
                entities = value.get("entities") or value.get("caption_entities") or []

        for kind in media_kinds:
            candidate = value.get(kind)
            if candidate and media is None:
                if kind == "photo" and isinstance(candidate, list):
                    candidate = candidate[-1]
                if isinstance(candidate, dict) and candidate.get("file_id"):
                    media = {"type": kind, "file_id": candidate["file_id"]}
                elif isinstance(candidate, list):
                    walk_rich(candidate, kind)
        # Some rich payloads store a media object directly with file_id.
        if media is None and value.get("file_id"):
            inferred = parent_key if parent_key in media_kinds else value.get("type")
            if inferred in media_kinds:
                media = {"type": inferred, "file_id": value["file_id"]}
        for key, child in value.items():
            if key in {"text", "caption", "entities", "caption_entities", "file_id"}:
                continue
            if isinstance(child, (dict, list)):
                walk_rich(child, key)

    # Normal message fields first.
    for kind in media_kinds:
        value = msg.get(kind)
        if not value:
            continue
        if kind == "photo":
            value = value[-1] if isinstance(value, list) else value
        if isinstance(value, dict) and value.get("file_id"):
            media = {"type": kind, "file_id": value["file_id"]}
            break

    # Forwarded posts delivered by this Telegram integration expose rich_message
    # instead of the standard text/caption/photo fields. Rich text may be split
    # into multiple runs when formatting changes (bold, monospace/code, links).
    # Collect all leaf text runs in order rather than accepting only the first run.
    rich = msg.get("rich_message")

    def collect_rich_text(value, parent_key=""):
        """Collect post body text, excluding buttons/link menus and other metadata."""
        parts = []
        ignored_keys = {
            "entities", "caption_entities", "file_id", "reply_markup",
            "inline_keyboard", "keyboard", "buttons", "button", "url",
            "link", "links", "button_url", "web_app", "login_url",
            "switch_inline_query", "callback_data", "reply_to_markup",
        }
        if isinstance(value, list):
            for item in value:
                parts.extend(collect_rich_text(item, parent_key))
        elif isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(key).casefold()
                if normalized_key in ignored_keys:
                    continue
                if key in {"text", "caption"} and isinstance(child, str):
                    if child:
                        parts.append(child)
                elif isinstance(child, (dict, list)):
                    # Recurse into nested text runs, but never into link/button metadata.
                    parts.extend(collect_rich_text(child, key))
        return parts

    if rich:
        rich_parts = collect_rich_text(rich)
        if rich_parts:
            # Formatting runs are contiguous pieces of the same visible post;
            # keep their original whitespace/newlines and concatenate verbatim.
            raw_text = "".join(rich_parts)
            entities = []
        walk_rich(rich)

    # rich_message can carry text segments whose entity offsets are relative to
    # an inner fragment rather than the reconstructed full text. Applying those
    # offsets to the whole post can incorrectly delete ordinary paragraphs and
    # checklist lines. For rich forwards, prioritize preserving the complete
    # visible text; clean using visible text only, without potentially misaligned
    # hidden-link entities. Standard Bot API messages keep the full entity cleanup.
    if rich:
        text, clean_entities = clean_text_and_entities(raw_text, [])
    else:
        text, clean_entities = clean_text_and_entities(raw_text, entities)

    # Never restore the original after cleanup: doing so could reintroduce ads or links.
    return {"text": text, "entities": clean_entities, "media": media}

def preview(chat_id, draft_id):
    draft = STATE["pending"].get(draft_id)
    if not draft:
        return
    # Remove stale previews when editing text or changing the destination.
    for message_id in dict.fromkeys(draft.get("preview_message_ids", [])):
        delete_private_message(chat_id, message_id)
    draft["preview_message_ids"] = []
    channel = draft["channel"]
    title, topic = CHANNELS[channel]
    media = draft.get("media")
    caption, preview_entities = add_channel_branding(draft.get("text", ""), draft.get("entities", []), channel, limit=3900)
    try:
        draft.setdefault("cleanup_message_ids", [])
        # Always preview the cleaned extracted content. Native copyMessage bypasses
        # clean_text_and_entities and can reintroduce unwanted source links/ads.
        source_chat_id = draft.get("source_chat_id")
        source_message_id = draft.get("source_message_id")
        if media:
            kind = media["type"]
            method = {
                "photo": "sendPhoto", "video": "sendVideo", "audio": "sendAudio",
                "voice": "sendVoice", "document": "sendDocument",
                "animation": "sendAnimation", "video_note": "sendVideoNote",
                "sticker": "sendSticker",
            }[kind]
            field = "sticker" if kind == "sticker" else kind
            sent_media = api(method, {"chat_id": chat_id, field: media["file_id"]})
            draft["cleanup_message_ids"].append(sent_media["message_id"])
            draft["preview_message_ids"].append(sent_media["message_id"])
        if caption:
            sent_caption = send_text(chat_id, "📝 پیش‌نمایش متن:\n\n" + caption, entities=[dict(e, offset=e["offset"] + utf16_len("📝 پیش‌نمایش متن:\n\n")) for e in preview_entities])
            draft["cleanup_message_ids"].append(sent_caption["message_id"])
            draft["preview_message_ids"].append(sent_caption["message_id"])
        elif not media:
            warning = send_text(chat_id, "پست متنی خالی است؛ متن را ویرایش کن یا لغو کن.")
            draft["cleanup_message_ids"].append(warning["message_id"])
        controls = [
            [{"text": "✅ تأیید و انتشار", "callback_data": f"approve:{draft_id}"}],
            [{"text": "✏️ ویرایش متن", "callback_data": f"edit:{draft_id}"},
             {"text": "🔄 تغییر کانال", "callback_data": f"channels:{draft_id}"}],
            [{"text": "❌ لغو", "callback_data": f"cancel:{draft_id}"}],
        ]
        sent_controls = send_text(chat_id, f"📌 مقصد انتشار: {title} ({channel})\nموضوع: {topic}\n\nاگر درست است تأیید کن؛ تا پیش از تأیید منتشر نمی‌شود.", controls)
        draft["cleanup_message_ids"].append(sent_controls["message_id"])
        draft["preview_message_ids"].append(sent_controls["message_id"])
        save_state()
    except Exception as exc:
        log.exception("Preview failed: %s", exc)
        error_message = send_text(chat_id, "⚠️ پیش‌نمایش ارسال نشد. دوباره تلاش کن یا فایل کوچک‌تری بفرست.")
        draft.setdefault("cleanup_message_ids", []).append(error_message["message_id"])
        save_state()

def publish(draft):
    channel = draft["channel"]
    # Publish the cleaned draft rather than native-copying the source message,
    # which bypasses link/ad cleanup and can reintroduce unwanted source links.
    media = draft.get("media")
    text, post_entities = add_channel_branding(draft.get("text", ""), draft.get("entities", []), channel, limit=4096 if not media else 1024)
    if not media:
        if not text:
            raise ValueError("پست خالی است")
        return api("sendMessage", {"chat_id": channel, "text": text[:4096], "entities": post_entities, "disable_web_page_preview": False})
    kind = media["type"]
    method = {
        "photo": "sendPhoto", "video": "sendVideo", "audio": "sendAudio",
        "voice": "sendVoice", "document": "sendDocument",
        "animation": "sendAnimation", "video_note": "sendVideoNote",
        "sticker": "sendSticker",
    }[kind]
    field = "sticker" if kind == "sticker" else kind
    payload = {"chat_id": channel, field: media["file_id"]}
    if text and kind not in {"sticker", "video_note"}:
        payload["caption"] = text[:1024]
        payload["caption_entities"] = [e for e in post_entities if e["offset"] + e["length"] <= utf16_len(text[:1024])]
    result = api(method, payload)
    if text and kind in {"sticker", "video_note"}:
        send_text(channel, text, entities=post_entities)
    return result

def handle_callback(query):
    user = query.get("from", {})
    chat_id = query.get("message", {}).get("chat", {}).get("id")
    data = query.get("data", "")
    api("answerCallbackQuery", {"callback_query_id": query["id"]})
    if not is_admin(user.get("id")):
        if chat_id:
            send_text(chat_id, "⛔ فقط مدیر مجاز است.")
        return
    try:
        action, draft_id = data.split(":", 1)
    except ValueError:
        return
    draft = STATE["pending"].get(draft_id)
    if not draft:
        if chat_id:
            send_text(chat_id, "این پیش‌نویس دیگر در دسترس نیست.")
        return
    if action == "approve":
        try:
            publish(draft)
            cleanup_draft_messages(draft)
            STATE["pending"].pop(draft_id, None)
            STATE["edit_mode"].pop(str(user["id"]), None)
            save_state()
        except Exception as exc:
            log.exception("Publish failed: %s", exc)
            send_text(chat_id, f"❌ انتشار انجام نشد: {str(exc)[:700]}")
    elif action == "cancel":
        cleanup_draft_messages(draft)
        STATE["pending"].pop(draft_id, None)
        save_state()
    elif action == "edit":
        STATE["edit_mode"][str(user["id"])] = draft_id
        prompt = send_text(chat_id, "متن یا کپشن جدید را در یک پیام بفرست. برای پست متنی، این متن جایگزین کامل می‌شود.")
        draft.setdefault("cleanup_message_ids", []).append(prompt["message_id"])
        save_state()
    elif action == "channels":
        rows, row = [], []
        for target, (name, _) in CHANNELS.items():
            row.append({"text": f"{name} {target}", "callback_data": f"setchannel:{draft_id}:{target}"})
            if len(row) == 2:
                rows.append(row); row = []
        if row:
            rows.append(row)
        send_text(chat_id, "کانال مقصد جدید را انتخاب کن:", rows)
    elif action == "setchannel" and ":" in draft_id:
        # Channel usernames contain no colons; parse the final segment as destination.
        pass

def handle_update(update):
    if "callback_query" in update:
        query = update["callback_query"]
        data = query.get("data", "")
        user = query.get("from", {})
        chat_id = query.get("message", {}).get("chat", {}).get("id")
        api("answerCallbackQuery", {"callback_query_id": query["id"]})
        if not is_admin(user.get("id")):
            if chat_id:
                send_text(chat_id, "⛔ فقط مدیر مجاز است.")
            return
        parts = data.split(":")
        action, draft_id = parts[0], parts[1] if len(parts) > 1 else ""
        draft = STATE["pending"].get(draft_id)
        if not draft:
            if chat_id:
                send_text(chat_id, "این پیش‌نویس دیگر در دسترس نیست.")
            return
        if action == "setchannel" and len(parts) == 3 and parts[2] in CHANNELS:
            draft["channel"] = parts[2]
            save_state()
            preview(chat_id, draft_id)
        elif action == "channels":
            rows, row = [], []
            for target, (name, _) in CHANNELS.items():
                row.append({"text": f"{name} {target}", "callback_data": f"setchannel:{draft_id}:{target}"})
                if len(row) == 2:
                    rows.append(row); row = []
            if row: rows.append(row)
            picker = send_text(chat_id, "کانال مقصد جدید را انتخاب کن:", rows)
            draft.setdefault("cleanup_message_ids", []).append(picker["message_id"])
            save_state()
        elif action == "approve":
            try:
                publish(draft)
                cleanup_draft_messages(draft)
                STATE["pending"].pop(draft_id, None)
                STATE["edit_mode"].pop(str(user["id"]), None)
                save_state()
            except Exception as exc:
                log.exception("Publish failed")
                send_text(chat_id, f"❌ انتشار انجام نشد: {str(exc)[:700]}")
        elif action == "cancel":
            cleanup_draft_messages(draft)
            STATE["pending"].pop(draft_id, None)
            STATE["edit_mode"].pop(str(user["id"]), None)
            save_state()
        elif action == "edit":
            STATE["edit_mode"][str(user["id"])] = draft_id
            save_state()
            prompt = send_text(chat_id, "متن یا کپشن جدید را در یک پیام بفرست. برای پست متنی، متن کاملاً جایگزین می‌شود.")
            draft.setdefault("cleanup_message_ids", []).append(prompt["message_id"])
            save_state()
        return

    msg = update.get("message")
    if not msg:
        return
    user = msg.get("from", {})
    chat_id = msg.get("chat", {}).get("id")
    if not is_admin(user.get("id")):
        if chat_id:
            send_text(chat_id, "⛔ این بات خصوصی است و فقط مدیر می‌تواند از آن استفاده کند.")
        return
    user_key = str(user["id"])
    if user_key in STATE["edit_mode"]:
        draft_id = STATE["edit_mode"].pop(user_key)
        draft = STATE["pending"].get(draft_id)
        if draft:
            draft.setdefault("cleanup_message_ids", []).append(msg["message_id"])
            new_text = clean_text(msg.get("text") or msg.get("caption") or "")
            draft["text"] = new_text
            draft["entities"] = []
            draft["edited_manually"] = True
            draft.pop("source_chat_id", None)
            draft.pop("source_message_id", None)
            save_state()
            updated = send_text(chat_id, "متن پیش‌نویس به‌روزرسانی شد.")
            draft.setdefault("cleanup_message_ids", []).append(updated["message_id"])
            save_state()
            preview(chat_id, draft_id)
            return
    if msg.get("text") == "/start":
        send_text(chat_id, "سلام! متن، عکس، فیلم، موسیقی، صدا یا فایل را برای من بفرست. پیش‌نمایش و کانال مقصد را نشان می‌دهم و فقط بعد از تأیید تو منتشر می‌کنم.")
        return
    if msg.get("text") == "/cancel":
        send_text(chat_id, "برای لغو، دکمه «لغو» زیر پیش‌نویس را بزن.")
        return
    # Do not reject a useful post just because it contains an unwanted link.
    # extract_message/clean_text_and_entities remove the offending link line while
    # keeping the rest of the post for preview and approval.
    content = extract_message(msg)
    if not content["text"] and not content["media"]:
        # Diagnostic reply prevents guessing when Telegram sends an unsupported
        # message shape; include only field names, never message contents.
        keys = ", ".join(sorted(k for k in msg.keys() if k not in {"text", "caption", "entities", "caption_entities"}))
        log.warning("Unsupported/empty message payload keys=%s", keys)
        send_text(chat_id, "این نوع پیام هنوز شناسایی نشده.\nفیلدهای دریافتی تلگرام: " + (keys or "بدون فیلد قابل‌شناسایی") + "\nلطفاً همین پیام را دوباره بفرست؛ این گزارش کمک می‌کند نوع رسانه را اضافه کنم.")
        return
    draft_id = str(update["update_id"])
    channel = detect_channel(content["text"], content["media"]["type"] if content["media"] else "")
    STATE["pending"][draft_id] = {
        "chat_id": chat_id,
        "text": content["text"],
        "entities": content.get("entities", []),
        "media": content["media"],
        "channel": channel,
        "source_chat_id": chat_id,
        "source_message_id": msg["message_id"],
        "cleanup_message_ids": [msg["message_id"]],
    }
    save_state()
    preview(chat_id, draft_id)

def main():
    if not TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN secret.")
    if not ADMIN_ID.isdigit():
        raise SystemExit("Set ADMIN_USER_ID to your numeric Telegram user ID in GitHub Actions secrets or variables.")
    # Polling requires webhook mode to be disabled; preserve queued updates.
    api("deleteWebhook", {"drop_pending_updates": False})
    started = time.time()
    while time.time() - started < POLL_SECONDS:
        try:
            updates = api("getUpdates", {"offset": int(STATE.get("offset", 0)), "timeout": 20, "allowed_updates": ["message", "callback_query"]}, timeout=30)
            for update in updates:
                try:
                    message = update.get("message") or {}
                    callback = update.get("callback_query") or {}
                    sender = message.get("from") or callback.get("from") or {}
                    log.info("Received update=%s type=%s sender=%s", update.get("update_id"), "callback_query" if callback else ("message" if message else "other"), sender.get("id", "unknown"))
                    handle_update(update)
                except Exception as exc:
                    log.exception("Update %s failed", update.get("update_id"))
                    message = update.get("message") or {}
                    callback = update.get("callback_query") or {}
                    chat_id = message.get("chat", {}).get("id") or callback.get("message", {}).get("chat", {}).get("id")
                    sender = message.get("from") or callback.get("from") or {}
                    if chat_id and is_admin(sender.get("id")):
                        try:
                            send_text(chat_id, "⚠️ پیام دریافت شد اما پردازش آن خطا داد. دوباره بفرست یا نوع فایل را عوض کن.\nجزئیات: " + str(exc)[:250])
                        except Exception:
                            log.exception("Could not notify admin about update failure")
                STATE["offset"] = max(int(STATE.get("offset", 0)), int(update["update_id"]) + 1)
            save_state()
        except Exception:
            log.exception("Polling failed")
            time.sleep(5)
    save_state()

if __name__ == "__main__":
    main()
