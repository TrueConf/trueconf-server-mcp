# ── Агрегатор инструментов: импорт обоих upstream-доменов триггерит
#    регистрацию @mcp.tool() во всех подпакетах ──────────────────────────
from app.mcp.tools import (
    trueconf_server,  # noqa: F401
    trueconf_server_ai,  # noqa: F401
)
