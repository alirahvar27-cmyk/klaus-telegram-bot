import os
import time
from google import genai
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = "gemini-3.5-flash-lite"
client = genai.Client(api_key=API_KEY)

CHANNELS = {
    "@TechNamaFa": "فناوری و گوشی هوشمند",
    "@NbzeKhabar": "سواد خبری و توضیح بی‌طرفانه رویدادهای جهان؛ خبر روز را جعل نکن",
    "@Khndedoon": "طنز و موقعیت‌های بامزه حیوانات",
    "@RazKehann": "نجوم و رازهای کیهان",
    "@FilmGardFa": "سینما و دانستنی‌های فیلم",
    "@MazeKhoooneh": "آشپزی و غذاهای ایرانی",
    "@HaleKhoobDaiily": "آرامش و حال خوب",
    "@SafarkadehFa": "گردشگری و مقصدهای سفر",
    "@ZehnAgahh": "ذهن‌آگاهی و تمرین‌های آرامش",
    "@PoolBalad": "آموزش عمومی سواد مالی",
    "@LevelUpFa": "رشد فردی و کتاب",
    "@NimeShabHorror": "داستان ترسناک کوتاه و خیالی",
    "@TradePulseFa": "آموزش بازار سهام و مدیریت ریسک؛ بدون توصیه خرید و فروش",
    "@NetPlusFa": "شبکه، اینترنت و امنیت سایبری",
}


def make_post(topic):
    prompt = f"""یک پست فارسی جذاب و طبیعی برای کانال تلگرام درباره «{topic}» بنویس.
    80 تا 140 کلمه، مفید و خوش‌خوان باشد.
    تیتر کوتاه داشته باشد؛ ایموجی کم و به‌جا استفاده کن.
    کلیشه، اطلاعات ساختگی، تجربه شخصی جعلی و سؤال پایانی اجباری ممنوع.
    فقط متن نهایی پست را برگردان. برای موضوعات خبری، خبر روز یا نقل‌قول تأییدنشده نساز."""
    result = client.models.generate_content(model=MODEL, contents=prompt)
    text = (result.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty post")
    return text[:4000]


def send_post(channel, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": channel, "text": text},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram error for {channel}: {data}")


def main():
    failures = []
    for channel, topic in CHANNELS.items():
        try:
            post = make_post(topic)
            send_post(channel, post)
            print(f"Published: {channel}")
        except Exception as exc:
            failures.append(channel)
            print(f"FAILED: {channel}: {exc}")
        time.sleep(2)
    if failures:
        raise RuntimeError("Some channels failed: " + ", ".join(failures))
    print("KLAUS finished all 14 channels.")

if __name__ == "__main__":
    main()
