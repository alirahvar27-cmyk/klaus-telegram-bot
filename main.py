import os
from google import genai
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API_KEY = os.environ["GEMINI_API_KEY"]
CHANNEL = "@TechNamaFa"
MODEL = "gemini-3.5-flash-lite"

client = genai.Client(api_key=API_KEY)


def main():
    prompt = """یک پست فارسی کوتاه و مفید درباره فناوری گوشی‌های هوشمند بنویس.
حدود 100 کلمه، با تیتر جذاب و ایموجی کم.
اطلاعات ساختگی ننویس و سؤال پایانی اجباری نگذار.
فقط متن نهایی پست را برگردان."""
    result = client.models.generate_content(model=MODEL, contents=prompt)
    post = (result.text or "").strip()
    if not post:
        raise RuntimeError("Gemini returned empty text")

    response = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHANNEL, "text": post},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(str(data))
    print(f"Test post sent to {CHANNEL}")

if __name__ == "__main__":
    main()
