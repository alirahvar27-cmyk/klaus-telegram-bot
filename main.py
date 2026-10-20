import os
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

CHANNELS = [
    "@TechNamaFa",
    "@NbzeKhabar",
    "@Khndedoon",
    "@RazKehann",
    "@FilmGardFa",
    "@MazeKhoooneh",
    "@HaleKhoobDaiily",
    "@SafarkadehFa",
    "@ZehnAgahh",
    "@PoolBalad",
    "@LevelUpFa",
    "@NimeShabHorror",
    "@TradePulseFa",
    "@NetPlusFa",
]

def send_message(channel, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": channel, "text": text},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data)
    print(f"Sent to {channel}")

if __name__ == "__main__":
    print("KLAUS is ready.")
