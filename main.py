
import os
import json
import time
import random
import hashlib
import requests
from pathlib import Path
from google import genai

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API = f"https://api.telegram.org/bot{TOKEN}"

CHANNELS = {
    "@TechNamaFa": ("تک‌نما", "فناوری و گوشی"),
    "@NbzeKhabar": ("نبض خبر", "سواد خبری و راستی‌آزمایی"),
    "@Khndedoon": ("خنده‌دون", "طنز و حیوانات بامزه"),
    "@RazKehann": ("راز کیهان", "نجوم و فضا"),
    "@FilmGardFa": ("فیلم‌گرد", "معرفی فیلم و سینما"),
    "@MazeKhoooneh": ("مزه‌خونه", "آشپزی و غذا"),
    "@HaleKhoobDaiily": ("حال خوب", "آرامش و عادت‌های سالم"),
    "@SafarkadehFa": ("سفرکده", "گردشگری و سفر"),
    "@ZehnAgahh": ("ذهن‌آگاه", "ذهن‌آگاهی و تمرکز"),
    "@PoolBalad": ("پول‌بلد", "سواد مالی و بودجه‌بندی"),
    "@LevelUpFa": ("لِوِل‌آپ", "رشد فردی و یادگیری"),
    "@NimeShabHorror": ("نیمه‌شب", "داستان ترسناک خیالی"),
    "@TradePulseFa": ("تریدپالس", "آموزش بازار و مدیریت ریسک"),
    "@NetPlusFa": ("نت‌پلاس", "شبکه، DNS و امنیت سایبری"),
}

POLL_CHANNELS = {
    "@TechNamaFa", "@Khndedoon", "@RazKehann",
    "@FilmGardFa", "@MazeKhoooneh", "@SafarkadehFa",
    "@PoolBalad", "@LevelUpFa", "@NimeShabHorror",
    "@TradePulseFa", "@NetPlusFa", "@NbzeKhabar"
}

STATE_FILE = Path("sent.json")
state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else []

def tg(method, data):
    r = requests.post(f"{API}/{method}", json=data, timeout=40)
    r.raise_for_status()
    result = r.json()
    if not result.get("ok"):
        raise RuntimeError(result)
    return result["result"]

def make_content(channel, name, topic):
    prompt = f"""
برای کانال تلگرامی فارسی «{name}» درباره «{topic}» محتوای حرفه‌ای تولید کن.
پست 100 تا 150 کلمه، تیتر جذاب، پاراگراف‌بندی مناسب موبایل و ایموجی محدود داشته باشد.
اطلاعات، خبر، لینک، قیمت یا منبع ساختگی نده.
برای خبر، اگر اطلاعات زنده تأییدشده نداری، محتوای سواد خبری تولید کن.
برای نت‌پلاس آموزش امن شبکه و حریم خصوصی بده؛ سرویس یا پروکسی ساختگی معرفی نکن.
برای مالی و ترید آموزش بده، نه سیگنال یا وعده سود.
فقط JSON معتبر برگردان با این کلیدها:
title, text, image_query, poll_question, poll_options
image_query عبارت انگلیسی برای یافتن عکس مرتبط باشد.
poll_question پرسش کوتاه؛ poll_options شامل 2 تا 4 گزینه کوتاه.
"""
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )
    data = json.loads(response.text)
    title = str(data.get("title", name)).strip()
    text = str(data.get("text", "")).strip()
    if not text:
        raise RuntimeError("متن خالی است")
    post = f"{title}\n\n{text}"
    digest = hashlib.sha256((channel + post).encode()).hexdigest()
    if digest in state:
        raise RuntimeError("محتوای تکراری؛ ارسال نشد")
    return post[:3900], data, digest

def find_image(query):
    if not query:
        return None
    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "generator": "search",
                "gsrsearch": query, "gsrnamespace": 6,
                "gsrlimit": 8, "prop": "imageinfo",
                "iiprop": "url", "iiurlwidth": 1200,
                "format": "json"
            }, timeout=20
        )
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
        images = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            if url and url.lower().split("?")[0].endswith(
                (".jpg", ".jpeg", ".png", ".webp")
            ):
                images.append(url)
        return random.choice(images) if images else None
    except Exception as e:
        print("Image search error:", e)
        return None

def main():
    errors = []
    for channel, (name, topic) in CHANNELS.items():
        try:
            post, data, digest = make_content(channel, name, topic)
            image = find_image(str(data.get("image_query", topic)))

            if image:
                try:
                    tg("sendPhoto", {
                        "chat_id": channel,
                        "photo": image,
                        "caption": post[:1000]
                    })
                except Exception as e:
                    print("Photo fallback:", e)
                    tg("sendMessage", {"chat_id": channel, "text": post})
            else:
                tg("sendMessage", {"chat_id": channel, "text": post})

            question = str(data.get("poll_question", "")).strip()
            options = data.get("poll_options", [])
            if channel in POLL_CHANNELS and question and isinstance(options, list):
                options = [str(x).strip() for x in options if str(x).strip()][:4]
                if 2 <= len(options) <= 4:
                    tg("sendPoll", {
                        "chat_id": channel,
                        "question": question[:300],
                        "options": options,
                        "is_anonymous": True
                    })

            state.append(digest)
            state[:] = state[-300:]
            STATE_FILE.write_text(
                json.dumps(state, ensure_ascii=False),
                encoding="utf-8"
            )
            print("Published:", channel)
        except Exception as e:
            errors.append(f"{channel}: {e}")
            print("FAILED:", channel, e)
        time.sleep(2)

    if errors:
        raise RuntimeError("\n".join(errors))

if __name__ == "__main__":
    main()