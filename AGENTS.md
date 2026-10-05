# TrueConf Server MCP

## Запуск

```bash
# Typer CLI (entry point после uv sync):
trueconf-server-mcp --server 10.0.0.1 --port 9000

# или через python main.py (тот же Typer app):
uv run python main.py --server 10.0.0.1

# с .env файлом (см. ниже):
uv run python main.py
```

Подкоманд нет: Typer схлопывает единственную команду `serve` в корень. `main.py serve --server X` падает с `Got unexpected extra argument(s) (serve)`; обманчиво, что `main.py serve --help` при этом показывает help (help обрабатывается до валидации аргументов).

Python 3.12, пакеты через `uv`. Тесты: `uv run pytest` (pytest + pytest-asyncio, `asyncio_mode = auto`, 15 файлов в `tests/`). Линтер: `uv run ruff check .`.

### Приоритет конфигурации

**CLI flags > env vars > `.env` > дефолты кода.**

1. **CLI flags** — `--server`, `--port`, `--discovery-mode {static|bm25|code}`, ... (см. `trueconf-server-mcp --help`).
2. **Environment variables** — `TRUECONF_SERVER`, `TRUECONF_MCP_PORT`, ... (Typer `envvar=` читает их автоматически).
3. **`.env` файл** — загружается через `python-dotenv` (`load_dotenv()` в начале `main.py`). Пример: `.env.example`. Реальный `.env` в `.gitignore`.
4. **Дефолты** — в сигнатурах Typer-опций и `app/config.py::Config`.

`run_server(config)` (в `main.py`) принимает готовый `Config` dataclass и запускает сервер. `Config.from_env()` — fallback для программного использования без Typer.

## Конфигурация

| Параметр CLI | Env var | По умолчанию | Описание |
|---|---|---|---|
| `--server` | `TRUECONF_SERVER` | (обязательный) | Хост TrueConf Server |
| `--client-id` | `TRUECONF_CLIENT_ID` | (обязательный) | OAuth client_id |
| `--client-secret` | `TRUECONF_SECRET` | (обязательный) | OAuth client_secret |
| `--verify-ssl/--no-verify-ssl` | `TRUECONF_VERIFY_SSL` | `true` | Проверка SSL-сертификата |
| `--base-url` | `MCP_BASE_URL` | `https://localhost` | Публичный URL сервера. По умолчанию `https://localhost` (порт 443 опускается); `http://localhost:<port>` при `--no-tls`. |
| `--port` | `TRUECONF_MCP_PORT` | `443` (`80` при `--no-tls`) | Порт. HTTPS по умолчанию 443, plain HTTP при `--no-tls` — 80. |
| `--no-tls` | `MCP_NO_TLS` | `false` | Отключить TLS — plain HTTP. Дефолт порта становится 80, самоподписанный сертификат не генерируется. |
| `--tls-cert` | `MCP_TLS_CERT` | (none → авто-генерация) | Путь к PEM-сертификату. Требует `--tls-key`. Если не указан и TLS включён — генерируется self-signed. |
| `--tls-key` | `MCP_TLS_KEY` | (none → авто-генерация) | Путь к PEM-ключу. Требует `--tls-cert`. |
| `--discovery-mode` | `DISCOVERY_MODE` | `static` | `static` (все 35 инструментов: 30 conferences + 1 users + 4 transcriptions), `bm25` (search gateway), `code` (CodeMode sandbox) |
| — | `CODE_MODE_EXPERIMENTAL` | `false` | **Deprecated** — legacy-альяс: `true` → `discovery-mode=code` (только если `--discovery-mode`/`DISCOVERY_MODE` не заданы явно) |
| `--auth-mode` | `AUTH_MODE` | `token` | `token` = ручной токен через TokenStore (единственный активный режим). `oauth` = OAuthProxy + DCR (**отключён**: `_TrueConfTokenVerifier` принимал любой токен — auth bypass; код оставлен как dead code для будущего re-enable после реализации настоящей верификации). `--auth-mode oauth` rejected Typer. |
| `--api-token-ttl` | `API_TOKEN_TTL` | `86400` | TTL нашего токена (сек) |
| `--http-timeout` | `HTTP_TIMEOUT` | `30.0` | Timeout (сек) для HTTP-запросов к TrueConf API |
| `--ai-server-url` | `AI_SERVER_URL` | (none) | Базовый URL TrueConf AI Server (напр. `sai01t.trueconf.name` — `https://` подставится сам; для plain-HTTP — явно `http://10.110.2.39`). Нужен для transcription-тул. Адрес НЕ берётся из TCS API (`GET /servers-ai` требует admin-права) |

Для локальной разработки скопируйте `.env.example` → `.env` и отредактируйте.

## TLS

По умолчанию сервер запускается на `https://0.0.0.0:443` с **автоматически сгенерированным self-signed сертификатом**. SAN сертификата берётся из host-части `MCP_BASE_URL`:
- `https://localhost` (дефолт) → SAN `[localhost, 127.0.0.1]`
- `https://10.100.2.108` → SAN `[10.100.2.108]`
- `https://conf.local` → SAN `[conf.local]`

Сертификат **персистится** в `~/Library/Application Support/fastmcp/tls/{cert.pem,key.pem}` (права `0600` на ключ) и переиспользуется между рестартами. Регенерация — при отсутствии файлов, истечении срока (<30 дней), **несовпадении SAN с текущим `MCP_BASE_URL`** или несовпадении key↔cert (self-heal после крэша между двумя атомарными установками). Новая пара сначала staging'ится во временный каталог и ставится через `os.replace`.

**Кастомный сертификат**: `--tls-cert /path/cert.pem --tls-key /path/key.pem` (оба флага обязательны, если указан хотя бы один). Используется для валидных сертификатов (Let's Encrypt и т.п.).

**Plain HTTP**: `--no-tls` — отключает TLS, дефолт порта становится 80. Bearer-токены передаются в cleartext — только для случаев, когда TLS-клиент не работает (например, LM Studio с self-signed).

### Привилегированные порты (<1024)

- **macOS** (Mojave+): бинд `0.0.0.0:443` работает **без root**. Бинд на конкретный интерфейс (`127.0.0.1:443`) требует root.
- **Linux**: требует `sudo setcap cap_net_bind_service+ep $(which python)` (один раз при установке) либо запуск под `sudo`. Без прав — exit с понятной ошибкой и подсказкой про `setcap`/`sudo`/`--port 8443`.
- **Windows**: запуск от администратора (UAC) либо `--port 8443`.

### Перерегистрация OAuth redirect_uri

Смена дефолта `MCP_BASE_URL` с `http://localhost:8000` на `https://localhost` меняет `redirect_uri`, который регистрируется на TrueConf Server при OAuth-настройке. Существующие регистрации нужно обновить. Проект не релизнут — миграции нет.

**Переименование `/login/callback` → `/auth/callback`** также меняет `redirect_uri` (теперь `.../auth/callback`). Для **обоих** auth-режимов (`oauth` и `token`) существующие регистрации на TrueConf Server нужно обновить — старый путь `/login/callback` больше не обслуживается.

## Архитектура

```
main.py                    # Typer CLI (единственная команда serve, схлопнута в корень,
                           # DiscoveryMode), run_server(config),
                           # _serve() (mcp.run_http_async + cleanup_task), import-time side effects
                           # (load_dotenv, logging.basicConfig, init_i18n, регистрация
                           # tools/prompts/routes через side-effect imports)
app/
    __init__.py            # маркер пакета
    _version.py            # версия (генерируется setuptools-scm)
    config.py              # Config dataclass + build_config()/get_config()/set_config() —
                           # единый источник конфигурации; константа TRUECONF_API_VERSION
    tls.py                 # TLS: extract_san_names, generate/ensure_self_signed_cert,
                           # resolve_tls_files(config), bind_error_help(port)
    _client_api/           # слой 1: upstream API клиенты (без MCP-зависимостей, приватный пакет)
        __init__.py        # маркер пакета + описание структуры
        _trueconf_server/  # чистый домен TrueConf Server API (v4/v4.1 REST)
            __init__.py    # маркер пакета
            models.py      # Pydantic-модели из OpenAPI schemas
            mode_utils.py  # _resolve_mode()/_resolve_access()/build_guest_rights()
                           # + _MODE_MAP / _ACCESS_MAP
        _trueconf_server_ai/  # чистый домен TrueConf AI Server user API
            __init__.py    # маркер пакета
            models.py      # Pydantic-модели: AiTokenPair, фильтры списков
            client.py      # HTTP-клиент AI Server: auth/from-tcs, auth/refresh,
                           # transcriptions (+lines, summary); AiApiError
    mcp/                   # слой 2: MCP-инфра (зависит от _client_api + fastmcp)
        __init__.py        # mcp (FastMCP), _request(), _request_file() (бинарные ответы),
                           # init_http_client()/close_http_client()/get_http_client(),
                           # _token_store + get_token_store()/set_token_store() — общие утилиты
        auth/              # auth/access glue к апстримам (слой 2)
            __init__.py    # фасад: re-export публичного API обоих модулей
            trueconf_server.py   # ApiTokenAuth — наш UUID → TrueConf токен + авто-refresh,
                           # create_oauth_auth() — OAuthProxy с DCR (dead code, disabled),
                           # init_auth(config, token_store) — всегда ApiTokenAuth (OAuth path disabled)
            trueconf_server_ai.py  # AI Server glue: адрес из конфига (--ai-server-url /
                           # AI_SERVER_URL), без GET /servers-ai (нужны admin-права),
                           # from-tcs exchange (domain = --server, fallback https://),
                           # in-memory кэш JWT-пар по sha256(tc-токена), sai_request()
                           # (refresh-on-401 → ре-exchange → ai_token_invalid)
        token_store.py     # TokenStore — зашифрованное файловое хранилище токенов,
                           # init_token_store(config) — фабрика (derive keys + FileTreeStore + Fernet),
                           # periodic_cleanup() — часовая фоновая задача (вызывает cleanup_expired)
        instructions.py    # STATIC/BM25/CODE_MODE_INSTRUCTIONS — per-mode server instructions,
                           # apply_discovery_mode(config) — выбор transform + mcp.instructions
        code_mode.py       # CodeMode: guide + create_code_mode_transform()
        pages.py           # HTML-страницы (login/success/error) + путь к templates/
        prompts.py         # MCP-prompts (conference_help) — side-effect регистрация через import
        i18n.py            # i18nice: yml-локали ru/en, detect_lang() (?lang → cookie → Accept-Language)
        errors.py          # make_error() — единообразные error-dict для инструментов
        logging_utils.py   # mask_token()
        routes.py          # HTTP UI-роуты (/, /success, /error, /&state=null, /auth/callback,
                           # /api/health, /static/app.css, /static/app.js, /favicon.ico, /logo.png)
                           # + _cors() (Origin-allowlist) + register_login_callback() — всегда
         tools/
            __init__.py    # агрегатор: импорт trueconf_server + trueconf_server_ai
                           # → триггер @mcp.tool регистрации
            trueconf_server/   # инструменты против TrueConf Server (v4/v4.1)
                __init__.py    # импорт доменов → регистрация
                conferences/   # 30 MCP-инструментов, один файл на инструмент
                    __init__.py # импорт всех 30 модулей → триггер @mcp.tool регистрации
                    # Core CRUD
                    list_conferences.py
                    get_conference.py
                    create_conference.py
                    update_conference.py
                    delete_conference.py
                    # Lifecycle
                    run_conference.py
                    stop_conference.py
                    join_conference.py
                    # Invitations
                    list_invitations.py
                    add_invitation.py
                    remove_invitation.py
                    get_invitation.py
                    update_invitation.py
                    invite_participants.py
                    # Participants & Roles
                    get_conference_participants.py
                    get_conference_owner.py
                    get_conference_me.py
                    # Recordings
                    list_recordings.py
                    get_recording.py
                    start_recording.py
                    stop_recording.py
                    pause_recording.py
                    # Links & Calendar
                    get_deeplinks.py
                    get_shared_links.py
                    get_conference_ics.py
                    get_conference_calendars.py
                    # Notifications & Registration
                    notify_conference.py
                    register_for_conference.py
                    # Translations
                    get_conference_translations.py
                    # Admin
                    calculate_conferences.py
                    schedule_utils.py  # хелпер без @mcp.tool: schedule/guest_rights
                users/         # 1 MCP-инструмент
                    __init__.py # импорт модулей → триггер @mcp.tool регистрации
                    get_user_addressbook.py  # только API v4.1 (TrueConf Server ≥ 5.5.6)
            trueconf_server_ai/   # инструменты против TrueConf AI Server
                __init__.py       # импорт доменов → регистрация
                transcriptions/   # 4 MCP-инструмента против TrueConf AI Server
                    __init__.py           # импорт модулей → триггер @mcp.tool регистрации
                    list_transcriptions.py
                    get_transcription.py
                    get_transcription_lines.py
                    get_transcription_summary.py
            # (масштабируется: trueconf_server/summaries/ и т.д.)
    web/                   # веб-ассеты и шаблоны (раньше были в корне как static/ + templates/)
        assets/            # favicon.ico, logo.png
        static/
            app.css        # Общий chrome (topbar, footer, lang-switch, status-badge) — login/success/error
            app.js         # Language switcher dropdown + TrueConf Server health check
        locales/           # i18nice yml: common/login/success/error × ru/en
        templates/
            login.html     # Полная страница входа (shared topbar + two-column main + footer)
            success.html   # Полная страница после авторизации (токен + конфиги MCP-клиентов)
            error.html     # Полная страница ошибки OAuth (красный акцент, retry-карточка)
```

## Критично: Токен-флоу

Цепочка авторизации — самая важная концепция в проекте:

**Режим `oauth` (отключён):** OAuthProxy + DCR путь оставлен как dead code (`create_oauth_auth` / `_TrueConfTokenVerifier` в `app/mcp/auth/trueconf_server.py`). `init_auth` всегда возвращает `ApiTokenAuth`. Причина отключения: `_TrueConfTokenVerifier.verify_token` принимал ЛЮБУЮ строку как валидный токен — полный обход авторизации. Re-enable только после реализации настоящей валидации opaque-токенов против TrueConf Server.

**Режим `token` (единственный активный):**
1. Пользователь заходит на `/` → OAuth2 редирект на TrueConf Server
2. `/auth/callback` обменивает code на TrueConf tokens, создаёт наш длинный токен, редиректит на `/success` (токен доставляется через `mcp_token` httpOnly cookie, не через query param)
3. Наш токен хранится зашифрованно в `~/Library/Application Support/fastmcp/oauth-proxy/<fingerprint>/mcp-api-tokens/`
4. MCP-клиент шлёт `Authorization: Bearer <our_token>`:
   - `ApiTokenAuth.verify_token()` ищет наш токен в TokenStore
   - Если TrueConf токен протух — прозрачный refresh
   - Возвращает `AccessToken(token=<TrueConf_token>)` — `.token` это TrueConf токен, не наш UUID
5. Инструменты вызывают `get_access_token()` → `.token` = TrueConf токен, `.client_id` = user_id
6. `_call_trueconf()` использует общий httpx-клиент (`init_http_client()`), добавляет `Authorization: Bearer <TrueConf_token>` в headers per-request

**Не путайте наш UUID-токен с TrueConf access_token.** `ApiTokenAuth` делает маппинг.

**CORS для cookie-флоу.** TrueConf Server выполняет `/oauth2/authorize` через `fetch()` из JS — `/auth/callback` приходит как **credentialed cross-site CORS request**. Для таких запросов браузер требует: (1) `Access-Control-Allow-Origin` = конкретный Origin (не `*`), (2) `Access-Control-Allow-Credentials: true`. Без обоих браузер блокирует ответ и **дропает `Set-Cookie`** → `/success` не видит cookie → login loop. `_cors()` в `routes.py` ставит `Access-Control-Allow-Origin` = Origin **только если Origin входит в allowlist** (base URL TrueConf Server или `MCP_BASE_URL`), + `Allow-Credentials: true` + `Vary: Origin`; без Origin — `*`. `SameSite=None` + `Secure` на cookie необходимы, но **недостаточны** без правильных CORS headers.

**Неаутентифицированные запросы (pass-through).** `RequireAuthMiddleware` пропатчен (`_patch_auth_middleware_optional` в `app/mcp/auth/trueconf_server.py`) так, что запросы без Bearer-токена проходят через middleware к MCP-обработчику. Инструменты сами проверяют `get_access_token()` через `_request` и, если токена нет, возвращают `{"error": "authorization_required", "login_url": ..., "message": ..., "how_to": ...}` dict — LLM объясняет юзеру как авторизоваться. Жёсткий 401-ответ с JSON-инструкциями **никогда не срабатывает** в обоих auth-режимах (token и oauth). Pass-through патч обязателен для code_mode/bm25 — иначе `initialize` падает на 401 и discovery недоступен.

## Критично: Семантика update_conference (partial update)

`update_conference` — это merge: поля, которые не переданы, не попадают в тело PATCH (`exclude_none`) и не меняются. Сервер при PATCH расписания требует **полный** набор полей для типа (`once` — start_time, time, special_time_offset, duration; `week` — плюс непустой days), неполный → 500. Поэтому два случая требуют текущего состояния конференции — **один общий `GET /conferences/{id}`** (делается только если сработал хотя бы один случай; полный запрос GET не делает):

1. **`guest_rights` без `access`.** Явный `access != "public"` → немедленный `guest_rights_requires_public_access` (без сети). Если `access` не передан (включая непонятную строку — `_resolve_access` → `None`, опечатка ведёт себя как omission) → GET и проверка текущего `access`: `public` → PATCH с `rights` (без `access` в теле); `private` → та же ошибка, но с фактическим текущим access в сообщении. PATCH с `rights` на private **не улетает**: поведение сервера задокументировано негде, а молча принять права, где гостей нет, — ложь о результате.
2. **Частичное расписание** (`once`/`week`, не хватает `duration`/`time`/`days`/`date`/`timezone`) — недостающее наследуется из текущего расписания: `duration`/`days`/`special_time_offset` как есть (не хватает `timezone` → offset берётся из `special_time_offset`); локальное `time` восстанавливается из `start_time`(UTC) + `special_time_offset` (в **ответе** `ScheduleOutput` поля `time` НЕТ, а `start_time`/`end_time` — строки формата, не зафиксированного в спеке — парсит `parse_schedule_output_time`: unix и ISO); дата первого вхождения сохраняется из `start_time` **+ `special_time_offset`** — это **локальная** дата, а не UTC-дата `start_time` (они различаются, когда локальное время старта пересекает границу UTC-суток). Для `week` время повторения берётся из time-of-day якоря (TrueConf хранит одну пару time/offset). Расписания нет (`type: none`) → наследовать нечего, стандартные required-field ошибки, PATCH не улетает.

**Правило: явно переданные значения ВСЕГДА переопределяют наследуемые.** Наследование только доединяет недостающее, никогда не перетирает явный ввод (явный `timezone` побеждает наследуемый offset, явный `access` побеждает текущий статус). Это прописано в docstring `update_conference` — не ломать, когда правите merge-логику. Хелперы: `schedule_update_is_partial` / `resolve_partial_schedule` в `schedule_utils.py`.

## Добавление новых инструментов

1. Если нужны новые модели — добавить в `app/_client_api/_trueconf_server/models.py`
2. Создать файл в соответствующем пакете (`app/mcp/tools/trueconf_server/conferences/`, `app/mcp/tools/trueconf_server_ai/transcriptions/` и т.д.)
3. Декоратор `@mcp.tool(tags={"tag1", "tag2"})` — `mcp` импортируется из `app.mcp`
4. API-запросы через `await _request("METHOD", "path", json=..., params=...)` (`_request` — из `app.mcp`)
5. `_request` сам обрабатывает auth, логирование и парсинг ошибок (единые error-dict через `make_error` из `app/mcp/errors.py`). Для бинарных endpoint'ов (ICS, CSV) — `_request_file`: возвращает MCP `File` с size-лимитом (10MB) вместо base64
6. Импорт нового модуля в `__init__.py` пакета (например `app/mcp/tools/trueconf_server/conferences/__init__.py`) автоматически регистрирует инструменты. Не забыть `import app.mcp.tools.trueconf_server` / `import app.mcp.tools.trueconf_server_ai` в `main.py` (или в общем `app/mcp/tools/__init__.py`)

**Именование: файл vs MCP-имя инструмента.**
- **Имя файла = API-запрос**, который инструмент оборачивает: `update_invitation.py` для
  `PATCH /conferences/{id}/invitations/{invitation_id}`, как и соседние
  `list_invitations.py` / `add_invitation.py` / `remove_invitation.py` / `get_invitation.py`.
- **Функция внутри называется так же, как файл** (`update_invitation`).
- **MCP-имя инструмента** (его видит LLM, по нему работает `search_tools`) задаётся через
  параметр `name` декоратора, если оно должно отличаться от файла/функции:
  ```python
  @mcp.tool(name="update_conference_guest_display_name", tags={"invitations", "write"})
  async def update_invitation(conference_id, invitation_id, display_name) -> dict:
      ...
  ```
  Зачем: MCP-имя — это промпт для LLM. Оно должно отражать **реальную семантику** (кого можно
  переименовать через этот endpoint), а не общее название запроса. Пример: `PATCH invitations`
  меняет `display_name` только для гостей, поэтому MCP-имя `update_conference_guest_display_name`,
  а не `update_invitation` — иначе LLM пытается «переименовать» зарегистрированных пользователей.
  В `instructions.py` (примеры для `search_tools`) указывать MCP-имя, а не имя файла.

**Версии API.** База по умолчанию — `/api/v4` (`TRUECONF_API_VERSION` в `app/config.py`). Для endpoint'ов, доступных только в v4.1 (TrueConf Server ≥ 5.5.6), передавай `version="v4.1"` в `_request` — он соберёт абсолютный URL. Если v4.1-запрос вернул HTTP 404, `_request` возвращает `endpoint_not_supported` dict (LLM объясняет пользователю, что сервер нужно обновить до 5.5.6+). Пример: `get_user_addressbook`.

`mcp.instructions` (server-level контекст для MCP-клиента) задаётся в `apply_discovery_mode()` (`app/mcp/instructions.py`) per-режим (`STATIC_INSTRUCTIONS` / `BM25_INSTRUCTIONS` / `CODE_MODE_INSTRUCTIONS`). Вызывается из `run_server()` в `main.py`. При изменении домена (новые типы объектов) обновлять все три константы.

## Деплой

- По умолчанию сервер сам терминирует TLS на 443 с self-signed сертификатом (см. раздел [TLS](#tls))
- Caddy — опционально, для валидных сертификатов (Let's Encrypt); проксирует на `localhost:443` (или `--port 8443` при коллизии). Caddyfile в репо не коммитится
- Альтернатива: ngrok (`ngrok http 443`) — туннелирует HTTPS с валидным сертификатом
- Путь хранения токенов зависит от `TRUECONF_SECRET` — смена = все токены станут нечитаемыми
- Фоновая задача `periodic_cleanup()` стартует с одного sweep при запуске, затем каждые час чистит: наши токены, достигшие `api_token_ttl`, TrueConf-токены без refresh_token и просроченные >7 дней (grace period)
- **⚠️ Single-worker only:** `asyncio.Lock` в `TokenStore._index_lock` сериализует только в одном процессе. Multi-worker деплой (uvicorn `--workers N`) с общим filesystem — гонки на индексе (read-modify-write → потерянные токены, двойные удаления). Запускать с одним worker.

## Подключение MCP-клиентов (LM Studio, Cursor и т.д.)

### MCP_BASE_URL — критически важно

`MCP_BASE_URL` определяет URL-адреса в OAuth metadata (`/.well-known/oauth-authorization-server`).
MCP-клиент получает эти URL и обращается к ним при DCR и OAuth flow.

**Правило:** `MCP_BASE_URL` должен быть тем URL, по которому клиент может достучаться до сервера извне.

| Сценарий | `MCP_BASE_URL` |
|----------|----------------|
| Локальный (только localhost) | `https://localhost` (дефолт, порт 443 опущен) |
| LAN (другие устройства в сети) | `https://<LAN-IP>` (порт 443 опущен) |
| Через Caddy | `https://<domain-or-ip>` |
| Через ngrok | `https://<ngrok-url>` |

**Частая ошибка:** `MCP_BASE_URL=https://127.0.0.1` — metadata возвращает `127.0.0.1`, клиент не может достучаться → 401 → "Plugin process exited".

### CIMD (Client ID Metadata Document)

FastMCP OAuthProxy по умолчанию включает CIMD (`enable_cimd=True`). В metadata появляется `client_id_metadata_document_supported: true`.

**Проблема:** LM Studio интерпретирует это как "сервер поддерживает только CIMD, а не стандартный DCR" → показывает "This server does not support Dynamic Client Registration".

**Решение:** Отключить CIMD в `create_oauth_auth()` (`app/mcp/auth/trueconf_server.py`):
```python
auth = OAuthProxy(
    ...,
    enable_cimd=False,
)
```

### LM Studio + OAuth

LM Studio (начиная с 0.3.17) поддерживает MCP-серверы через `mcp.json`. Поддерживает DCR (Dynamic Client Registration) для OAuth flow. **Не поддерживает CIMD.**

Пример конфигурации в LM Studio:
```json
{
  "mcpServers": {
    "trueconf": {
      "url": "https://<MCP_BASE_URL>/mcp"
    }
  }
}
```

### Caddy + Node.js (LM Studio)

Node.js (используется внутри LM Studio) **не доверяет самоподписанным сертификатам** — ни Caddy, ни нашему авто-сгенерированному self-signed из раздела [TLS](#tls). Не использует macOS Keychain.

Caddy пишет `root certificate is already trusted by system`, но Node.js это игнорирует. `NODE_EXTRA_CA_CERTS` не помогает — LM Studio не прокидывает эту переменную в свой Node.js процесс.

**Решения:**
- **ngrok** — туннелирует HTTPS с валидным сертификатом (free tier: URL меняется при каждом перезапуске)
- **Домен + Let's Encrypt** — Caddy автоматически получит валидный сертификат

### NODE_TLS_REJECT_UNAUTHORIZED workaround (self-signed cert)

Если LM Studio вылетает с ошибкой:

> TypeError: fetch failed: self-signed certificate; if the root CA is installed locally, try running Node.js with --use-system-ca

Запустите LM Studio с отключённой валидацией TLS-сертификатов:

**macOS:**
```bash
NODE_TLS_REJECT_UNAUTHORIZED=0 open "/Applications/LM Studio.app"
```

**Windows (CMD):**
```cmd
set NODE_TLS_REJECT_UNAUTHORIZED=0
start "" "C:\Program Files\LM Studio\LM Studio.exe"
```

**Linux:**
```bash
NODE_TLS_REJECT_UNAUTHORIZED=0 lm-studio
```

**Важно:**
- Env var действует только для текущей сессии — перезапуск из Dock/Start Menu/Spotlight требует повторного запуска из терминала
- Отключает валидацию сертификатов для ВСЕХ HTTPS-запросов Node.js в процессе LM Studio — только для локальной разработки
- Проверено: работает с auth mode `token`

## Известные проблемы

- **Схема-less AI URL молча резолвилась против base_url TrueConf Server.** Если `AI_SERVER_URL`/`--ai-server-url` задан без `http(s)://` и нормализация схемы не применяется, httpx подставляет относительный URL в `base_url` общего клиента (`https://<TCS>/api/v4` + путь) → 404 `routeNotFound` в формате ошибок TCS (trace_id), а не AI Server. Защита: `resolve_sai_base()` всегда добавляет `https://` (явный `http://` сохраняется) + гвард в `ai_client._request` (URL без схемы → `ValueError`, запрос не уходит в сеть) + маппинг TCS-404 → `ai_server_wrong_host` (диагностика: «запрос ушёл в TrueConf Server, проверьте AI_SERVER_URL»), гвард-`ValueError` → `ai_server_url_invalid`
- `download_recording` удалён — грузил весь видеофайл в base64 (memory bomb), LLM не мог осмысленно использовать видео-блоб в MCP-контексте. Скачивание записей — через `download_url` из `get_recording`/`list_recordings`
- LM Studio не поддерживает CIMD — если в metadata есть `client_id_metadata_document_supported: true`, LM Studio показывает "DCR not supported". Решение: `enable_cimd=False` в OAuthProxy
- `MCP_BASE_URL` с `127.0.0.1` не работает для удалённых клиентов — metadata возвращает localhost URL
- Node.js (LM Studio) не доверяет самоподписанным сертификатам — ни Caddy, ни авто-сгенерированному из [TLS](#tls). Workaround: `NODE_TLS_REJECT_UNAUTHORIZED=0` при запуске LM Studio (см. раздел выше). Для production — ngrok или Let's Encrypt.
- ~~**CORS login loop (fixed).**~~ Исторически `_cors()` в `routes.py` возвращал `Access-Control-Allow-Origin: *` без `Access-Control-Allow-Credentials: true`. Для credentialed cross-site `fetch()` (которым является `/auth/callback` из TrueConf Server JS) браузер блокирует такой ответ и **дропает `Set-Cookie`** → `/success` не видит cookie → login loop. Фикс: `_cors()` разрешает Origin только из allowlist (base URL TrueConf / `MCP_BASE_URL`) + ставит `Allow-Credentials: true` + `Vary: Origin`; без Origin — `*` как и раньше.
- **Login CSRF (session fixation, insider-only).** TrueConf Server не поддерживает `state` и PKCE в OAuth flow, поэтому классическая OAuth state-binding недоступна. Атакующий — легитимный пользователь TrueConf Server — может прогнать `/` flow своими кредами, перехватить `code` до consumed и доставить жертве `https://<mcp>/auth/callback?code=<attacker_code>` в течение ~60с (TTL кода). В результате MCP-клиент жертвы работает в аккаунте атакующего (видит его конференции, записи, чаты). Это session fixation, не credential theft: creds жертвы не утекают, work product жертвы оседает в аккаунте атакующего. Митигации: `mcp_token` cookie `max_age=60` (держится лишь для 60-секундного ре-рендера `/success` при смене языка), `httponly`, `samesite=none` + `secure` (None обязателен: TrueConf Server выполняет `/oauth2/authorize` через `fetch()` из JS — callback приходит как cross-site cors request, и SameSite=Lax было бы drop'нуто браузером; cookie вообще не сохранялось → /success не видел токен → login loop). Re-confirmation step (страница «Вы авторизуетесь как X. Подтвердить?» + POST с CSRF-токеном) отклонён по cost/benefit — friction на каждый легитимный логин ради узкого insider-сценария. Остаточный риск принят.
