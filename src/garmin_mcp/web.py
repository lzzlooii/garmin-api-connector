"""单账号个人 API 管理页面与经过认证的 MCP 入口。没有 Garmin 密码登录。"""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import re
import secrets
import time
import ipaddress
from urllib.parse import urlsplit
from typing import Any

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.transport_security import TransportSecuritySettings

from . import client as store
from . import official
from .server import mcp, reset_client

log = logging.getLogger("garmin-mcp.web")


# 对本进程的常见认证格式脱敏；不保证外部代理、平台或异常堆栈的日志。
_REDACT = re.compile(r"(/k/)[^/\s'\"]+|((?:Bearer|ApiKey)\s+)[^\s'\"]+", re.IGNORECASE)
_make_record = logging.getLogRecordFactory()


def _redacting_record(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _make_record(*args, **kwargs)
    try:
        msg = record.getMessage()
    except Exception:  # noqa: BLE001
        return record
    clean = _REDACT.sub(lambda m: (m.group(1) or m.group(2)) + "***", msg)
    if clean != msg:
        record.msg, record.args = clean, None
    return record


logging.setLogRecordFactory(_redacting_record)

COOKIE = "gm_admin"
SESSION_DAYS = 7
MAX_FAILS, LOCK_SECONDS = 5, 15 * 60


# ═══════════════════════════ 1. MCP 接口 + 密钥检查 ═══════════════════════════

# 设置页面已经有密钥保护，这里关掉 SDK 自带的"只允许 localhost"检查，否则云端访问会被拒。
_open = TransportSecuritySettings(enable_dns_rebinding_protection=False)

# stateless：每个请求独立处理，不依赖会话，最适合云平台（重启、多实例都不怕）。
mcp_http = mcp.streamable_http_app(
    streamable_http_path="/mcp", stateless_http=True, json_response=True,
    transport_security=_open, host="127.0.0.1",
)
mcp_sse = mcp.sse_app(sse_path="/sse", message_path="/messages/", transport_security=_open, host="127.0.0.1")

MCP_PATHS = ("/mcp", "/sse", "/messages")


def _secret_ok(given: str | None) -> bool:
    return bool(given) and hmac.compare_digest(given.encode(), store.load_config()["secret"].encode())


async def _unauthorized(send: Send) -> None:
    await Response("Unauthorized", status_code=401)({"type": "http"}, None, send)  # type: ignore[arg-type]


class Gateway:
    """最外层的"门卫"：判断请求是给 AI 的 MCP 接口，还是给人看的设置页面。"""

    def __init__(self, pages: ASGIApp) -> None:
        self.pages = pages

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            # streamable HTTP 需要在启动时初始化它的会话管理器
            await mcp_http(scope, receive, send)
            return
        if scope["type"] != "http":
            return

        path: str = scope["path"]
        # Health probes reveal no credentials and may be plain HTTP behind TLS ingress.
        if path != "/healthz":
            host = dict(scope.get("headers", [])).get(b"host", b"").decode("latin-1")
            if not _allowed_host(host):
                await Response("Invalid host", 400)(scope, receive, send)
                return
            address = (scope.get("client") or ("", 0))[0]
            try:
                local = ipaddress.ip_address(address).is_loopback
            except ValueError:
                local = False
            if scope.get("scheme") != "https" and not local:
                await Response("HTTPS required", 400)(scope, receive, send)
                return

        # 方式一：/k/<密钥>/mcp —— 密钥在地址里
        if path.startswith("/k/"):
            if os.getenv("ALLOW_URL_SECRET") != "1":
                await _unauthorized(send)
                return
            parts = path.split("/", 3)  # ["", "k", "<secret>", "rest"]
            secret = parts[2] if len(parts) > 2 else ""
            rest = "/" + (parts[3] if len(parts) > 3 else "")
            if not _secret_ok(secret) or not _mcp_path(rest):
                await _unauthorized(send)
                return
            prefix = f"/k/{secret}"
            # 去掉前缀再交给 MCP；root_path 让 SSE 告诉客户端带前缀的消息地址
            scope = dict(scope, path=rest, raw_path=rest.encode(), root_path=prefix)
            await self._mcp(scope, receive, send)
            return

        # 方式二：/mcp + Authorization: Bearer <密钥>
        if _mcp_path(path):
            auth = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
            if not _secret_ok(token):
                await _unauthorized(send)
                return
            await self._mcp(scope, receive, send)
            return

        await self.pages(scope, receive, send)

    async def _mcp(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = mcp_http if scope["path"].startswith("/mcp") else mcp_sse
        await app(scope, receive, send)


# ═══════════════════════════ 2. 管理员登录 ═══════════════════════════


def _mcp_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in MCP_PATHS)


def _allowed_host(value: str) -> bool:
    try:
        host = urlsplit("//" + value).hostname
    except ValueError:
        return False
    allowed = {"localhost", "127.0.0.1", "::1"}
    public = urlsplit(os.getenv("PUBLIC_URL", ""))
    if public.scheme == "https" and public.hostname:
        allowed.add(public.hostname.lower())
    allowed.update(x.strip().lower() for x in os.getenv("ALLOWED_HOSTS", "").split(",") if x.strip())
    return bool(host) and host.lower() in allowed


def _admin_password() -> str | None:
    pw = os.getenv("ADMIN_PASSWORD", "")
    return pw if len(pw) >= 12 and pw not in {"请改成你自己的长密码", "请设置独立的长管理员密码"} else None


def _sign(expiry: int) -> str:
    cfg = store.load_config()
    # 把管理员密码也算进签名：改了密码，所有已登录的设备自动退出
    key = hashlib.sha256((cfg["session_key"] + (_admin_password() or "")).encode()).digest()
    mac = hmac.new(key, str(expiry).encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{mac}"


def _is_admin(request: Request) -> bool:
    raw = request.cookies.get(COOKIE, "")
    try:
        expiry = int(raw.split(".", 1)[0])
    except ValueError:
        return False
    return expiry > time.time() and hmac.compare_digest(raw, _sign(expiry))


_fails: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _locked(ip: str) -> bool:
    now = time.time()
    _fails[ip] = [t for t in _fails.get(ip, []) if now - t < LOCK_SECONDS]
    return len(_fails[ip]) >= MAX_FAILS


def _same_origin(request: Request) -> bool:
    """POST 请求必须来自本站页面，防止别的网站冒用你的登录状态（CSRF）。

    现代浏览器都会带 Sec-Fetch-Site，直接告诉我们请求是不是本站发起的；
    老浏览器退回到比较 Origin。Cookie 本身也设了 SameSite=Strict，双保险。
    """
    if request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
        return False
    origin = request.headers.get("origin")
    if not origin or origin == "null":
        return False
    expected = urlsplit(_base_url(request))
    actual = urlsplit(origin)
    return actual.scheme == expected.scheme and actual.netloc == expected.netloc


def _base_url(request: Request) -> str:
    return os.getenv("PUBLIC_URL", "").rstrip("/") or f"{request.url.scheme}://{request.url.netloc}"


# ═══════════════════════════ 3. 页面 ═══════════════════════════

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--mute:#667085;--line:#e4e7ec;--acc:#0b6bcb;--ok:#13795b;--bad:#c4320a;--code:#f1f3f6}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1b1e23;--fg:#e8eaed;--mute:#9aa1ad;--line:#2b2f36;--acc:#5aa9ff;--ok:#3ccf91;--bad:#ff7a59;--code:#24282f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
main{max-width:560px;margin:0 auto;padding:20px 16px 48px}h1{font-size:22px;margin:8px 0 4px}h2{font-size:17px;margin:0 0 8px}
.sub{color:var(--mute);margin:0 0 20px;font-size:14px}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:0 0 14px}
label{display:block;font-size:14px;color:var(--mute);margin:12px 0 4px}input[type=text],input[type=email],input[type=password],textarea{width:100%;padding:12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--fg);font-size:16px}
textarea{min-height:90px;font-family:ui-monospace,monospace;font-size:13px}
button,.btn{display:inline-block;border:0;border-radius:10px;padding:12px 16px;font-size:16px;background:var(--acc);color:#fff;cursor:pointer;text-decoration:none;margin-top:14px}
button.ghost{background:transparent;color:var(--acc);border:1px solid var(--line)}button.danger{background:transparent;color:var(--bad);border:1px solid var(--line)}
.wide{width:100%}.row{display:flex;gap:8px;flex-wrap:wrap}.radio{display:flex;gap:10px;margin-top:6px}.radio label{flex:1;margin:0;padding:12px;border:1px solid var(--line);border-radius:10px;color:var(--fg);text-align:center}
.radio input{margin-right:6px}.code{background:var(--code);border-radius:8px;padding:10px;font:13px/1.5 ui-monospace,monospace;word-break:break-all;margin:6px 0}
.copy{margin:0;padding:8px 12px;font-size:14px}.ok{color:var(--ok)}.bad{color:var(--bad)}.mute{color:var(--mute);font-size:14px}
details{margin-top:10px}summary{cursor:pointer;color:var(--acc)}ol{padding-left:20px;margin:8px 0}li{margin:4px 0}
"""

JS = """
document.querySelectorAll('[data-copy]').forEach(b=>b.onclick=async()=>{
 const t=document.getElementById(b.dataset.copy).innerText;
 try{await navigator.clipboard.writeText(t);b.innerText='已复制 ✓'}catch(e){b.innerText='请长按上面文字复制'}
 setTimeout(()=>b.innerText='复制',2000)});
document.querySelectorAll('form[data-confirm]').forEach(f=>f.onsubmit=()=>confirm(f.dataset.confirm));
"""


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><main>{body}</main><script>{JS}</script></body></html>"""
    return HTMLResponse(doc, status_code=status)


def _e(s: Any) -> str:
    return html.escape(str(s or ""))


def _copy_block(id_: str, text: str) -> str:
    return (f'<div class="code" id="{id_}">{_e(text)}</div>'
            f'<button class="ghost copy" type="button" data-copy="{id_}">复制</button>')


async def home(request: Request) -> Response:
    if not _admin_password():
        return _page("需要设置管理员密码", """<h1>还差一步</h1><div class="card">
<p>请在部署平台的<b>环境变量</b>里添加 <code>ADMIN_PASSWORD</code>（至少 12 位），然后重启服务。</p>
<p class="mute">这个密码用来保护本设置页面，只有你知道。</p></div>""")
    if not _is_admin(request):
        return _login_page()
    return _dashboard(request)


def _login_page(error: str = "") -> Response:
    err = f'<p class="bad">{_e(error)}</p>' if error else ""
    return _page("登录", f"""<h1>佳明 AI 连接器</h1><p class="sub">输入管理员密码进入设置</p>
<form class="card" method="post" action="/login">{err}
<label>管理员密码</label><input type="password" name="password" autocomplete="current-password" required autofocus>
<button class="wide">进入</button></form>""", 401 if error else 200)


async def login(request: Request) -> Response:
    ip = _client_ip(request)
    if not _same_origin(request):
        return Response("Forbidden", 403)
    if _locked(ip):
        return _login_page("尝试次数过多，请 15 分钟后再试")
    form = await request.form()
    expected = _admin_password() or ""
    if not expected or not hmac.compare_digest(str(form.get("password", "")).encode(), expected.encode()):
        _fails.setdefault(ip, []).append(time.time())
        log.warning("管理员登录失败（来源 %s）", ip)
        return _login_page("密码不对")
    _fails.pop(ip, None)
    resp = RedirectResponse("/", 303)
    expiry = int(time.time()) + SESSION_DAYS * 86400
    resp.set_cookie(COOKIE, _sign(expiry), max_age=SESSION_DAYS * 86400, httponly=True,
                    secure=request.url.scheme == "https", samesite="strict")
    return resp


async def logout(request: Request) -> Response:
    if not _is_admin(request) or not _same_origin(request):
        return Response("Forbidden",403)
    store.save_config(session_key=secrets.token_hex(32))
    resp = RedirectResponse("/", 303)
    resp.delete_cookie(COOKIE)
    return resp


def _dashboard(request: Request, notice: str = "", error: str = "") -> Response:
    key=official.get_key()
    effective=store.get_region()
    region_fixed=bool(os.getenv("GARMIN_REGION"))
    alerts=f'<p class="ok">{_e(notice)}</p><p class="bad">{_e(error)}</p>'
    region_ui=(f'<p>区域由环境变量固定：{_e(store.REGION_NAMES[effective])}</p><input type="hidden" name="region" value="{effective}">' if region_fixed else '<label>区域</label><select name="region"><option value="cn" '+('selected' if effective=='cn' else '')+'>中国区</option><option value="global" '+('selected' if effective=='global' else '')+'>国际区</option></select>')
    status=('已配置密钥（不代表当前验证有效） '+official.mask(key)) if key else '未配置密钥'
    form=('<p>密钥由环境变量管理，替换时修改 GARMIN_PERSONAL_API_KEY。</p>' if official.key_source()=='env' else f'<form method="post" action="/official">{region_ui}<label>个人 API 密钥</label><input type="password" name="key" autocomplete="off" required><button>保存并验证</button></form><form method="post" action="/official/delete"><button class="danger">删除本机保存的密钥</button></form>')
    secret=store.load_config()['secret']
    base=_base_url(request)
    return _page('Garmin 个人 API 设置', f'<h1>Garmin 个人 API 设置</h1>{alerts}<div class="card"><p>{_e(status)}</p><p>密钥只显示一次，请立即复制并安全保存。遗失后需在佳明设置撤销旧密钥、创建新密钥，再更新这里。删除聊天或本机文件不会撤销佳明密钥。</p>{form}<form method="post" action="/test"><button>验证一次官方资料查询</button></form></div><div class="card"><h2>MCP 连接</h2><p>优先使用地址和 Authorization 请求头。</p>{_copy_block("server",base+"/mcp")}{_copy_block("authorization","Bearer "+secret)}<details><summary>兼容连接地址（含访问凭证）</summary><p>默认关闭此方式。仅确有兼容需要时设置 ALLOW_URL_SECRET=1；网址可能被历史记录或代理保存。</p></details><form method="post" action="/secret/reset"><button>重置 MCP 访问凭证</button></form></div><form method="post" action="/logout"><button>退出设置</button></form>')


def _region(value: Any) -> str:
    fixed=os.getenv("GARMIN_REGION")
    if fixed:
        return store.get_region()
    return value if value in store.REGIONS else "cn"

async def secret_reset(request: Request) -> Response:
    if not _is_admin(request) or not _same_origin(request):
        return RedirectResponse("/",303)
    store.save_config(secret=store.new_secret())
    return _dashboard(request,"MCP 访问凭证已重置，旧连接需更新。")

async def test_read(request: Request) -> Response:
    if not _is_admin(request) or not _same_origin(request):return Response("Forbidden",403)
    key=official.get_key()
    if not key:return _dashboard(request,error="未配置密钥。")
    try:
        await run_in_threadpool(official.verify,key)
    except official.OfficialError as e:return _dashboard(request,error=str(e))
    return _dashboard(request,notice="本次官方资料查询成功；密钥后续仍可能到期或被撤销。")


# ───────── 官方 API 密钥 ─────────


async def official_save(request: Request) -> Response:
    if not _is_admin(request) or not _same_origin(request):
        return RedirectResponse("/", 303)
    form = await request.form()
    key = str(form.get("key", "")).strip()
    region = _region(form.get("region"))
    if len(key) < 16 or any(ch.isspace() for ch in key):
        return _dashboard(request, error="密钥格式不对，请完整复制佳明页面上显示的密钥。")
    try:
        await run_in_threadpool(official.verify, key, region)
    except official.OfficialError as e:
        return _dashboard(request, error=f"验证失败：{e}")
    if official.key_source() == "env":
        return _dashboard(request,error="密钥由环境变量管理，请在部署配置中修改。")
    official.save_key(key)
    store.save_config(region=region)
    reset_client()
    log.info("官方 API 密钥已保存（%s）", region)
    return _dashboard(request, "✓ 官方 API 连接成功！下面把连接信息填进 AI App 就可以用了。")


async def official_delete(request: Request) -> Response:
    if not _is_admin(request) or not _same_origin(request):
        return RedirectResponse("/", 303)
    if official.key_source() == "env":
        return _dashboard(request,error="密钥由环境变量管理，请先从部署配置删除。")
    official.delete_key()
    reset_client()
    return _dashboard(request, "已删除 API 密钥。如果不再使用，建议也到佳明设置里删除这个密钥。")


async def health(_: Request) -> Response:
    return JSONResponse({"ok": True})


async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"  # 页面上有密钥，不能通过 Referer 泄露给其他网站
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; connect-src 'self'"
    if request.url.scheme == "https":
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    return resp


pages = Starlette(routes=[
    Route("/", home),
    Route("/login", login, methods=["POST"]),
    Route("/logout", logout, methods=["POST"]),
    Route("/official", official_save, methods=["POST"]),
    Route("/official/delete", official_delete, methods=["POST"]),
    Route("/secret/reset", secret_reset, methods=["POST"]),
    Route("/test", test_read, methods=["POST"]),
    Route("/healthz", health),
])
pages.add_middleware(BaseHTTPMiddleware, dispatch=security_headers)

app = Gateway(pages)


def main() -> None:
    import uvicorn  # noqa: PLC0415

    public = urlsplit(os.getenv("PUBLIC_URL", ""))
    if public.netloc and (public.scheme != "https" or public.username or public.password):
        raise RuntimeError("PUBLIC_URL 必须是 HTTPS 地址，不可包含凭证")
    if os.getenv("TRUSTED_PROXY_IPS") == "*":
        raise RuntimeError("请列出可信代理 IP，不允许信任所有来源")
    store.load_config()  # 第一次启动时生成密钥
    if not _admin_password():
        log.warning("没有设置 ADMIN_PASSWORD（至少 12 位），设置页面将无法登录")
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,  # 云平台在前面加了 HTTPS 代理，用它传来的真实协议和地址
        forwarded_allow_ips=os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1"),
        access_log=False,  # 访问日志会记下带密钥的完整地址，所以关掉
    )


if __name__ == "__main__":
    main()
