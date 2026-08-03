from pathlib import Path
from urllib.parse import urlencode

from fastmcp.utilities.ui import create_secure_html_response
from starlette.responses import HTMLResponse

from app.mcp.i18n import render_translations, translate

_TEMPLATES_DIR = Path(__file__).parent.parent / "web" / "templates"


def _read_template(name: str) -> str:
    return (_TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _lang_switch_vars(
    lang: str, query_params: dict[str, str], page: str = ""
) -> dict[str, str]:
    """Build the placeholder values for the topbar language switcher.

    Lang URLs preserve existing query params (token, error, name, ...) and
    only swap the `lang` value, so switching language never loses context.

    `page` is "" for the root login page, "success" for the token page, or
    "error" for the error page — the lang-switch URL targets the same page.
    """
    base = {k: v for k, v in query_params.items() if k != "lang"}

    def _url_for(target: str) -> str:
        params = {**base, "lang": target}
        path = f"/{page}" if page else "/"
        return f"{path}?{urlencode(params)}"

    return {
        "lang_code": lang.upper(),
        "lang_url_ru": _url_for("ru"),
        "lang_url_en": _url_for("en"),
        "lang_active_ru": "active" if lang == "ru" else "",
        "lang_active_en": "active" if lang == "en" else "",
    }


def _apply_vars(html: str, vars: dict[str, str]) -> str:
    for key, value in vars.items():
        html = html.replace("{{ " + key + " }}", value)
    return html


def login_page(
    auth_url: str, lang: str, query_params: dict[str, str], server_url: str
) -> HTMLResponse:
    html = _read_template("login.html")
    html = html.replace("{{ auth_url }}", auth_url)
    html = html.replace("{{ server_url }}", server_url)
    html = _apply_vars(html, _lang_switch_vars(lang, query_params, page=""))
    html = render_translations(html, lang)
    return create_secure_html_response(html)


def success_page(
    token: str,
    name: str,
    user_id: str,
    token_ttl: int,
    base_url: str,
    lang: str,
    query_params: dict[str, str],
    server_url: str,
) -> HTMLResponse:
    body = _read_template("success.html")
    body = body.replace("{{ token }}", token)
    body = body.replace("{{ name }}", name)
    body = body.replace("{{ user_id }}", user_id)
    body = body.replace("{{ token_ttl }}", str(token_ttl))
    body = body.replace("{{ token_ttl_hours }}", str(token_ttl // 3600))
    body = body.replace("{{ base_url }}", base_url)
    body = body.replace("{{ server_url }}", server_url)
    body = body.replace(
        "{{ t.ttl_value }}",
        translate("success.ttl", lang, count=token_ttl // 3600),
    )
    body = _apply_vars(body, _lang_switch_vars(lang, query_params, page="success"))
    body = render_translations(body, lang)
    return create_secure_html_response(body)


def error_page(
    query_params: dict[str, str], lang: str, server_url: str
) -> HTMLResponse:
    html = _read_template("error.html")
    html = html.replace("{{ server_url }}", server_url)

    # Map the error code to a human-readable message; fall back to generic.
    code = query_params.get("code", "")
    if code:
        msg = translate(f"error.{code}", lang)
        if msg == f"error.{code}":  # i18n key not found → fallback
            msg = translate("error.response_text", lang)
    else:
        msg = translate("error.response_text", lang)
    html = html.replace("{{ t.error.response_text }}", msg)

    html = _apply_vars(html, _lang_switch_vars(lang, query_params, page="error"))
    html = render_translations(html, lang)
    return create_secure_html_response(html, status_code=400)
