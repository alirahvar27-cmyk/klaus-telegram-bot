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

def send_text(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return api("sendMessage", payload)

def clean_text(text):
    text = text or ""
    # Remove ordinary source-channel links, but never strip proxy/SOCKS URLs.
    text = re.sub(r"(?i)\\b(?:https?://)?(?:www\\.)?(?:t\\.me|telegram\\.me)/(?!proxy(?:[/?#]|$)|socks(?:[/?#]|$))[A-Za-z0-9_+/=?%&.-]+", "", text)
    text = re.sub(r"(?i)\\b(?:خرید|فروش)\\s*(?:آی\\s*پی|ip|فیلترشکن|وی\\s*پی\\s*ان)|(?:فیلترشکن|وی\\s*پی\\s*ان)\\s*(?:اختصاصی|ارزان|اقتصادی)|آی\\s*پی\\s*(?:اختصاصی|ارزان|اقتصادی)|ip\\s*(?:اختصاصی|ارزان|اقتصادی)", "", text)
    text = re.sub(r"(?i)@[A-Za-z0-9_]{4,}", "", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if re.search(r"(?i)(منبع|source|forwarded from|ارسالی از|کانال اصلی|عضویت در کانال)", stripped):
            continue
        if re.search(r"(خرید|فروش).{0,25}(فیلترشکن|آی\\s*پی|\\bip\\b)|(?:فیلترشکن|وی\\s*پی\\s*ان).{0,20}(اختصاصی|ارزان|اقتصادی)|(?:آی\\s*پی|\\bip\\b).{0,20}(خرید|اقتصادی|اختصاصی)", stripped):
            continue
        # Strip repeated source branding/link-label-only lines; real URLs are kept.
        if re.fullmatch(r"[\\s•|·،,ـ]*(?:همراه|پروکسی)(?:[\\s•|·،,ـ]*(?:همراه|پروکسی))*[\\s•|·،,ـ]*", stripped, flags=re.IGNORECASE):
            continue
        lines.append(line.rstrip())
    return re.sub(r"\\n{3,}", "\\n\\n", "\\n".join(lines)).strip()
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

def append_proxy_entity_links(text, entities):
    """Make hidden proxy links visible as real URLs, including nonstandard proxy URL hosts."""
    if not text or not entities:
        return text

    def py_index(offset):
        units = 0
        for i, char in enumerate(text):
            if units >= offset:
                return i
            units += len(char.encode("utf-16-le")) // 2
        return len(text)

    replacements = []
    for entity in entities:
        if entity.get("type") != "text_link" or not entity.get("url"):
            continue
        url = entity["url"].strip()
        start = py_index(int(entity.get("offset", 0)))
        end = py_index(int(entity.get("offset", 0)) + int(entity.get("length", 0)))
        label = text[start:end].strip()
        # Include all links hidden behind the repeated "پروکسی" labels, as well as
        # standard Telegram proxy/SOCKS links regardless of their visible label.
        is_proxy_label = bool(re.search(r"پروکسی|proxy|socks", label, re.IGNORECASE))
        is_proxy_url = bool(re.search(r"(?i)(?:t\\.me|telegram\\.me)/(?:proxy|socks)(?:[/?#]|$)|tg://proxy(?:[/?#]|$)", url))
        if start < end and (is_proxy_label or is_proxy_url) and url not in text[start:end]:
            replacements.append((start, end, label + " — " + url))
    for start, end, replacement in sorted(replacements, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text

def extract_message(msg):
    raw_text = msg.get("text") or msg.get("caption") or ""
    entities = msg.get("entities") or msg.get("caption_entities") or []
    raw_text = append_proxy_entity_links(raw_text, entities)
    text = clean_text(raw_text)
    media = None
    for kind in ("photo", "video", "audio", "voice", "document", "animation", "video_note", "sticker"):
        value = msg.get(kind)
        if value:
            if kind == "photo":
                value = value[-1]
            media = {"type": kind, "file_id": value.get("file_id")}
            break
    return {"text": text, "media": media}

def preview(chat_id, draft_id):
    draft = STATE["pending"].get(draft_id)
    if not draft:
        return
    channel = draft["channel"]
    title, topic = CHANNELS[channel]
    media = draft.get("media")
    caption = draft.get("text", "")
    try:
        if media:
            kind = media["type"]
            method = {
                "photo": "sendPhoto", "video": "sendVideo", "audio": "sendAudio",
                "voice": "sendVoice", "document": "sendDocument",
                "animation": "sendAnimation", "video_note": "sendVideoNote",
                "sticker": "sendSticker",
            }[kind]
            field = "sticker" if kind == "sticker" else kind
            api(method, {"chat_id": chat_id, field: media["file_id"]})
        if caption:
            # A separate text preview keeps all media types and long captions manageable.
            send_text(chat_id, "📝 پیش‌نمایش متن:\n\n" + caption[:3900])
        elif not media:
            send_text(chat_id, "پست متنی خالی است؛ متن را ویرایش کن یا لغو کن.")
        controls = [
            [{"text": "✅ تأیید و انتشار", "callback_data": f"approve:{draft_id}"}],
            [{"text": "✏️ ویرایش متن", "callback_data": f"edit:{draft_id}"},
             {"text": "🔄 تغییر کانال", "callback_data": f"channels:{draft_id}"}],
            [{"text": "❌ لغو", "callback_data": f"cancel:{draft_id}"}],
        ]
        send_text(chat_id, f"📌 مقصد انتشار: {title} ({channel})\nموضوع: {topic}\n\nاگر درست است تأیید کن؛ تا پیش از تأیید منتشر نمی‌شود.", controls)
    except Exception as exc:
        log.exception("Preview failed: %s", exc)
        send_text(chat_id, "⚠️ پیش‌نمایش ارسال نشد. دوباره تلاش کن یا فایل کوچک‌تری بفرست.")

def publish(draft):
    channel = draft["channel"]
    media = draft.get("media")
    text = draft.get("text", "")
    if not media:
        if not text:
            raise ValueError("پست خالی است")
        return api("sendMessage", {"chat_id": channel, "text": text[:4096], "disable_web_page_preview": False})
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
    return api(method, payload)

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
            STATE["pending"].pop(draft_id, None)
            STATE["edit_mode"].pop(str(user["id"]), None)
            save_state()
            send_text(chat_id, f"✅ منتشر شد در {draft['channel']}")
        except Exception as exc:
            log.exception("Publish failed: %s", exc)
            send_text(chat_id, f"❌ انتشار انجام نشد: {str(exc)[:700]}")
    elif action == "cancel":
        STATE["pending"].pop(draft_id, None)
        save_state()
        send_text(chat_id, "پیش‌نویس لغو شد و چیزی منتشر نشد.")
    elif action == "edit":
        STATE["edit_mode"][str(user["id"])] = draft_id
        send_text(chat_id, "متن یا کپشن جدید را در یک پیام بفرست. برای پست متنی، این متن جایگزین کامل می‌شود.")
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
                STATE["pending"].pop(draft_id, None)
                save_state()
                send_text(chat_id, f"✅ منتشر شد در {draft['channel']}")
            except Exception as exc:
                log.exception("Publish failed")
                send_text(chat_id, f"❌ انتشار انجام نشد: {str(exc)[:700]}")
        elif action == "cancel":
            STATE["pending"].pop(draft_id, None)
            save_state()
            send_text(chat_id, "پیش‌نویس لغو شد و چیزی منتشر نشد.")
        elif action == "edit":
            STATE["edit_mode"][str(user["id"])] = draft_id
            save_state()
            send_text(chat_id, "متن یا کپشن جدید را در یک پیام بفرست. برای پست متنی، متن کاملاً جایگزین می‌شود.")
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
            new_text = clean_text(msg.get("text") or msg.get("caption") or "")
            draft["text"] = new_text
            save_state()
            send_text(chat_id, "متن پیش‌نویس به‌روزرسانی شد.")
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
    STATE["pending"][draft_id] = {"chat_id": chat_id, "text": content["text"], "media": content["media"], "channel": channel}
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
