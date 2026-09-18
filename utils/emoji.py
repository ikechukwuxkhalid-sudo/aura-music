"""Premium emoji manager — owner can toggle / upload / set mappings"""

import json
from pathlib import Path
from config import EMOJI_FILE, PREMIUM_EMOJI_ENABLED

# Built-in useful mappings from your emoji file
DEFAULT_MAP = {
    "fire": ("5289722755871162900", "🔥"),
    "rocket": ("5372917041193828849", "🚀"),
    "check": ("5778197216170612822", "✅"),
    "star": ("5778620107240511377", "⭐"),
    "ban": ("5332296662142434561", "⛔️"),
    "warning": ("6129782440157256336", "⚠️"),
    "crown": ("6129705083501293112", "👑"),
    "shield": ("5778350254445303205", "🛡"),
    "lock": ("6129906126625447892", "🔒"),
    "unlock": ("5355075407743826720", "🔓"),
    "users": ("5778295678295872471", "👤"),
    "chart": ("6129801569941592173", "📊"),
    "bell": ("6129577213734952104", "🔔"),
    "boom": ("6129532314146838421", "💥"),
    "zap": ("6129805465476929485", "⚡"),
    "ok": ("5458604417592863845", "👍"),
    "eyes": ("5280881372418816002", "👀"),
    "gift": ("5359664288241829619", "🎁"),
    "back": ("5352759161945867747", "🔙"),
    "wave": ("5458904472598095631", "👋"),
    "mute": ("5247100325059370738", "🔇"),
    "kick": ("5246743378917334735", "👢"),
    "warn": ("6129782440157256336", "⚠️"),
    "note": ("5210856225624824917", "📝"),
    "pin": ("6129694470637100146", "📌"),
    "link": ("5877465816030515018", "🔗"),
    "cross": ("5210952531676504517", "❌"),
    "settings": ("5877260593903177342", "⚙️"),
    "robot": ("5355051922862653659", "🤖"),
    "heart": ("5442678635909621223", "❤️"),
}

_cache = None
_enabled = PREMIUM_EMOJI_ENABLED

def _load():
    global _cache
    if _cache is not None:
        return _cache
    if EMOJI_FILE.exists():
        try:
            data = json.loads(EMOJI_FILE.read_text(encoding="utf-8"))
            _cache = {**DEFAULT_MAP, **{k: tuple(v) if isinstance(v, list) else v for k, v in data.get("map", {}).items()}}
            return _cache
        except Exception:
            pass
    _cache = dict(DEFAULT_MAP)
    return _cache

def save_map(extra: dict):
    global _cache
    m = _load()
    m.update(extra)
    _cache = m
    payload = {"map": {k: list(v) if isinstance(v, tuple) else v for k, v in m.items()}}
    EMOJI_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def set_enabled(val: bool):
    global _enabled
    _enabled = val

def is_enabled() -> bool:
    return _enabled

def pe(key: str, fallback: str = None) -> str:
    """Return premium HTML tag or plain fallback. Safe for HTML parse_mode."""
    if not _enabled:
        return fallback or key
    m = _load()
    item = m.get(key)
    if not item:
        return fallback or key
    eid, fb = item if isinstance(item, (list, tuple)) else (None, item)
    if eid and _enabled:
        return f'<tg-emoji emoji-id="{eid}">{fb or fallback or ""}</tg-emoji>'
    return fb or fallback or key

def set_emoji(key: str, emoji_id: str, fallback: str):
    save_map({key: (emoji_id, fallback)})
