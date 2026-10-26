import json
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
from pathlib import Path

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = os.getenv("ADMIN_USER_ID", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
STATE_PATH = Path(os.getenv("STATE_PATH", "telegram_approval_state.json"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "240"))
BLOCKED_HANDLES = {
    "@cliptanz00", "@haibekhand", "@khooroosjangi", "@CinemaBoxOrg",
    "@keyhan_n1", "@𝑮𝒉𝒐𝒔𝒕𝑪𝒆𝒎𝒆𝒕𝒆𝒓𝒚", "@ghost_cemetery", "@hipfm",
    "@HipFMAd", "@Khodesun", "@Tofan_Admin_124", "@pmscary",
    "@MobhamMovies", "@safar_dordonya", "@lmdbtv", "@JournalTourism",
    "@DiamondProxy", "@Music_Vip12", "@ITSecurityComputer", "@AmoyeTel",
    "@meme_ol_ski", "@horror_of_house", "@fxtrd_support", "@iRoProxy", "@iProxy",
    "@Diastomii", "@Hesse_Arammesh", "@Gamefa_official", "@Tweetr_khabari",
    "@ProxyMTProtoIR", "@MobhamV2ray", "@HezarGame", "@ZhneAram",
}
BLOCKED_URLS = {
    "https://youtu.be/afK1H0UtBoc",
    "http://t.me/digiunicos",
    "https://t.me/tradecity_pro",
    "https://t.me/+hA56yS7uKNRhNzQ0",
    "https://telegram.me/+JewA2B2eSAs5Njk0",
}
BLOCKED_PHRASES = ("لینک ورود به صرافی", "ورود به VVIP رایگان", "DIGIUNICOS", "𝐒𝐜𝐚𝐫𝐲 𝐖𝐨𝐫𝐥𝐝 𝐅𝐚𝐜𝐭𝐬", "★𝐒𝐜𝐚𝐫𝐲_𝐬𝐭𝐫𝐚𝐧𝐠𝐞")
BLOCKED_PROMO = re.compile(
    r"TON giveaway:\s*\$100 total,\s*10 winners\.\s*Follow @thesignal24 and like \+ comment on every X news post through Oct 30\.?",
    re.IGNORECASE,
)
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
    "@NetPlusFa": ("نت‌پلاس 🔐/پروکسی فیلتر شکن", "شبکه و امنیت سایبری"),
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
            data.setdefault("schedule_mode", {})
            data.setdefault("status_cleanup", [])
            data.setdefault("active_channel", None)
            data.setdefault("channel_schedule_next", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"offset": 0, "pending": {}, "edit_mode": {}, "schedule_mode": {}, "status_cleanup": [], "active_channel": None, "channel_schedule_next": {}}

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
    """Clear all temporary private-chat messages associated with one draft."""
    chat_id = draft.get("chat_id")
    if chat_id:
        for message_id in dict.fromkeys(draft.get("cleanup_message_ids", [])):
            delete_private_message(chat_id, message_id)
    draft["cleanup_message_ids"] = []
    draft["preview_message_ids"] = []


def send_publish_status(chat_id, text):
    """Send the final status and start its 24-hour lifetime after Telegram accepts it."""
    if not chat_id:
        return None
    message = send_text(chat_id, text)
    STATE.setdefault("status_cleanup", []).append({
        "chat_id": chat_id,
        "message_id": message["message_id"],
        "delete_at": int(time.time()) + 24 * 60 * 60,
    })
    save_state()
    return message


def cleanup_expired_status_messages():
    """Delete only expired status messages in the admin's private bot chat."""
    now = int(time.time())
    remaining = []
    changed = False
    for item in STATE.setdefault("status_cleanup", []):
        if int(item.get("delete_at", 0)) > now or int(item.get("retry_after", 0)) > now:
            remaining.append(item)
            continue
        try:
            api("deleteMessage", {
                "chat_id": item["chat_id"],
                "message_id": item["message_id"],
            })
            changed = True
            log.info("Deleted expired private status message %s", item["message_id"])
        except Exception as exc:
            item["retry_after"] = now + 300
            remaining.append(item)
            changed = True
            log.warning("Could not delete expired status message %s; retrying later: %s", item.get("message_id"), exc)
    if changed or len(remaining) != len(STATE.get("status_cleanup", [])):
        STATE["status_cleanup"] = remaining
        save_state()

def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2



# MEDIA_GROUP_FIX_V2
def _split_utf16_text(text, entities=None, limit=4096):
    text = text or ""
    entities = [dict(e) for e in (entities or [])]
    chunks = []
    pos = 0
    while pos < len(text):
        end, units = pos, 0
        while end < len(text):
            u = utf16_len(text[end])
            if units + u > limit:
                break
            units += u
            end += 1
        if end <= pos:
            end = pos + 1
        if end < len(text):
            cut = max(text.rfind("\n", pos, end), text.rfind(" ", pos, end))
            if cut > pos + 20:
                end = cut
        chunk = text[pos:end]
        base, chunk_end = utf16_len(text[:pos]), utf16_len(text[:pos]) + utf16_len(chunk)
        chunk_entities = []
        for ent in entities:
            a = int(ent.get("offset", 0))
            b = a + int(ent.get("length", 0))
            if a >= base and b <= chunk_end:
                e = dict(ent)
                e["offset"] = a - base
                chunk_entities.append(e)
        chunks.append((chunk, chunk_entities))
        pos = end
        while pos < len(text) and text[pos] == "\n":
            pos += 1
    return chunks or [("", [])]

def _split_caption(text, entities):
    return _split_utf16_text(text, entities, 1024)

def _media_items(media):
    if not isinstance(media, list):
        return [media] if isinstance(media, dict) and media.get("file_id") else []
    return [m for m in media if isinstance(m, dict) and m.get("type") and m.get("file_id")]

def _send_album(chat_id, media_items, caption_parts=None):
    caption_parts = caption_parts or []
    results = []
    for start in range(0, len(media_items), 10):
        batch = media_items[start:start + 10]
        payload_media = []
        for idx, item in enumerate(batch):
            kind = item["type"]
            if kind not in {"photo", "video", "document", "audio"}:
                raise ValueError(f"Unsupported media-group type: {kind}")
            obj = {"type": kind, "media": item["file_id"]}
            if start == 0 and idx == 0 and caption_parts and caption_parts[0][0]:
                obj["caption"], obj["caption_entities"] = caption_parts[0]
            payload_media.append(obj)
        results.extend(api("sendMediaGroup", {"chat_id": chat_id, "media": payload_media}))
    return results


def add_channel_branding(text, entities, channel, limit=None):
    """Preserve cleaned post content and append the destination channel link."""
    text = text or ""
    entities = [dict(e) for e in (entities or [])]
    username = channel.lstrip("@")
    footer = "@" + username
    # Avoid duplicate branding if the destination channel is already linked in the post.
    if not re.search(r"(?<![A-Za-z0-9_])@" + re.escape(username) + r"(?![A-Za-z0-9_])", text, re.IGNORECASE):
        separator = "\n\n" if text else ""
        offset = utf16_len(text + separator)
        text = text + separator + footer
        entities.append({"type": "text_link", "offset": offset, "length": utf16_len(footer), "url": "https://t.me/" + username})
    max_text_len = limit if limit is not None else 4096
    if utf16_len(text) > max_text_len:
        raise ValueError("متن از محدودیت تلگرام طولانی‌تر است؛ برای حفظ متن، انتشار متوقف شد.")
    return text, entities

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
        line_links = [(a, b, e) for a, b, e in spans if a < line_end and b > old_pos]
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
        def is_proxy_url(url):
            return bool(re.search(
                r"(?i)(?:t\.me|telegram\.me)/(?:proxy|socks)(?:[/?#]|$)|"
                r"tg://(?:proxy|socks)(?:[/?#]|$)",
                str(url or "")
            ))

        has_proxy_link = any(is_proxy_url(ent.get("url", "")) for _, _, ent in line_links)
        label_only = bool(re.fullmatch(
            r"[\s✅✔️☑️〰️~—–-•|·،,ـ]*(?:همراه|پروکسی)(?:[\s✅✔️☑️〰️~—–-•|·،,ـ]*(?:همراه|پروکسی))*[\s✅✔️☑️〰️~—–-•|·،,ـ]*",
            stripped, re.IGNORECASE
        ))
        def is_proxy_url(url):
            return bool(re.search(
                r"(?i)(?:t\.me|telegram\.me)/(?:proxy|socks)(?:[/?#]|$)|"
                r"(?:https?://)?(?:www\.)?[^\s]*\b(?:proxy|socks)\b[^\s]*",
                str(url or "")
            ))

        has_nonproxy_hidden_link = any(not is_proxy_url(ent.get("url", "")) for _, _, ent in line_links)
        visible_urls = re.findall(r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/)[^\s<>]+", stripped)
        has_nonproxy_visible_link = any(not is_proxy_url(url) for url in visible_urls)
        has_blocked_slogan = bool(re.search("اینترنت\s*آزاد\s*برای\s*همه\s*یا\s*هیچکس", stripped, re.IGNORECASE))
        if has_blocked_slogan or is_promo or is_handle_footer:
            old_pos += len(raw_line)
            continue
        if re.search(r"(?i)(منبع|source|forwarded from|ارسالی از|کانال اصلی|عضویت در کانال)", stripped):
            old_pos += len(raw_line)
            continue

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
            seg_start = max(a, old_pos)
            seg_end = min(b, old_pos + len(line))
            if seg_start >= seg_end:
                continue
            entity_type = ent.get("type", "")
            if entity_type == "text_link" and not is_allowed_link(ent.get("url", "")):
                continue
            if cleaned_line != raw_line.rstrip("\r\n"):
                continue
            new_ent = dict(ent)
            new_ent["offset"] = line_start_new_units + utf16_len(text[old_pos:seg_start])
            new_ent["length"] = utf16_len(text[seg_start:seg_end])
            if entity_type == "text_link" and not new_ent.get("url"):
                continue
            kept_entities.append(new_ent)
        new_units += utf16_len(line)
        old_pos += len(raw_line)

    cleaned = "".join(kept_parts).strip()
    if not cleaned:
        return "", []
    leading = len("".join(kept_parts)) - len("".join(kept_parts).lstrip())
    if leading:
        shift = utf16_len("".join(kept_parts)[:leading])
        kept_entities = [dict(e, offset=max(0, e["offset"] - shift)) for e in kept_entities]
    return cleaned, sorted(kept_entities, key=lambda e: e["offset"])

def clean_text(text):
    return clean_text_and_entities(text, [])[0]

def sanitize_draft_text(text):
    """Remove only the user's explicit blocklist and tidy resulting whitespace."""
    value = text or ""
    for url in sorted(BLOCKED_URLS, key=len, reverse=True):
        value = re.sub(re.escape(url), "", value, flags=re.IGNORECASE)
    for handle in sorted(BLOCKED_HANDLES, key=len, reverse=True):
        value = re.sub(re.escape(handle), "", value, flags=re.IGNORECASE)
    for phrase in BLOCKED_PHRASES:
        value = re.sub(re.escape(phrase), "", value, flags=re.IGNORECASE)
    lines = []
    for line in value.splitlines():
        if BLOCKED_PROMO.search(line.strip()):
            continue
        line = re.sub(r"[ \t]{2,}", " ", line).strip()
        line = re.sub(r"^[|•·,،;؛:—–-]+\s*|\s*[|•·,،;؛:—–-]+$", "", line).strip()
        if line:
            lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

def sanitize_text_and_entities(text, entities):
    original = text or ""
    entities = entities or []
    cleaned = sanitize_draft_text(original)
    if cleaned == original:
        return cleaned, entities

    def is_real_proxy_link(url):
        return bool(re.match(
            r"(?i)^(?:(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:proxy|socks)(?:[/?#].*)?|tg://(?:proxy|socks)(?:[/?#].*)?)$",
            str(url or "").strip()
        ))

    def char_index(value, offset):
        units = 0
        for i, char in enumerate(value):
            if units >= offset:
                return i
            units += utf16_len(char)
        return len(value)

    kept = []
    search_from = 0
    for entity in entities:
        if entity.get("type") != "text_link" or not is_real_proxy_link(entity.get("url")):
            continue
        start = char_index(original, int(entity.get("offset", 0)))
        end = char_index(original, int(entity.get("offset", 0)) + int(entity.get("length", 0)))
        label = original[start:end]
        if not label:
            continue
        new_start = cleaned.find(label, search_from)
        if new_start < 0:
            new_start = cleaned.find(label)
        if new_start < 0:
            continue
        new_entity = dict(entity)
        new_entity["offset"] = utf16_len(cleaned[:new_start])
        new_entity["length"] = utf16_len(label)
        kept.append(new_entity)
        search_from = new_start + len(label)
    return cleaned, sorted(kept, key=lambda e: e["offset"])

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

def normalize_channel_command(value):
    """Normalize a channel link/name so admin can select a channel in plain chat."""
    value = (value or "").strip().casefold().replace("ك", "ک").replace("ي", "ی").replace("ى", "ی")
    value = re.sub(r"[\u200c\u200d\ufeff]", "", value)
    value = re.sub(r"^https?://(?:www\.)?(?:t\.me|telegram\.me)/", "@", value, flags=re.IGNORECASE)
    value = re.sub(r"^@", "", value)
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def resolve_channel_command(text):
    """Return ('end', None), ('channel', username), or (None, None)."""
    normalized = normalize_channel_command(text)
    if normalized == normalize_channel_command("پایان"):
        return "end", None
    aliases = {
        "@LevelUpFa": {"لول آپ", "لول اپ", "لولوپ", "level up"},
        "@NetPlusFa": {"نت پلاس", "نت‌پلاس", "net plus"},
    }
    for channel, (name, _) in CHANNELS.items():
        candidates = {
            normalize_channel_command(channel),
            normalize_channel_command(name),
            normalize_channel_command("https://t.me/" + channel.lstrip("@")),
        }
        candidates.update(normalize_channel_command(alias) for alias in aliases.get(channel, set()))
        if normalized and normalized in candidates:
            return "channel", channel
    return None, None


def _single_extract_message(msg):
    """Extract ordinary Bot API messages and Telegram's rich_message forward payload."""
    media_kinds = ("photo", "video", "audio", "voice", "document", "animation", "video_note", "sticker")
    raw_text = msg.get("text") or msg.get("caption") or ""
    entities = msg.get("entities") or msg.get("caption_entities") or []
    media = None
    def walk_rich(value, parent_key=""):
        nonlocal raw_text, entities, media
        if isinstance(value, list):
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
        if media is None and value.get("file_id"):
            inferred = parent_key if parent_key in media_kinds else value.get("type")
            if inferred in media_kinds:
                media = {"type": inferred, "file_id": value["file_id"]}
        for key, child in value.items():
            if key in {"text", "caption", "entities", "caption_entities", "file_id"}:
                continue
            if isinstance(child, (dict, list)):
                walk_rich(child, key)
    for kind in media_kinds:
        value = msg.get(kind)
        if not value:
            continue
        if kind == "photo":
            value = value[-1] if isinstance(value, list) else value
        if isinstance(value, dict) and value.get("file_id"):
            media = {"type": kind, "file_id": value["file_id"]}
            break
    rich = msg.get("rich_message")
    def collect_rich_content(value):
        parts = []
        rich_entities = []
        total_units = 0
        entity_types = {"bold", "italic", "underline", "strikethrough", "spoiler", "code", "pre", "blockquote", "expandable_blockquote", "text_link", "text_mention", "custom_emoji"}
        style_keys = {"bold":"bold", "italic":"italic", "underline":"underline", "strikethrough":"strikethrough", "spoiler":"spoiler", "code":"code", "mono":"code", "monospace":"code", "pre":"pre", "quote":"blockquote", "blockquote":"blockquote", "expandable_blockquote":"expandable_blockquote"}
        ignored_keys = {"entities", "caption_entities", "file_id", "reply_markup", "inline_keyboard", "keyboard", "buttons", "button", "url", "link", "links", "button_url", "web_app", "login_url", "switch_inline_query", "callback_data", "reply_to_markup"}
        def add_entity(entity, base, run_text):
            try:
                local_offset = int(entity.get("offset", 0)); length = int(entity.get("length", utf16_len(run_text) - local_offset))
            except (TypeError, ValueError): return
            if length <= 0 or local_offset < 0 or local_offset + length > utf16_len(run_text): return
            item = dict(entity); item["offset"] = base + local_offset; item["length"] = length; rich_entities.append(item)
        def walk(node, inherited=(), parent_key=""):
            nonlocal total_units
            if isinstance(node, list):
                for child in node: walk(child, inherited, parent_key)
                return
            if not isinstance(node, dict): return
            run_text = node.get("text")
            if not isinstance(run_text, str): run_text = node.get("caption")
            if isinstance(run_text, str) and run_text:
                base = total_units; parts.append(run_text); total_units += utf16_len(run_text)
                local_entities = node.get("entities") or node.get("caption_entities") or []
                for entity in local_entities:
                    if isinstance(entity, dict): add_entity(entity, base, run_text)
                run_styles = list(inherited); node_type = str(node.get("type", node.get("format", ""))).casefold()
                if node_type in entity_types: run_styles.append(node_type)
                for key, entity_type in style_keys.items():
                    if node.get(key) is True and entity_type not in run_styles: run_styles.append(entity_type)
                for entity_type in dict.fromkeys(run_styles):
                    entity = {"type": entity_type, "offset": 0, "length": utf16_len(run_text)}
                    if entity_type == "text_link":
                        url = node.get("url") or node.get("href")
                        if url: entity["url"] = url
                        else: continue
                    if entity_type == "pre" and node.get("language"): entity["language"] = node["language"]
                    rich_entities.append(dict(entity, offset=base))
                for key, child in node.items():
                    normalized = str(key).casefold()
                    if normalized in {"text", "caption", "entities", "caption_entities", "file_id"}: continue
                    if normalized in ignored_keys or any(token in normalized for token in ("button", "keyboard", "markup", "menu", "website", "social", "web_app", "login_url", "callback", "action", "cta")): continue
                    if isinstance(child, (dict, list)):
                        mapped = style_keys.get(normalized); walk(child, tuple(run_styles + ([mapped] if mapped else [])), key)
                return
            for key, child in node.items():
                normalized = str(key).casefold()
                if normalized in ignored_keys or any(token in normalized for token in ("button", "keyboard", "markup", "menu", "website", "social", "web_app", "login_url", "callback", "action", "cta")): continue
                if isinstance(child, (dict, list)):
                    mapped = style_keys.get(normalized); walk(child, tuple(inherited + ((mapped,) if mapped else ())), key)
        walk(value); return "".join(parts), sorted(rich_entities, key=lambda e: (e["offset"], e["length"]))
    if rich:
        walk_rich(rich); rich_text, rich_entities = collect_rich_content(rich)
        if rich_text: raw_text = rich_text; entities = rich_entities
    raw_text, entities = clean_text_and_entities(raw_text, entities)
    return {"text": raw_text, "entities": entities, "media": media}

def extract_message(msg):
    album = msg.get("album_items") if isinstance(msg, dict) else None
    if not album: return _single_extract_message(msg)
    parsed = [_single_extract_message(item) for item in album]
    media, text, entities = [], "", []
    for item in parsed:
        one = item.get("media")
        if one: media.extend(one if isinstance(one, list) else [one])
        if not text and item.get("text"): text = item.get("text") or ""; entities = item.get("entities") or []
    return {"text": text, "entities": entities, "media": media}


def preview(chat_id, draft_id):
    draft = STATE["pending"].get(draft_id)
    if not draft: return
    draft["text"], draft["entities"] = sanitize_text_and_entities(draft.get("text", ""), draft.get("entities", []))
    if not draft: return
    cleanup_draft_messages(draft)
    draft.setdefault("preview_message_ids", []); draft.setdefault("cleanup_message_ids", [])
    channel = draft["channel"]; title, topic = CHANNELS[channel]
    text, entities = add_channel_branding(draft.get("text", ""), draft.get("entities", []), channel, limit=4096)
    media = draft.get("media"); items = _media_items(media); sent = []
    if len(items) > 1:
        parts = _split_caption(text, entities) if text else []; sent = _send_album(chat_id, items, parts)
        for extra_text, extra_entities in parts[1:]:
            prefix = "📝 ادامه متن پیش‌نمایش:" + chr(10) * 2; sent.append(send_text(chat_id, prefix + extra_text, entities=[dict(e, offset=e["offset"] + utf16_len(prefix)) for e in extra_entities]))
    elif items:
        item = items[0]; kind = item["type"]; methods = {"photo":"sendPhoto", "video":"sendVideo", "audio":"sendAudio", "voice":"sendVoice", "document":"sendDocument", "animation":"sendAnimation", "video_note":"sendVideoNote", "sticker":"sendSticker"}; payload = {"chat_id": chat_id, ("sticker" if kind == "sticker" else kind): item["file_id"]}
        parts = _split_caption(text, entities) if text and kind not in {"sticker", "video_note"} else [("", [])]
        if parts[0][0]: payload["caption"], payload["caption_entities"] = parts[0]
        sent.append(api(methods[kind], payload))
        for extra_text, extra_entities in parts[1:]:
            prefix = "📝 ادامه متن پیش‌نمایش:" + chr(10) * 2; sent.append(send_text(chat_id, prefix + extra_text, entities=[dict(e, offset=e["offset"] + utf16_len(prefix)) for e in extra_entities]))
    elif text: sent.append(send_text(chat_id, "📝 پیش‌نمایش متن:" + chr(10) * 2 + text, entities=[dict(e, offset=e["offset"] + utf16_len("📝 پیش‌نمایش متن:" + chr(10) * 2)) for e in entities]))
    else: sent.append(send_text(chat_id, "پست خالی است؛ متن را ویرایش کن یا لغو کن."))
    for item in sent:
        mid = item.get("message_id")
        if mid: draft["cleanup_message_ids"].append(mid); draft["preview_message_ids"].append(mid)
    scheduled_ready = bool(draft.get("scheduled_at") and draft.get("scheduled_approved"))
    controls = []
    if not scheduled_ready: controls.append([{"text": ("✅ تأیید و زمان‌بندی" if draft.get("scheduled_at") else "✅ تأیید و انتشار"), "callback_data": f"approve:{draft_id}"}])
    controls.extend([[{"text": "✏️ ویرایش متن", "callback_data": f"edit:{draft_id}"}, {"text": "🔄 تغییر کانال", "callback_data": f"channels:{draft_id}"}], [{"text": "⏰ تعیین زمان انتشار", "callback_data": f"schedule:{draft_id}"}], [{"text": "❌ لغو", "callback_data": f"cancel:{draft_id}"}]])
    status_text = ("زمان‌بندی ثبت شد؛ پست در زمان تعیین‌شده خودکار منتشر می‌شود." if scheduled_ready else ("زمان پیشنهادی خودکار است؛ با تأیید، زمان‌بندی ثبت می‌شود." if draft.get("scheduled_at") else "اگر درست است تأیید کن؛ تا پیش از تأیید منتشر نمی‌شود."))
    if draft.get("scheduled_at"):
        scheduled_dt = datetime.fromtimestamp(int(draft["scheduled_at"]), ZoneInfo("Asia/Tehran")); status_text += chr(10) + "زمان: " + scheduled_dt.strftime("%Y-%m-%d %H:%M") + " (تهران)"
    controls_msg = send_text(chat_id, f"📌 مقصد انتشار: {title} ({channel})" + chr(10) + f"موضوع: {topic}" + chr(10) * 2 + status_text, controls)
    draft["cleanup_message_ids"].append(controls_msg["message_id"]); draft["preview_message_ids"].append(controls_msg["message_id"]); save_state()


def publish(draft):
    channel = draft["channel"]; media = draft.get("media"); text, post_entities = add_channel_branding(draft.get("text", ""), draft.get("entities", []), channel, limit=4096); items = _media_items(media)
    if not items:
        if not text: raise ValueError("پست خالی است")
        return api("sendMessage", {"chat_id": channel, "text": text, "entities": post_entities, "disable_web_page_preview": False})
    if len(items) > 1:
        parts = _split_caption(text, post_entities) if text else []; sent = _send_album(channel, items, parts)
        for extra_text, extra_entities in parts[1:]: send_text(channel, extra_text, entities=extra_entities)
        return sent
    item = items[0]; kind = item["type"]; methods = {"photo":"sendPhoto", "video":"sendVideo", "audio":"sendAudio", "voice":"sendVoice", "document":"sendDocument", "animation":"sendAnimation", "video_note":"sendVideoNote", "sticker":"sendSticker"}; payload = {"chat_id": channel, ("sticker" if kind == "sticker" else kind): item["file_id"]}; parts = _split_caption(text, post_entities) if text and kind not in {"sticker", "video_note"} else [("", [])]
    if parts[0][0]: payload["caption"], payload["caption_entities"] = parts[0]
    result = api(methods[kind], payload)
    for extra_text, extra_entities in parts[1:]: send_text(channel, extra_text, entities=extra_entities)
    return result


def handle_callback(query):
    user = query.get("from", {}); chat_id = query.get("message", {}).get("chat", {}).get("id"); data = query.get("data", ""); api("answerCallbackQuery", {"callback_query_id": query["id"]})
    if not is_admin(user.get("id")):
        if chat_id: send_text(chat_id, "⛔ فقط مدیر مجاز است.")
        return
    try: action, draft_id = data.split(":", 1)
    except ValueError: return
    draft = STATE["pending"].get(draft_id)
    if not draft:
        if chat_id: send_text(chat_id, "این پیش‌نویس دیگر در دسترس نیست.")
        return
    if action == "approve":
        try:
            publish(draft)
            channel = draft["channel"]
            cleanup_draft_messages(draft)
            STATE["pending"].pop(draft_id, None)
            STATE["edit_mode"].pop(str(user["id"]), None)
            save_state()
            send_publish_status(chat_id, f"✅ پست با موفقیت در {channel} منتشر شد.")
        except Exception as exc:
            log.exception("Publish failed: %s", exc)
            send_text(chat_id, f"❌ انتشار انجام نشد: {str(exc)[:700]}")
    elif action == "cancel": cleanup_draft_messages(draft); STATE["pending"].pop(draft_id, None); save_state()
    elif action == "edit":
        STATE["edit_mode"][str(user["id"])] = draft_id; prompt = send_text(chat_id, "متن یا کپشن جدید را در یک پیام بفرست. برای پست متنی، این متن جایگزین کامل می‌شود."); draft.setdefault("cleanup_message_ids", []).append(prompt["message_id"]); save_state()
    elif action == "channels":
        rows, row = [], []
        for target, (name, _) in CHANNELS.items():
            row.append({"text": f"{name} {target}", "callback_data": f"setchannel:{draft_id}:{target}"})
            if len(row) == 2: rows.append(row); row = []
        if row: rows.append(row)
        send_text(chat_id, "کانال مقصد جدید را انتخاب کن:", rows)
    elif action == "setchannel" and ":" in draft_id: pass

def handle_update(update):
    if "callback_query" in update:
        query = update["callback_query"]; data = query.get("data", ""); user = query.get("from", {}); chat_id = query.get("message", {}).get("chat", {}).get("id"); api("answerCallbackQuery", {"callback_query_id": query["id"]})
        if not is_admin(user.get("id")):
            if chat_id: send_text(chat_id, "⛔ فقط مدیر مجاز است.")
            return
        parts = data.split(":"); action, draft_id = parts[0], parts[1] if len(parts) > 1 else ""; draft = STATE["pending"].get(draft_id)
        if not draft:
            if chat_id: send_text(chat_id, "این پیش‌نویس دیگر در دسترس نیست.")
            return
        if action == "setchannel" and len(parts) == 3 and parts[2] in CHANNELS:
            draft["channel"] = parts[2]
            if draft.get("auto_scheduled") and draft.get("scheduled_at"):
                queue = STATE.setdefault("channel_schedule_next", {})
                queue[parts[2]] = max(int(queue.get(parts[2], 0) or 0), int(draft["scheduled_at"]))
            save_state()
            preview(chat_id, draft_id)
        elif action == "channels":
            rows, row = [], []
            for target, (name, _) in CHANNELS.items():
                row.append({"text": f"{name} {target}", "callback_data": f"setchannel:{draft_id}:{target}"})
                if len(row) == 2: rows.append(row); row = []
            if row: rows.append(row)
            picker = send_text(chat_id, "کانال مقصد جدید را انتخاب کن:", rows); draft.setdefault("cleanup_message_ids", []).append(picker["message_id"]); save_state()
        elif action == "approve":
            if draft.get("scheduled_at") and int(draft.get("scheduled_at", 0)) > time.time():
                draft["scheduled_approved"] = True
                save_state()
                cleanup_draft_messages(draft)
                preview(chat_id, draft_id)
                return
            try:
                publish(draft)
            except Exception as exc:
                log.exception("Publish failed")
                send_text(chat_id, f"❌ انتشار انجام نشد: {str(exc)[:700]}")
                return
            channel = draft["channel"]
            cleanup_draft_messages(draft)
            STATE["pending"].pop(draft_id, None)
            STATE["edit_mode"].pop(str(user["id"]), None)
            save_state()
            try:
                send_publish_status(chat_id, f"✅ پست با موفقیت در {channel} منتشر شد.")
            except Exception:
                log.exception("Post was published, but success confirmation could not be sent")
        elif action == "cancel": cleanup_draft_messages(draft); STATE["pending"].pop(draft_id, None); STATE["edit_mode"].pop(str(user["id"]), None); save_state()
        elif action == "schedule":
            cleanup_draft_messages(draft)
            user_key = str(user["id"]); today = datetime.now(ZoneInfo("Asia/Tehran")).date(); rows=[]; row=[]
            for day_offset in range(8):
                chosen_date = today + timedelta(days=day_offset); label=("امروز" if day_offset == 0 else "فردا" if day_offset == 1 else chosen_date.strftime("%m-%d")) + " · " + chosen_date.isoformat(); row.append({"text": label, "callback_data": f"scheduledate:{draft_id}:{chosen_date.isoformat()}"})
                if len(row)==2: rows.append(row); row=[]
            if row: rows.append(row)
            STATE["schedule_mode"][user_key]={"draft_id":draft_id,"step":"date"}; save_state(); prompt=send_text(chat_id,"📅 تاریخ انتشار را از گزینه‌ها انتخاب کن. بعد ساعت و دقیقه را خودت وارد می‌کنی. برای لغو /cancel بفرست.",rows); draft.setdefault("cleanup_message_ids",[]).append(prompt["message_id"]); save_state()
        elif action == "scheduledate" and len(parts) == 3:
            try:
                chosen_date=datetime.strptime(parts[2],"%Y-%m-%d").date(); today=datetime.now(ZoneInfo("Asia/Tehran")).date()
                if chosen_date<today or chosen_date>today+timedelta(days=7): raise ValueError("تاریخ خارج از بازه است.")
            except ValueError:
                error_message = send_text(chat_id,"این تاریخ معتبر نیست؛ دوباره از گزینه‌های تاریخ انتخاب کن.")
                draft.setdefault("cleanup_message_ids", []).append(error_message["message_id"])
                save_state()
                return
            cleanup_draft_messages(draft)
            STATE["schedule_mode"][str(user["id"])]={"draft_id":draft_id,"step":"hour","date":chosen_date.isoformat()}; save_state(); prompt=send_text(chat_id,"🕒 ساعت انتشار را به‌صورت عدد ۰ تا ۲۳ بفرست؛ مثلاً 18."); draft.setdefault("cleanup_message_ids",[]).append(prompt["message_id"]); save_state()
        elif action == "edit":
            STATE["edit_mode"][str(user["id"])] = draft_id; save_state(); prompt=send_text(chat_id,"متن یا کپشن جدید را در یک پیام بفرست. برای پست متنی، متن کاملاً جایگزین می‌شود."); draft.setdefault("cleanup_message_ids",[]).append(prompt["message_id"]); save_state()
        return
    msg=update.get("message")
    if not msg: return
    user=msg.get("from",{}); chat_id=msg.get("chat",{}).get("id")
    if not is_admin(user.get("id")):
        if chat_id: send_text(chat_id,"⛔ این بات خصوصی است و فقط مدیر می‌تواند از آن استفاده کند.")
        return
    user_key=str(user["id"])
    if msg.get("text")=="/cancel" and user_key in STATE.get("schedule_mode",{}):
        mode = STATE["schedule_mode"].pop(user_key, {})
        draft_id = mode.get("draft_id", "") if isinstance(mode, dict) else mode
        draft = STATE.get("pending", {}).get(draft_id)
        if draft:
            draft.setdefault("cleanup_message_ids", []).append(msg["message_id"])
            cleanup_draft_messages(draft)
        save_state()
        cancel_message = send_text(chat_id,"تعیین زمان لغو شد؛ پیش‌نویس قبلی دست‌نخورده است.")
        if draft:
            draft.setdefault("cleanup_message_ids", []).append(cancel_message["message_id"])
            preview(chat_id, draft_id)
        return
    if user_key in STATE.get("schedule_mode",{}):
        mode=STATE["schedule_mode"][user_key]
        if isinstance(mode,str): mode={"draft_id":mode,"step":"date"}; STATE["schedule_mode"][user_key]=mode
        draft_id=mode.get("draft_id",""); draft=STATE["pending"].get(draft_id); value=(msg.get("text") or "").strip(); step=mode.get("step","date")
        if draft:
            draft.setdefault("cleanup_message_ids", []).append(msg["message_id"])
        try:
            tehran_now=datetime.now(ZoneInfo("Asia/Tehran"))
            if not draft: STATE["schedule_mode"].pop(user_key,None); save_state(); send_text(chat_id,"این پیش‌نویس دیگر در دسترس نیست."); return
            if step=="date":
                scheduled_date=datetime.strptime(value,"%Y-%m-%d").date(); today=tehran_now.date()
                if scheduled_date<today or scheduled_date>today+timedelta(days=7): raise ValueError("تاریخ باید از امروز تا حداکثر ۷ روز آینده باشد.")
                mode["date"]=scheduled_date.isoformat(); mode["step"]="hour"; STATE["schedule_mode"][user_key]=mode; save_state(); cleanup_draft_messages(draft); prompt=send_text(chat_id,"🕒 ساعت انتشار را به‌صورت عدد ۰ تا ۲۳ بفرست؛ مثلاً 18."); draft.setdefault("cleanup_message_ids",[]).append(prompt["message_id"]); save_state()
            elif step=="hour":
                if not re.fullmatch(r"\d{1,2}",value) or not 0<=int(value)<=23: raise ValueError("ساعت باید عددی بین ۰ تا ۲۳ باشد.")
                mode["hour"]=int(value); mode["step"]="minute"; STATE["schedule_mode"][user_key]=mode; save_state(); cleanup_draft_messages(draft); prompt=send_text(chat_id,"⏱ دقیقهٔ انتشار را به‌صورت عدد ۰ تا ۵۹ بفرست؛ مثلاً 05 یا 30."); draft.setdefault("cleanup_message_ids",[]).append(prompt["message_id"]); save_state()
            elif step=="minute":
                if not re.fullmatch(r"\d{1,2}",value) or not 0<=int(value)<=59: raise ValueError("دقیقه باید عددی بین ۰ تا ۵۹ باشد.")
                scheduled_dt=datetime.strptime(f"{mode['date']} {mode['hour']:02d}:{int(value):02d}","%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Tehran")); scheduled_epoch=scheduled_dt.timestamp()
                if scheduled_epoch<=time.time()+30:
                    mode["step"]="hour"; STATE["schedule_mode"][user_key]=mode; save_state(); cleanup_draft_messages(draft)
                    retry_message=send_text(chat_id,"این ساعت گذشته یا خیلی نزدیک است. ساعت دیگری بین ۰ تا ۲۳ بفرست؛ بعد دوباره دقیقه را می‌پرسم.")
                    draft.setdefault("cleanup_message_ids", []).append(retry_message["message_id"]); save_state(); return
                draft["scheduled_at"]=int(scheduled_epoch)
                if draft.get("auto_scheduled"):
                    queue = STATE.setdefault("channel_schedule_next", {})
                    queue[draft["channel"]] = max(int(queue.get(draft["channel"], 0) or 0), int(scheduled_epoch))
                draft["scheduled_approved"]=True; STATE["schedule_mode"].pop(user_key,None); save_state(); cleanup_draft_messages(draft); preview(chat_id,draft_id)
            else: raise ValueError("مرحلهٔ زمان‌بندی نامعتبر است.")
        except ValueError as exc:
            STATE["schedule_mode"][user_key]=mode; save_state(); prompt_text=(f"❌ {exc}\nتاریخ را با قالب YYYY-MM-DD بفرست؛ فقط امروز تا ۷ روز آینده. برای لغو /cancel." if step=="date" else f"❌ {exc}\nساعت را به‌صورت عدد ۰ تا ۲۳ بفرست." if step=="hour" else f"❌ {exc}\nدقیقه را به‌صورت عدد ۰ تا ۵۹ بفرست."); error_message=send_text(chat_id,prompt_text)
            if draft:
                draft.setdefault("cleanup_message_ids", []).append(error_message["message_id"])
                save_state()
        return
    if msg.get("text")=="/cancel": send_text(chat_id,"برای لغو، دکمه «لغو» زیر پیش‌نویس را بزن."); return
    if user_key in STATE["edit_mode"]:
        draft_id=STATE["edit_mode"].pop(user_key); draft=STATE["pending"].get(draft_id)
        if draft:
            draft.setdefault("cleanup_message_ids",[]).append(msg["message_id"]); draft["text"]=msg.get("text") or msg.get("caption") or ""; draft["entities"]=msg.get("entities") or msg.get("caption_entities") or []; draft["text"],draft["entities"]=sanitize_text_and_entities(draft["text"],draft["entities"]); draft["edited_manually"]=True; draft.pop("source_chat_id",None); draft.pop("source_message_id",None); save_state(); updated=send_text(chat_id,"متن پیش‌نویس به‌روزرسانی شد."); draft.setdefault("cleanup_message_ids",[]).append(updated["message_id"]); save_state(); preview(chat_id,draft_id); return
    command, target_channel = resolve_channel_command(msg.get("text") or "")
    if command == "end":
        previous_channel = STATE.get("active_channel")
        STATE["active_channel"] = None
        save_state()
        ended_name = CHANNELS.get(previous_channel, (previous_channel or "کانال فعلی", ""))[0]
        send_text(chat_id, f"✅ صف {ended_name} پایان یافت. برای شروع کانال بعدی، اسم یا لینک آن را بفرست.")
        return
    if command == "channel":
        STATE["active_channel"] = target_channel
        save_state()
        channel_name = CHANNELS[target_channel][0]
        next_time = int(STATE.setdefault("channel_schedule_next", {}).get(target_channel, 0) or 0)
        note = ""
        if next_time > time.time():
            next_dt = datetime.fromtimestamp(next_time, ZoneInfo("Asia/Tehran"))
            note = chr(10) + "زمان‌بندی مستقل این کانال از قبل وجود دارد؛ صف بعدی از " + next_dt.strftime("%Y-%m-%d %H:%M") + " ادامه پیدا می‌کند."
        send_text(chat_id, f"📌 کانال فعال شد: {channel_name} ({target_channel})" + chr(10) + "پست‌های جدید این کانال زمان پیشنهادی با فاصلهٔ ۲۰ دقیقه می‌گیرند. برای پایان کار این کانال بنویس «پایان»." + note)
        return
    if msg.get("text")=="/start": send_text(chat_id,"سلام! متن، عکس، فیلم، موسیقی، صدا یا فایل را برای من بفرست. پیش‌نمایش و کانال مقصد را نشان می‌دهم و فقط بعد از تأیید تو منتشر می‌کنم."); return
    content=extract_message(msg)
    if not content["text"] and not content["media"]:
        keys=", ".join(sorted(k for k in msg.keys() if k not in {"text","caption","entities","caption_entities"})); log.warning("Unsupported/empty message payload keys=%s",keys); send_text(chat_id,"این نوع پیام هنوز شناسایی نشده.\nفیلدهای دریافتی تلگرام: "+(keys or "بدون فیلد قابل‌شناسایی")+"\nلطفاً همین پیام را دوباره بفرست؛ این گزارش کمک می‌کند نوع رسانه را اضافه کنم."); return
    draft_id=str(update["update_id"]); media_value=content.get("media")
    if isinstance(media_value,list): media_type=next((item.get("type","") for item in media_value if isinstance(item,dict) and item.get("type")),"")
    elif isinstance(media_value,dict): media_type=media_value.get("type","")
    else: media_type=""
    active_channel = STATE.get("active_channel")
    channel = active_channel if active_channel in CHANNELS else detect_channel(content["text"], media_type)
    draft = {"chat_id": chat_id, "text": content["text"], "entities": content.get("entities", []), "media": content["media"], "channel": channel, "source_chat_id": chat_id, "source_message_id": msg["message_id"], "cleanup_message_ids": [msg["message_id"]]}
    if active_channel in CHANNELS:
        now = int(time.time())
        channel_schedule_next = STATE.setdefault("channel_schedule_next", {})
        previous_slot = int(channel_schedule_next.get(channel, 0) or 0)
        scheduled_at = max(now + 20 * 60, previous_slot + 20 * 60) if previous_slot else now + 20 * 60
        draft["scheduled_at"] = scheduled_at
        draft["auto_scheduled"] = True
        channel_schedule_next[channel] = scheduled_at
    STATE["pending"][draft_id] = draft
    save_state()
    preview(chat_id, draft_id)

def publish_due_drafts():
    now=int(time.time())
    for draft_id,draft in list(STATE.get("pending",{}).items()):
        due=int(draft.get("scheduled_at",0) or 0)
        if not draft.get("scheduled_approved") or not due or due>now: continue
        try:
            publish(draft); chat_id=draft.get("chat_id"); channel=draft.get("channel"); cleanup_draft_messages(draft); STATE["pending"].pop(draft_id,None); save_state()
            if chat_id: send_publish_status(chat_id,f"✅ پست زمان‌بندی‌شده در {channel} منتشر شد.")
        except Exception as exc:
            log.exception("Scheduled publish failed for draft %s",draft_id); chat_id=draft.get("chat_id")
            if chat_id:
                try: send_text(chat_id,f"❌ انتشار زمان‌بندی‌شده انجام نشد: {str(exc)[:500]}")
                except Exception: log.exception("Could not report scheduled publish failure")
            draft["scheduled_approved"]=False; save_state()

def main():
    if not TOKEN: raise SystemExit("Missing TELEGRAM_BOT_TOKEN secret.")
    if not ADMIN_ID.isdigit(): raise SystemExit("Set ADMIN_USER_ID to your numeric Telegram user ID in GitHub Actions secrets or variables.")
    api("deleteWebhook", {"drop_pending_updates": False}); started=time.time()
    while time.time()-started<POLL_SECONDS:
        try:
            cleanup_expired_status_messages(); publish_due_drafts(); updates=api("getUpdates", {"offset":int(STATE.get("offset",0)),"timeout":20,"allowed_updates":["message","callback_query"]}, timeout=30); grouped_updates=[]; album_buckets={}
            for incoming in updates:
                imsg=incoming.get("message") or {}; gid=imsg.get("media_group_id")
                if gid:
                    bucket=album_buckets.setdefault(str(gid),{"first":incoming,"items":[]}); bucket["items"].append(imsg)
                else: grouped_updates.append(incoming)
            for bucket in album_buckets.values():
                first=dict(bucket["first"]); first_msg=dict(first.get("message") or {}); first_msg["album_items"]=bucket["items"]; first["message"]=first_msg; grouped_updates.append(first)
            grouped_updates.sort(key=lambda u:int(u.get("update_id",0)))
            for update in grouped_updates:
                try:
                    message=update.get("message") or {}; callback=update.get("callback_query") or {}; sender=message.get("from") or callback.get("from") or {}; log.info("Received update=%s type=%s sender=%s",update.get("update_id"),"callback_query" if callback else ("message" if message else "other"),sender.get("id","unknown")); handle_update(update)
                except Exception as exc:
                    log.exception("Update %s failed",update.get("update_id")); message=update.get("message") or {}; callback=update.get("callback_query") or {}; chat_id=message.get("chat",{}).get("id") or callback.get("message",{}).get("chat",{}).get("id"); sender=message.get("from") or callback.get("from") or {}
                    if chat_id and is_admin(sender.get("id")):
                        try: send_text(chat_id,"⚠️ پیام دریافت شد اما پردازش آن خطا داد.\nجزئیات: "+str(exc)[:250])
                        except Exception: log.exception("Could not notify admin about update failure")
                STATE["offset"]=max(int(STATE.get("offset",0)),int(update["update_id"])+1)
            save_state()
        except Exception:
            log.exception("Polling failed"); time.sleep(5)
    save_state()

if __name__ == "__main__": main()