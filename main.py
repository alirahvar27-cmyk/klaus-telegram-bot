
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
# Publishing is disabled unless DRY_RUN contains exactly "false".
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
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip() or "mistral-small-latest"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_MODEL = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast").strip() or "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
AI_ORDER = [
    item.strip().lower()
    for item in os.getenv("KLAUS_AI_ORDER", "gemini,mistral,groq,openrouter,cloudflare,openai").split(",")
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