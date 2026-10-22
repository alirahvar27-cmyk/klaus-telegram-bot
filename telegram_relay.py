"""Authorized Telegram channel relay. Requires a Telegram user session and permission to republish sources."""
from __future__ import annotations
import asyncio, difflib, json, logging, os, re, tempfile
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import types as tl_types

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger("KLAUS.relay")
STATE_PATH = Path("telegram_relay_state.json")
MAX_MEDIA_BYTES = min(max(int(os.getenv("RELAY_MAX_MEDIA_BYTES", "50000000")), 1_000_000), 100_000_000)

# Tentative source-to-destination routing. Review these mappings before enabling.
SOURCE_TARGETS = {
    "proxymtprotoir": "@NetPlusFa", "iRoProxy": "@NetPlusFa", "MobhamV2ray": "@NetPlusFa",
    "vpnplanB": "@NetPlusFa", "diamondproxy": "@NetPlusFa", "myconfig": "@NetPlusFa",
    "CinemaBoxOrg": "@FilmGardFa", "sinema_city": "@FilmGardFa", "CinemaBoxNow": "@FilmGardFa",
    "MobhamMoviess": "@FilmGardFa", "lmdbtv": "@FilmGardFa", "Editday100": "@FilmGardFa", "PromptChat_GPT": "@TechNamaFa",
    "web3nabu": "@TradePulseFa", "tofan_signal": "@TradePulseFa", "CryptoSignal2018": "@TradePulseFa",
    "signalshah0": "@TradePulseFa", "forextrder1": "@TradePulseFa", "YeganeCrypto": "@TradePulseFa",
    "the_signal_24": "@TradePulseFa", "noxtrade": "@TradePulseFa", "signal_tx": "@TradePulseFa",
    "Tofan_Trade": "@TradePulseFa", "tradecity_pro": "@TradePulseFa", "signal_xcoin": "@TradePulseFa",
    "sabtenam_trade": "@TradePulseFa",
    "ghost_cemetery": "@NimeShabHorror", "scary_strange": "@NimeShabHorror",
    "Clashwithmrmills": "@LevelUpFa", "Tweetr_khabari": "@NbzeKhabar", "mental_tired": "@ZehnAgahh",
    "AmoyeTel": "@Khndedoon", "BetterThanDope": "@Khndedoon", "moonb78": "@Khndedoon",
    "whsii": "@Khndedoon", "sinaezzati_ir": "@Khndedoon", "kianaafr": "@Khndedoon", "hipfm": "@Khndedoon",
}

def source_targets():
    mapping = dict(SOURCE_TARGETS)
    raw = os.getenv("RELAY_SOURCE_TARGETS", "").strip()
    if raw:
        extra = json.loads(raw)
        if not isinstance(extra, dict):
            raise ValueError("RELAY_SOURCE_TARGETS must be a JSON object")
        for source, target in extra.items():
            source, target = str(source).strip().lstrip("@"), str(target).strip()
            if source and target.startswith("@"):
                mapping[source] = target
    return mapping

def load_state():
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

def save_state(state):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)

def clean_caption(text, source_user):
    text = str(text or "")
    # Strip references to any channel in the supplied source list, not just this sender.
    for username in SOURCE_TARGETS:
        text = re.sub(rf"(?i)(?:https?://)?(?:t\.me|telegram\.me)/{re.escape(username)}(?:/\d+)?", "", text)
        text = re.sub(rf"(?i)@{re.escape(username)}\b", "", text)
        text = re.sub(rf"(?i)(?<!\w){re.escape(username)}(?!\w)", "", text)
    lines = []
    source_names = tuple(name.casefold() for name in SOURCE_TARGETS)
    for line in text.splitlines():
        line = line.strip()
        lowered = line.casefold()
        if re.search(r"(?i)(?:منبع|کانال اصلی|ادامه مطلب|source|join us|عضویت)\s*[:：-]?.*(?:t\.me/|telegram\.me/|@[\w]+)", line):
            continue
        if any(name in lowered for name in source_names) and re.search(r"(?i)(?:منبع|کانال|عضویت|join|follow|ادامه|لینک)", lowered):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_caption_with_entities(text, source_user, entities):
    """Clean caption text while remapping Telegram formatting entities by UTF-16 offsets."""
    original = str(text or "")
    cleaned = clean_caption(original, source_user)
    if not cleaned or not entities:
        return cleaned, []

    def char_at_utf16(value, offset):
        units = 0
        for index, char in enumerate(value):
            if units >= offset:
                return index
            units += len(char.encode("utf-16-le")) // 2
        return len(value)

    # Build a character mapping only for unchanged portions of the source.
    matcher = difflib.SequenceMatcher(a=original, b=cleaned, autojunk=False)
    mapping = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for delta in range(i2 - i1):
                mapping[i1 + delta] = j1 + delta

    def utf16_offset(value, char_index):
        return len(value[:char_index].encode("utf-16-le")) // 2

    preserved = []
    for entity in entities or []:
        try:
            start = char_at_utf16(original, int(entity.offset))
            end = char_at_utf16(original, int(entity.offset) + int(entity.length))
        except (AttributeError, TypeError, ValueError):
            continue
        if end <= start or any(index not in mapping for index in range(start, end)):
            continue
        mapped = [mapping[index] for index in range(start, end)]
        if mapped != list(range(mapped[0], mapped[0] + len(mapped))):
            continue
        clone = dict(entity.to_dict()) if hasattr(entity, "to_dict") else {
            key: value for key, value in vars(entity).items() if not key.startswith("_")
        }
        entity_class_name = clone.pop("_", type(entity).__name__)
        clone["offset"] = utf16_offset(cleaned, mapped[0])
        clone["length"] = utf16_offset(cleaned, mapped[-1] + 1) - clone["offset"]
        entity_class = getattr(tl_types, entity_class_name, None)
        if entity_class is not None:
            try:
                preserved.append(entity_class(**clone))
            except (TypeError, ValueError):
                continue
    return cleaned, preserved

async def relay_one(client, source, target, message, state):
    source_key = source.lstrip("@")
    if message.id <= int(state.get(source_key, 0) or 0):
        return False
    caption, caption_entities = clean_caption_with_entities(message.message or "", source_key, message.entities or [])
    if message.media is not None:
        size = getattr(message.file, "size", None)
        if size and size > MAX_MEDIA_BYTES:
            LOG.warning("Skipped oversized media @%s/%s", source_key, message.id)
            state[source_key] = message.id
            save_state(state)
            return False
        with tempfile.TemporaryDirectory(prefix="telegram-relay-") as temp_dir:
            try:
                path = await client.download_media(message, file=temp_dir)
                if not path:
                    LOG.warning("Media download empty @%s/%s", source_key, message.id)
                    return False
                kwargs = {"caption": caption or None, "formatting_entities": caption_entities or None}
                if getattr(message, "voice", False):
                    kwargs["voice_note"] = True
                elif getattr(message, "video", False):
                    kwargs["supports_streaming"] = True
                await client.send_file(target, path, **kwargs)
            except Exception:
                LOG.exception("Media relay failed @%s/%s", source_key, message.id)
                return False
    elif caption:
        try:
            await client.send_message(target, caption, formatting_entities=caption_entities or None, link_preview=False)
        except Exception:
            LOG.exception("Text relay failed @%s/%s", source_key, message.id)
            return False
    state[source_key] = message.id
    save_state(state)
    LOG.info("Relayed @%s/%s -> %s (media=%s)", source_key, message.id, target, bool(message.media))
    return True

async def main_async():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_SESSION_STRING", "").strip()
    if not (api_id and api_hash and session):
        raise RuntimeError("Missing TELEGRAM_API_ID, TELEGRAM_API_HASH, or TELEGRAM_SESSION_STRING GitHub secret")
    mapping, state = source_targets(), load_state()
    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    await client.start()
    try:
        for source, target in mapping.items():
            try:
                entity = await client.get_entity(source)
                latest = await client.get_messages(entity, limit=1)
                if not latest:
                    continue
                newest_id = latest[0].id
                # First run seeds the cursor; no historical flood to destination channels.
                if source not in state:
                    state[source] = newest_id
                    save_state(state)
                    LOG.info("Baseline @%s at message %s (history not copied)", source, newest_id)
                    continue
                last_id = int(state.get(source, 0) or 0)
                if newest_id <= last_id:
                    continue
                async for message in client.iter_messages(entity, min_id=last_id, reverse=True):
                    await relay_one(client, source, target, message, state)
            except Exception as exc:
                LOG.warning("Source unavailable @%s: %s", source, exc)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main_async())
