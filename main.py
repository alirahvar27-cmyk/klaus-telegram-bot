import os
import json
import time
import hashlib
import logging
import html
import random
from pathlib import Path

import requests
from google import genai

# =========================================================

# KLAUS — Configuration

# =========================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

if not TELEGRAM_TOKEN:
raise RuntimeError("Missing GitHub Secret: TELEGRAM_BOT_TOKEN")

if not GEMINI_API_KEY:
raise RuntimeError("Missing GitHub Secret: GEMINI_API_KEY")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
STATE_FILE = Path("sent.json")
MAX_HISTORY = 2000

HTTP = requests.Session()
HTTP.headers.update({
"User-Agent": "KLAUS-Publisher/1.0 (Telegram content automation)"
})

AI = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(
level=logging.INFO,
format="%(asctime)s [%(levelname)s] %(message)s",
)
LOG = logging.getLogger("KLAUS")

# =========================================================

# Channels

# =========================================================

CHANNELS = {
"@TechNamaFa": ("تک‌نما", "فناوری و گوشی هوشمند"),
"@NbzeKhabar": ("نبض خبر", "خبر و سواد خبری و راستی‌آزمایی"),
"@Khndedoon": ("خنده‌دون", "طنز و حیوانات بامزه"),
"@RazKehann": ("راز کیهان", "نجوم و کیهان"),
"@FilmGardFa": ("فیلم‌گرد", "فیلم و سینما"),
"@MazeKhoooneh": ("مزه‌خونه", "آشپزی و غذا"),
"@HaleKhoobDaiily": ("حال خوب", "آرامش و عادت‌های سالم"),
"@SafarkadehFa": ("سفرکده", "سفر و گردشگری"),
"@ZehnAgahh": ("ذهن‌آگاه", "ذهن‌آگاهی و تمرکز"),
"@PoolBalad": ("پول‌بلد", "سواد مالی و بودجه‌بندی"),
"@LevelUpFa": ("لِوِل‌آپ", "رشد فردی و یادگیری"),
"@NimeShabHorror": ("نیمه‌شب", "داستان ترسناک خیالی"),
"@TradePulseFa": ("تریدپالس", "آموزش بازار و مدیریت ریسک"),
"@NetPlusFa": ("نت‌پلاس", "شبکه، DNS و امنیت سایبری"),
}

POLL_CHANNELS = {
"@TechNamaFa",
"@NbzeKhabar",
"@Khndedoon",
"@RazKehann",
"@FilmGardFa",
"@MazeKhoooneh",
"@SafarkadehFa",
"@PoolBalad",
"@LevelUpFa",
"@NimeShabHorror",
"@TradePulseFa",
"@NetPlusFa",
}

# =========================================================

# Persistent duplicate-prevention state

# =========================================================

def load_state():
if not STATE_FILE.exists():
return []

```
try:
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [str(item) for item in data]
except (OSError, json.JSONDecodeError) as exc:
    LOG.warning("Could not read sent.json: %s", exc)

return []
```

STATE = load_state()

def save_state():
temp_file = STATE_FILE.with_suffix(".tmp")
temp_file.write_text(
json.dumps(STATE[-MAX_HISTORY:], ensure_ascii=False),
encoding="utf-8",
)
temp_file.replace(STATE_FILE)

def content_hash(channel, text):
normalized = " ".join(text.split()).casefold()
return hashlib.sha256(
f"{channel}:{normalized}".encode("utf-8")
).hexdigest()

# =========================================================

# Telegram API with retries

# =========================================================

def telegram(method, payload, attempts=3):
url = f"{TELEGRAM_API}/{method}"
last_error = None

```
for attempt in range(attempts):
    try:
        response = HTTP.post(url, json=payload, timeout=40)

        if response.status_code == 429:
            try:
                retry_after = int(
                    response.json().get("parameters", {}).get(
                        "retry_after", 5
                    )
                )
            except (ValueError, TypeError):
                retry_after = 5

            time.sleep(min(max(retry_after, 1), 60))
            continue

        response.raise_for_status()
        result = response.json()

        if not result.get("ok"):
            raise RuntimeError(
                f"Telegram API rejected {method}: {result}"
            )

        return result["result"]

    except (requests.RequestException, ValueError, RuntimeError) as exc:
        last_error = exc

        if attempt < attempts - 1:
            time.sleep(2 ** attempt)

raise RuntimeError(
    f"Telegram {method} failed after {attempts} attempts: "
    f"{last_error}"
)
```

# =========================================================

# AI content generation

# =========================================================

def build_prompt(channel, name, topic):
special_rules = ""

```
if channel == "@NbzeKhabar":
    special_rules = """
```

خبر فوری یا رویداد روز را بدون منبع تأییدشده ادعا نکن.
در نبود داده زنده، درباره سواد خبری، بررسی منابع و راستی‌آزمایی بنویس.
"""

```
elif channel in ("@PoolBalad", "@TradePulseFa"):
    special_rules = """
```

محتوا آموزشی باشد، نه توصیه شخصی سرمایه‌گذاری.
سود تضمینی، سیگنال خریدوفروش یا قیمت لحظه‌ای ساختگی ارائه نکن.
"""

```
elif channel == "@NetPlusFa":
    special_rules = """
```

روی امنیت دفاعی، حفظ حریم خصوصی و تنظیمات امن تمرکز کن.
روش نفوذ به حساب دیگران یا سرویس و پروکسی ساختگی معرفی نکن.
"""

```
elif channel == "@NimeShabHorror":
    special_rules = """
```

داستان ترسناک را تخیلی بنویس و آن را به‌عنوان خبر واقعی معرفی نکن.
"""

```
elif channel == "@MazeKhoooneh":
    special_rules = """
```

در دستور غذا، مواد اولیه و مراحل قابل‌فهم ارائه کن.
زمان یا دمای پخت را در صورت نامطمئن بودن قطعی جلوه نده.
"""

```
return f"""
```

برای کانال تلگرامی فارسی «{name}» با موضوع «{topic}» محتوا تولید کن.

الزامات:

* فارسی روان و طبیعی بنویس.
* عنوان جذاب و متن حدود 100 تا 150 کلمه داشته باش.
* متن برای خواندن در تلفن همراه مناسب باشد.
* از ایموجی محدود استفاده کن.
* از نقل‌قول، آمار، خبر، قیمت، لینک و منبع ساختگی خودداری کن.
* اگر اطلاعات زنده و تأییدشده نداری، محتوای آموزشی یا عمومی بنویس.
* از بازنویسی تکراری و عنوان‌های گمراه‌کننده خودداری کن.
  {special_rules}

فقط یک شیء JSON معتبر برگردان، بدون Markdown و توضیح بیرون از JSON:
{{
"title": "عنوان فارسی",
"text": "متن کامل پست",
"image_query": "short English image search phrase",
"poll_question": "پرسش کوتاه نظرسنجی یا رشته خالی",
"poll_options": ["گزینه اول", "گزینه دوم"]
}}

اگر نظرسنجی مناسبی نداری، poll_question را خالی و poll_options را آرایه خالی قرار بده.
"""

def generate_content(channel, name, topic):
response = AI.models.generate_content(
model=GEMINI_MODEL,
contents=build_prompt(channel, name, topic),
config={
"response_mime_type": "application/json",
"temperature": 0.8,
},
)

```
if not response.text:
    raise RuntimeError("Gemini returned an empty response")

try:
    data = json.loads(response.text)
except json.JSONDecodeError as exc:
    raise RuntimeError("Gemini returned invalid JSON") from exc

if not isinstance(data, dict):
    raise RuntimeError("Gemini response is not a JSON object")

title = str(data.get("title", "")).strip()
body = str(data.get("text", "")).strip()

if not title or not body:
    raise RuntimeError("Generated title or text is empty")

# Telegram text messages support up to 4096 characters.
post = f"{title}\n\n{body}"
if len(post) > 3900:
    post = post[:3890].rsplit(" ", 1)[0] + "…"

digest = content_hash(channel, post)

if digest in STATE:
    raise RuntimeError("Duplicate content detected; skipped")

return post, data, digest
```

# =========================================================

# Wikimedia Commons image search

# =========================================================

def find_image(query):
if not query:
return None

```
try:
    response = HTTP.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 10,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1200,
            "format": "json",
        },
        timeout=25,
    )
    response.raise_for_status()

    pages = response.json().get("query", {}).get("pages", {})
    candidates = []

    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")

        if not url or not url.startswith("https://"):
            continue

        clean_url = url.split("?")[0].lower()
        if not clean_url.endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):
            continue

        metadata = info.get("extmetadata", {})

        def meta_value(key):
            value = metadata.get(key, {}).get("value", "")
            return html.unescape(str(value)).strip()

        candidates.append({
            "url": url,
            "title": page.get("title", ""),
            "artist": meta_value("Artist"),
            "license": meta_value("LicenseShortName"),
            "description": meta_value("ImageDescription"),
            "source": (
                "https://commons.wikimedia.org/wiki/"
                + requests.utils.quote(page.get("title", "").replace(
                    " ", "_"
                ), safe=":/()")
            ),
        })

    return random.choice(candidates) if candidates else None

except (requests.RequestException, ValueError, TypeError) as exc:
    LOG.warning("Image search failed: %s", exc)
    return None
```

def image_attribution(image):
if not image:
return ""

```
parts = []

if image.get("artist"):
    parts.append(f"پدیدآورنده: {image['artist'][:180]}")

if image.get("license"):
    parts.append(f"مجوز: {image['license'][:80]}")

if image.get("source"):
    parts.append(f"منبع: {image['source']}")

return "\n\n" + "\n".join(parts) if parts else ""
```

# =========================================================

# Publishing

# =========================================================

def publish_post(channel, post, image):
# Send text-only if no usable image was found.
if not image:
telegram("sendMessage", {
"chat_id": channel,
"text": post,
})
return

```
# Keep attribution with the image caption where possible.
attribution = image_attribution(image)
caption = post

if attribution:
    room = 1000 - len(attribution) - 1
    if room >= 100:
        caption = post[:room].rstrip() + attribution
    else:
        caption = post[:1000]

try:
    telegram("sendPhoto", {
        "chat_id": channel,
        "photo": image["url"],
        "caption": caption[:1000],
    })

except Exception as exc:
    LOG.warning(
        "Image publishing failed for %s; falling back to text: %s",
        channel,
        exc,
    )
    telegram("sendMessage", {
        "chat_id": channel,
        "text": post,
    })
```

def publish_poll(channel, data):
if channel not in POLL_CHANNELS:
return

```
question = str(data.get("poll_question", "")).strip()
raw_options = data.get("poll_options", [])

if not question or not isinstance(raw_options, list):
    return

options = []
for item in raw_options:
    if not isinstance(item, str):
        continue

    option = item.strip()
    if option and option not in options:
        options.append(option[:100])

options = options[:4]

if not 2 <= len(options) <= 4:
    return

telegram("sendPoll", {
    "chat_id": channel,
    "question": question[:300],
    "options": options,
    "is_anonymous": True,
})
```

# =========================================================

# Main scheduler job

# =========================================================

def main():
errors = []

```
LOG.info("KLAUS starting; channels=%d", len(CHANNELS))
LOG.info("Configured Gemini model: %s", GEMINI_MODEL)

for channel, (name, topic) in CHANNELS.items():
    try:
        post, data, digest = generate_content(
            channel,
            name,
            topic,
        )

        image_query = str(data.get("image_query", "")).strip()
        image = find_image(image_query) if image_query else None

        # Publish the main post.
        publish_post(channel, post, image)

        # Save the successful post before trying the optional poll.
        STATE.append(digest)
        del STATE[:-MAX_HISTORY]
        save_state()

        try:
            publish_poll(channel, data)
        except Exception as exc:
            LOG.error("Poll failed for %s: %s", channel, exc)
            errors.append(f"{channel}: poll failed: {exc}")

        LOG.info("Published successfully: %s", channel)

    except Exception as exc:
        errors.append(f"{channel}: {exc}")
        LOG.exception("Channel failed: %s", channel)

    # Avoid sending requests too quickly across channels.
    time.sleep(3)

LOG.info(
    "KLAUS finished. channels=%d errors=%d",
    len(CHANNELS),
    len(errors),
)

if errors:
    # Makes GitHub Actions mark the run as failed
    # so errors can be reviewed in the Actions logs.
    raise RuntimeError("\n".join(errors))
```

if **name** == "**main**":
main()
