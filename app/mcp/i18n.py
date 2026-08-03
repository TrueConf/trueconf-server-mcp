"""i18n support for TrueConf Server MCP pages.

Uses i18nice (JSON) with per-call locale detection:
?lang= query → tc_lang cookie → Accept-Language → default (ru).

Templates use full dotted placeholders like ``{{ t.login.hero_title }}``
or ``{{ t.common.subtitle }}``; a single regex pass resolves them all.
"""

from __future__ import annotations

import re
from pathlib import Path

import i18n

_LOCALES_DIR = Path(__file__).parent.parent / "web" / "locales"

SUPPORTED_LANGS: tuple[str, ...] = ("ru", "en")
DEFAULT_LANG = "ru"
LANG_COOKIE = "tc_lang"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

# Matches {{ t.namespace.key }} placeholders in templates.
_T_RE = re.compile(r"\{\{\s*t\.([a-z_]+\.[a-z_]+)\s*\}\}")
_ACCEPT_LANG_RE = re.compile(r"([a-zA-Z]{1,8})(?:-[a-zA-Z]+)?(?:;q=([0-9.]+))?")


def init_i18n() -> None:
    """Load translation files. Call once at startup."""
    i18n.load_path.append(str(_LOCALES_DIR))
    i18n.set("file_format", "yml")
    i18n.set("filename_format", "{namespace}.{locale}.{format}")
    i18n.set("fallback", DEFAULT_LANG)
    i18n.load_everything(lock=True)


def _normalize(lang: str | None) -> str | None:
    if not lang:
        return None
    base = lang.strip().lower().split("-")[0]
    return base if base in SUPPORTED_LANGS else None


def _parse_accept_language(header: str | None) -> str | None:
    if not header:
        return None
    best: tuple[float, str] | None = None
    for part in header.split(","):
        m = _ACCEPT_LANG_RE.match(part.strip())
        if not m:
            continue
        code = m.group(1).lower()
        base = code.split("-")[0]
        if base not in SUPPORTED_LANGS:
            continue
        q = float(m.group(2)) if m.group(2) else 1.0
        if best is None or q > best[0]:
            best = (q, base)
    return best[1] if best else None


def detect_lang(request) -> str:
    """Resolve the user's language: query → cookie → Accept-Language → default."""
    return (
        _normalize(request.query_params.get("lang"))
        or _normalize(request.cookies.get(LANG_COOKIE))
        or _parse_accept_language(request.headers.get("accept-language"))
        or DEFAULT_LANG
    )


def is_explicit_choice(request) -> bool:
    """True when the request carries an explicit ?lang= parameter."""
    return bool(_normalize(request.query_params.get("lang")))


def lang_cookie_value(lang: str) -> str:
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def set_lang_cookie(response, lang: str) -> None:
    response.set_cookie(
        LANG_COOKIE,
        lang_cookie_value(lang),
        max_age=COOKIE_MAX_AGE,
        path="/",
        samesite="lax",
        httponly=True,
    )


def translate(page_key: str, lang: str, **kwargs) -> str:
    """Translate a single fully-qualified key like 'login.hero_title'."""
    return i18n.t(page_key, locale=lang, **kwargs)


def render_translations(html: str, lang: str) -> str:
    """Replace every ``{{ t.ns.key }}`` placeholder with its translation."""

    def _sub(match: re.Match) -> str:
        return i18n.t(match.group(1), locale=lang)

    return _T_RE.sub(_sub, html)
