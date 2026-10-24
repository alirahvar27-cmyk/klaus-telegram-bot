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
BLOCKED_PHRASES = ("لینک ورود به صرافی", "ورود به VVIP رایگان")
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
    "@NetPlusFa": ("نت‌پلاس", "شبکه و امنیت سایبری"),
}
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("KLAUS-Approval")
http = requests.Session()
http.headers.update({"User-Agent": "KLAUS-Approval/1.0"})
