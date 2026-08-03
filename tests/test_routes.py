import pytest

from app.config import Config
from app.mcp.pages import _lang_switch_vars
from tests.conftest import FakeRequest


@pytest.fixture
def cfg() -> Config:
    return Config(
        server="server.example",
        client_id="cid",
        secret="secret",
        mcp_base_url="https://localhost",
        port=443,
    )


def test_login_callback_url_is_auth_callback(cfg: Config):
    """T03: login_callback_url uses /auth/callback (was /login/callback)."""
    assert cfg.login_callback_url == "https://localhost/auth/callback"


@pytest.mark.parametrize(
    "page, expected_path",
    [
        ("", "/"),
        ("success", "/success"),
        ("error", "/error"),
    ],
)
def test_lang_switch_targets_same_page(page, expected_path):
    """T02: lang-switch URL preserves the current page path."""
    vars = _lang_switch_vars("ru", {"token": "abc"}, page=page)
    assert vars["lang_url_en"] == f"{expected_path}?token=abc&lang=en"
    assert vars["lang_url_ru"] == f"{expected_path}?token=abc&lang=ru"


def test_lang_switch_drops_existing_lang_param():
    """Switching lang replaces the old lang param, not duplicates it."""
    vars = _lang_switch_vars("ru", {"lang": "ru", "token": "x"}, page="success")
    assert vars["lang_url_en"] == "/success?token=x&lang=en"


async def test_login_page_auth_url_uses_web_route(mock_config_set, _init_i18n):
    """The OAuth authorization redirect uses the TrueConf Server web route
    /oauth2/authorize (not the API path /api/v4/oauth2/auth). The web route
    proxies to the API internally; client-side browser redirect must hit it
    without the /api/v4 prefix.
    """
    from app.mcp.routes import login_page

    request = FakeRequest(query_params={}, headers={"accept-language": "en"})
    response = await login_page(request)

    body = response.body.decode()
    assert "/oauth2/authorize" in body, (
        "auth_url must use the /oauth2/authorize web route, not /api/v4/oauth2/auth"
    )
    assert "/api/v4/oauth2/auth" not in body, (
        "auth_url must NOT include the /api/v4 prefix"
    )
    assert "client_id=test-client-id" in body
    assert "response_type=code" in body
    assert "redirect_uri=https" in body
