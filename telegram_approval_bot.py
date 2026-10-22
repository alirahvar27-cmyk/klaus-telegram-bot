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
    """Add clickable Persian channel name above and clickable username below every post."""
    username = channel.lstrip("@")
    title = CHANNELS.get(channel, (username, ""))[0]
    header = f"📣 {title}"
    footer = f"📌 @{username}"
    middle = "\n\n" if text else "\n\n"
    max_text_len = limit if limit is not None else 4096
    fixed_len = utf16_len(header + middle + "\n\n" + footer)
    room = max(0, max_text_len - fixed_len)
    base = ""
    units = 0
    for char in (text or ""):
        char_units = utf16_len(char)
        if units + char_units > room:
            break
        base += char
        units += char_units
    body = header + middle + base + ("\n\n" if base else "") + footer
    header_offset = utf16_len("📣 ")
    footer_offset = utf16_len(header + middle + base + ("\n\n" if base else "") + "📌 ")
    result_entities = []
    body_start = utf16_len(header + middle)
    for entity in (entities or []):
        e = dict(entity)
        begin = int(e.get("offset", 0))
        finish = begin + int(e.get("length", 0))
        if finish <= utf16_len(base):
            e["offset"] = body_start + begin
            result_entities.append(e)
    result_entities.extend([
        {"type": "text_link", "offset": header_offset, "length": utf16_len(title), "url": f"https://t.me/{username}"},
        {"type": "text_link", "offset": footer_offset, "length": utf16_len("@" + username), "url": f"https://t.me/{username}"},
    ])
    return body, sorted(result_entities, key=lambda e: e["offset"])

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
        # Drop source-channel links even when Telegram hides the URL behind a label.
        has_source_channel_link = any(
            re.search(r"(?i)(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/", str(ent.get("url", "")))
            and not re.search(r"(?i)(?:t\.me|telegram\.me)/(?:proxy|socks)(?:[/?#]|$)", str(ent.get("url", "")))
            for _, _, ent in line_links
        )
        has_visible_url = bool(re.search(r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/)[^\s]+", stripped))
        if is_promo or is_handle_footer or has_source_channel_link or (ad_words and (line_links or has_visible_url)) or (label_only and not has_proxy_link):
            old_pos += len(raw_line)
            continue
        if re.search(r"(?i)(منبع|source|forwarded from|ارسالی از|کانال اصلی|عضویت در کانال)", stripped):
            old_pos += len(raw_line)
            continue

        cleaned_line = re.sub(
            r"(?i)\b(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?!proxy(?:[/?#]|$)|socks(?:[/?#]|$))[A-Za-z0-9_+/=?%&.-]+",
            "", line
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
                if new_ent["url"]:
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
    raw_text = msg.get("text") or msg.get("caption") or ""
    entities = msg.get("entities") or msg.get("caption_entities") or []
    text, clean_entities = clean_text_and_entities(raw_text, entities)
    media = None
    for kind in ("photo", "video", "audio", "voice", "document", "animation", "video_note", "sticker"):
        value = msg.get(kind)
        if value:
            if kind == "photo":
                value = value[-1]
            media = {"type": kind, "file_id": value.get("file_id")}
            break
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
            # A separate text preview keeps all media types and long captions manageable.
            sent_caption = send_text(chat_id, "📝 پیش‌نمایش متن:\n\n" + caption, entities=[dict(e, offset=e["offset"] + utf16_len("📝 پیش‌نمایش متن:\n\n")) for e in preview_entities])
            draft["cleanup_message_ids"].append(sent_caption["message_id"])
            draft["preview_message_ids"].append(sent_caption["message_id"])
        elif not media:
            send_text(chat_id, "پست متنی خالی است؛ متن را ویرایش کن یا لغو کن.")
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
        send_text(chat_id, "⚠️ پیش‌نمایش ارسال نشد. دوباره تلاش کن یا فایل کوچک‌تری بفرست.")

def publish(draft):
    channel = draft["channel"]
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
            send_text(chat_id, "کانال مقصد جدید را انتخاب کن:", rows)
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
    content = extract_message(msg)
    if not content["text"] and not content["media"]:
        send_text(chat_id, "لطفاً متن یا یک فایل/رسانه بفرست.")
        return
    draft_id = str(update["update_id"])
    channel = detect_channel(content["text"], content["media"]["type"] if content["media"] else "")
    STATE["pending"][draft_id] = {"chat_id": chat_id, "text": content["text"], "entities": content.get("entities", []), "media": content["media"], "channel": channel, "cleanup_message_ids": [msg["message_id"]]}
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
                    handle_update(update)
                except Exception:
                    log.exception("Update %s failed", update.get("update_id"))
                STATE["offset"] = max(int(STATE.get("offset", 0)), int(update["update_id"]) + 1)
            save_state()
        except Exception:
            log.exception("Polling failed")
            time.sleep(5)
    save_state()

if __name__ == "__main__":
    main()
