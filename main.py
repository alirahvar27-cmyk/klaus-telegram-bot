import os
import json
import time
import hashlib
import logging
import html
import random
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse

import feedparser

from source_adapters import normalize_source_item

import requests
from google import genai

# =========================================================
# KLAUS - Configuration
# =========================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

STATE_FILE = Path("sent.json")
DRY_RUN_FILE = Path("DRY_RUN")
MAX_HISTORY = 2000

# SAFE BY DEFAULT:
# An explicit DRY_RUN environment variable takes precedence; otherwise use the
# repository file. Publishing stays disabled if neither explicitly says false.
dry_run_env = os.getenv("DRY_RUN")
if dry_run_env is not None:
    DRY_RUN = dry_run_env.strip().lower() != "false"
else:
    try:
        DRY_RUN = (
            DRY_RUN_FILE.read_text(encoding="utf-8").strip().lower()
            != "false"
        )
    except OSError:
        DRY_RUN = True

TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    if TELEGRAM_TOKEN
    else ""
)

HTTP = requests.Session()
HTTP.headers.update({
    "User-Agent": "KLAUS-Publisher/1.0"
})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
LOG = logging.getLogger("KLAUS")

# AI providers are optional individually; KLAUS uses whichever valid keys are configured.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b"
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip() or "mistral-small-latest"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_MODEL = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast").strip() or "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
AI_ORDER = [
    item.strip().lower()
    for item in (os.getenv("KLAUS_AI_ORDER") or "gemini,mistral,groq,openrouter,cloudflare,openai").split(",")
    if item.strip().lower() in {"gemini", "mistral", "openai", "groq", "openrouter", "cloudflare"}
]
AI = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

if not any([GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY, (CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID)]):
    raise RuntimeError(
        "No AI provider configured. Add at least one of GEMINI_API_KEY, "
        "OPENAI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY, or both CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in GitHub Secrets."
    )

# A Telegram token is required only when real publishing is enabled.
if not DRY_RUN and not TELEGRAM_TOKEN:
    raise RuntimeError("Missing GitHub Secret: TELEGRAM_BOT_TOKEN")


# =========================================================
# Channels
# =========================================================

CHANNELS = {
    "@TechNamaFa": ("تک‌نما", "فناوری و گوشی هوشمند"),
    "@NbzeKhabar": ("نبض خبر", "خبر و سواد خبری و راستی‌آزمایی"),
    "@Khndedoon": ("خنده‌دون", "سرگرمی، طنز و محتوای شاد و خنده‌دار متنوع"),
    "@RazKehann": ("راز کیهان", "نجوم و کیهان"),
    "@FilmGardFa": ("فیلم‌گرد", "فیلم و سینما"),
    "@MazeKhoooneh": ("مزه‌خونه", "آشپزی و غذا"),
    "@HaleKhoobDaiily": ("حال خوب", "آرامش و عادت‌های سالم"),
    "@SafarkadehFa": ("سفرکده", "سفر و گردشگری"),
    "@ZehnAgahh": ("ذهن‌آگاه", "ذهن‌آگاهی و تمرکز"),
    "@PoolBalad": ("پول‌بلد", "سواد مالی و بودجه‌بندی"),
    "@LevelUpFa": ("لِوِل‌آپ", "بازی‌های ویدیویی، اخبار گیم، معرفی و نقد بازی، راهنما و صنعت بازی"),
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

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(item) for item in data]
    except (OSError, json.JSONDecodeError) as exc:
        LOG.warning("Could not read sent.json: %s", exc)

    return []


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
    raw = f"{channel}:{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# =========================================================
# Telegram API
# =========================================================

def telegram(method, payload, attempts=3):
    if DRY_RUN:
        raise RuntimeError("Safety guard: Telegram disabled in DRY_RUN")

    if not TELEGRAM_API:
        raise RuntimeError("Telegram token is missing")

    url = f"{TELEGRAM_API}/{method}"
    last_error = None

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
                    f"Telegram rejected {method}: {result}"
                )

            return result["result"]

        except (
            requests.RequestException,
            ValueError,
            RuntimeError,
        ) as exc:
            last_error = exc

            if attempt < attempts - 1:
                time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Telegram {method} failed: {last_error}"
    )



# =========================================================
# AI content generation
# =========================================================

def build_prompt(channel, name, topic):
    special_rules = ""

    if channel == "@NbzeKhabar":
        special_rules = """
خبر فوری یا رویداد روز را بدون منبع تأییدشده ادعا نکن.
در نبود اطلاعات زنده، درباره سواد خبری و راستی‌آزمایی بنویس.
"""

    elif channel in ("@PoolBalad", "@TradePulseFa"):
        special_rules = """
محتوا آموزشی باشد، نه توصیه شخصی سرمایه‌گذاری.
سود تضمینی، سیگنال خریدوفروش یا قیمت لحظه‌ای ساختگی ارائه نکن.
"""

    elif channel == "@NetPlusFa":
        special_rules = """
روی امنیت دفاعی، حریم خصوصی و تنظیمات امن تمرکز کن.
روش نفوذ به حساب دیگران آموزش نده.
"""

    elif channel == "@NimeShabHorror":
        special_rules = """
داستان ترسناک را تخیلی بنویس و آن را خبر واقعی معرفی نکن.
"""

    elif channel == "@MazeKhoooneh":
        special_rules = """
مواد اولیه و مراحل دستور غذا را روشن و قابل‌فهم بنویس.
"""

    return f"""
برای کانال فارسی «{name}» با موضوع «{topic}» یک پست تهیه کن.

قواعد:
- فارسی روان و طبیعی بنویس.
- عنوان جذاب و متن حدود 100 تا 150 کلمه داشته باش.
- متن برای تلفن همراه مناسب باشد.
- از ایموجی محدود استفاده کن.
- خبر، آمار، نقل‌قول، قیمت و لینک ساختگی نساز.
- اگر اطلاعات زنده و تأییدشده نداری، محتوای آموزشی یا عمومی بنویس.
- از تکرار و عنوان گمراه‌کننده خودداری کن.
- image_query باید یک عبارت انگلیسی دقیق برای عکس واقعی، زیبا، باکیفیت و مرتبط مستقیم با موضوع همین پست باشد؛ نه عبارت عمومی مثل "man using smartphone outdoors".
- تصویر باید حس عکس تحریریه‌ای حرفه‌ای، نور طبیعی و ترکیب‌بندی تمیز داشته باشد.
- از عکس‌های بی‌ربط، آدم‌های تصادفی، عکس‌های کم‌کیفیت، اسکرین‌شات، پوستر متنی، لوگو، واترمارک و تصاویر تکراری دوری کن.
{special_rules}

فقط یک شیء JSON معتبر برگردان، بدون Markdown:
{{
  "title": "عنوان فارسی",
  "text": "متن کامل پست",
  "image_query": "short English image search phrase",
  "poll_question": "",
  "poll_options": []
}}

اگر نظرسنجی مناسبی نداری، poll_question و poll_options را خالی بگذار.
"""


def generate_ai_response(prompt):
    """Try configured AI providers in order and return generated text."""
    errors = []
    providers = {
        "gemini": bool(GEMINI_API_KEY),
        "mistral": bool(MISTRAL_API_KEY),
        "groq": bool(GROQ_API_KEY),
        "openrouter": bool(OPENROUTER_API_KEY),
        "cloudflare": bool(CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID),
        "openai": bool(OPENAI_API_KEY),
    }

    for provider in AI_ORDER:
        if not providers.get(provider):
            continue
        try:
            if provider == "gemini":
                response = AI.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "temperature": 0.8,
                    },
                )
                text = (response.text or "").strip()
            else:
                configs = {
                    "mistral": (
                        "https://api.mistral.ai/v1/chat/completions",
                        MISTRAL_API_KEY, MISTRAL_MODEL,
                    ),
                    "groq": (
                        "https://api.groq.com/openai/v1/chat/completions",
                        GROQ_API_KEY, GROQ_MODEL,
                    ),
                    "openrouter": (
                        "https://openrouter.ai/api/v1/chat/completions",
                        OPENROUTER_API_KEY, OPENROUTER_MODEL,
                    ),
                    "cloudflare": (
                        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions",
                        CLOUDFLARE_API_TOKEN, CLOUDFLARE_MODEL,
                    ),
                    "openai": (
                        "https://api.openai.com/v1/chat/completions",
                        OPENAI_API_KEY, OPENAI_MODEL,
                    ),
                }
                endpoint, api_key, model = configs[provider]
                response = HTTP.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "Return only one valid JSON object. No Markdown."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.8,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=90,
                )
                response.raise_for_status()
                payload = response.json()
                text = str(
                    payload.get("choices", [{}])[0]
                    .get("message", {}).get("content", "")
                ).strip()

            if text:
                LOG.info("AI provider succeeded: %s", provider)
                return text
            raise RuntimeError("Provider returned empty content")
        except Exception as exc:
            LOG.warning("AI provider %s failed: %s", provider, exc)
            errors.append(f"{provider}: {exc}")

    raise RuntimeError("All configured AI providers failed: " + "; ".join(errors))


def generate_content(channel, name, topic):
    raw = generate_ai_response(build_prompt(channel, name, topic))
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI provider returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise RuntimeError("AI response is not a JSON object")

    title = str(data.get("title", "")).strip()
    body = str(data.get("text", "")).strip()
    if not title or not body:
        raise RuntimeError("Generated title or text is empty")

    post = f"{title}\n\n{body}"
    if len(post) > 3900:
        post = post[:3890].rsplit(" ", 1)[0] + "…"

    digest = content_hash(channel, post)
    if digest in STATE:
        raise RuntimeError("Duplicate content detected; skipped")

    return post, data, digest

# =========================================================
# Wikimedia Commons image search
# =========================================================

def find_image(query):
    if not query:
        return None

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

        query_words = {
            word.casefold() for word in re.findall(r"[a-zA-Z]{3,}", query)
            if word.casefold() not in {"photo", "image", "beautiful", "high", "quality", "professional", "editorial"}
        }
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")

            if not url or not url.startswith("https://"):
                continue

            clean_url = url.split("?")[0].lower()
            if not clean_url.endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue

            metadata = info.get("extmetadata", {})

            def meta_value(key):
                value = metadata.get(key, {}).get("value", "")
                value = html.unescape(str(value)).strip()
                return re.sub(r"<[^>]+>", "", value).strip()

            # Keep only public-domain/CC0 images so captions need no visible credit line.
            license_name = meta_value("LicenseShortName").casefold().replace(" ", "")
            usage_terms = meta_value("UsageTerms").casefold().replace(" ", "")
            allowed_license = (
                "publicdomain" in license_name
                or "publicdomain" in usage_terms
                or license_name == "cc0"
                or usage_terms == "cc0"
                or "creativecommonszero" in license_name
            )
            if not allowed_license:
                continue

            title = page.get("title", "")
            title_words = set(re.findall(r"[a-zA-Z]{3,}", title.casefold()))
            overlap = len(query_words & title_words)
            width = int(info.get("width") or 0)
            height = int(info.get("height") or 0)
            if width and height and (width < 700 or height < 450):
                continue
            if query_words and overlap == 0:
                continue
            candidates.append({
                "url": url,
                "title": title.removeprefix("File:"),
                "artist": meta_value("Artist"),
                "license": meta_value("LicenseShortName"),
                "source": (
                    "https://commons.wikimedia.org/wiki/"
                    + quote(title.replace(" ", "_"), safe=":/()")
                ),
                "score": overlap,
                "resolution": width * height,
            })

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item["score"], item["resolution"]), reverse=True)
        best_score = candidates[0]["score"]
        best = [item for item in candidates if item["score"] >= best_score and item["score"] > 0]
        return random.choice(best[:3]) if best else None

    except (
        requests.RequestException,
        ValueError,
        TypeError,
    ) as exc:
        LOG.warning("Image search failed: %s", exc)
        return None


def image_attribution(image):
    """Image credits are intentionally not appended to captions."""
    return ""


# =========================================================
# Publishing
# =========================================================

def channel_footer(channel):
    # Plain channel username, exactly as requested.
    return f"\n\n{channel}"


def publish_post(channel, post, image):
    if DRY_RUN:
        LOG.info("DRY RUN: skipped post for %s", channel)
        return

    footer = channel_footer(channel)
    if not image:
        telegram("sendMessage", {
            "chat_id": channel,
            "text": post[:3900] + footer,
            "disable_web_page_preview": True,
        })
        return

    # No image title, author, license, or Wikimedia URL is appended to the post.
    caption = post
    if len(caption) + len(footer) > 1024:
        caption = caption[:max(100, 1024 - len(footer) - 1)].rstrip() + "…"
    caption += footer

    try:
        telegram("sendPhoto", {
            "chat_id": channel,
            "photo": image["url"],
            "caption": caption[:1024],
        })

    except Exception as exc:
        LOG.warning(
            "Image publishing failed for %s; falling back to text: %s",
            channel,
            exc,
        )
        telegram("sendMessage", {
            "chat_id": channel,
            "text": post[:3900] + footer,
            "disable_web_page_preview": True,
        })


def publish_poll(channel, data):
    if DRY_RUN:
        LOG.info("DRY RUN: skipped poll for %s", channel)
        return

    if channel not in POLL_CHANNELS:
        return

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


# =========================================================
# Main job
# =========================================================

def main():
    errors = []

    LOG.info("KLAUS starting; channels=%d", len(CHANNELS))
    LOG.info("Configured Gemini model: %s", GEMINI_MODEL)
    LOG.info("DRY_RUN=%s", DRY_RUN)

    if DRY_RUN:
        LOG.info("SAFE TEST MODE: no Telegram posts or polls will be sent.")

    for channel, (name, topic) in CHANNELS.items():
        try:
            post, data, digest = generate_content(channel, name, topic)

            image_query = str(data.get("image_query", "")).strip()
            image = find_image(image_query) if image_query else None

            if DRY_RUN:
                LOG.info("DRY RUN PREVIEW — channel: %s", channel)
                LOG.info("POST:\n%s", post)
                LOG.info("Image found: %s", bool(image))
                LOG.info("Poll proposed: %s", bool(str(data.get("poll_question", "")).strip()))
                continue

            publish_post(channel, post, image)

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

        if not DRY_RUN:
            time.sleep(3)

    LOG.info(
        "KLAUS finished. channels=%d errors=%d dry_run=%s",
        len(CHANNELS),
        len(errors),
        DRY_RUN,
    )

    if errors:
        raise RuntimeError("\n".join(errors))


if __name__ == "__main__":
    main()
