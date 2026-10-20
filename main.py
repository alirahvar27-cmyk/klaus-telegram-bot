import os, time, requests
from google import genai

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3.5-flash-lite"

CHANNELS = {
    "@TechNamaFa": "فناوری و گوشی هوشمند",
    "@NbzeKhabar": "آموزش سواد خبری؛ خبر تأییدنشده نساز",
    "@Khndedoon": "طنز و حیوانات بامزه",
    "@RazKehann": "نجوم و رازهای کیهان",
    "@FilmGardFa": "سینما و دانستنی‌های فیلم",
    "@MazeKhoooneh": "آشپزی و غذاهای ایرانی",
    "@HaleKhoobDaiily": "آرامش و حال خوب",
    "@SafarkadehFa": "گردشگری و سفر",
    "@ZehnAgahh": "ذهن‌آگاهی و آرامش",
    "@PoolBalad": "آموزش سواد مالی",
    "@LevelUpFa": "رشد فردی و کتاب",
    "@NimeShabHorror": "داستان ترسناک خیالی",
    "@TradePulseFa": "آموزش بازار سهام و مدیریت ریسک",
    "@NetPlusFa": "شبکه و امنیت سایبری",
}

def main():
    errors = []
    for channel, topic in CHANNELS.items():
        try:
            prompt = f"یک پست فارسی طبیعی و مفید درباره {topic} بنویس. حدود 100 کلمه، تیتر جذاب، ایموجی کم، بدون کلیشه و اطلاعات ساختگی. سؤال پایانی اجباری نباشد. فقط متن پست را بده."
            result = client.models.generate_content(model=MODEL, contents=prompt)
            post = (result.text or "").strip()
            if not post:
                raise RuntimeError("متن خالی از Gemini")
            r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": channel, "text": post[:4000]}, timeout=30)
            r.raise_for_status()
            if not r.json().get("ok"):
                raise RuntimeError(str(r.json()))
            print("Published:", channel)
        except Exception as e:
            errors.append(f"{channel}: {e}")
            print("FAILED:", channel, e)
        time.sleep(2)
    if errors:
        raise RuntimeError("\n".join(errors))

if __name__ == "__main__":
    main()
