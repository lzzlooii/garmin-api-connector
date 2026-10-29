"""佳明官方个人 API（Garmin Connect Personal API）。

用法：在佳明网页版 设置 → 个人 API 密钥 里生成一个密钥。
  国际区：https://connect.garmin.com/app/settings/personalApiToken
  中国区：https://connect.garmin.cn/app/settings/personalApiToken

国际区和中国区是两套独立的服务器，密钥不能混用，区域要选对。

工作方式：
  1. 用密钥换一个 24 小时有效的通行证（bearer token），缓存在数据文件夹里
  2. 用通行证读数据；通行证快过期或被拒绝时，自动用密钥重新换

使用个人密钥读取个人数据；实际使用受 Garmin 个人 API 条款约束。
在佳明设置里删除密钥就立刻失效。缺点是没有训练准备度、训练状态等几项数据。
"""

from __future__ import annotations

import logging
import os
import threading
import json
from urllib.parse import urlsplit
import requests
from pathlib import Path
from typing import Any, Callable

from garmin_personal_api.auth import PersonalApiAuthenticator
from garmin_personal_api.client import GarminPersonalApiClient
from garmin_personal_api.errors import GarminPersonalApiError, HttpError

from . import client as store

log = logging.getLogger("garmin-mcp.official")

KEY_ENV = "GARMIN_PERSONAL_API_KEY"
KEY_PAGES = {
    "global": "https://connect.garmin.com/app/settings/personalApiToken",
    "cn": "https://connect.garmin.cn/app/settings/personalApiToken",
}
KEY_PAGE = KEY_PAGES["global"]  # 兼容旧代码
BASE_URLS = {
    "global": "https://personal.connectapi.garmin.com",
    "cn": "https://personal.connectapi.garmin.cn",
}


def region() -> str:
    """官方 API 用哪个区：环境变量 GARMIN_REGION 优先，其次是设置页面选的，默认国际区。"""
    return store.get_region()


def key_page(r: str | None = None) -> str:
    return KEY_PAGES[r or region()]


def base_url(r: str | None = None) -> str:
    return BASE_URLS[r or region()]

class OfficialError(Exception):
    """给用户看的错误（中文）。"""


def _key_file() -> Path:
    return store.data_dir() / "personal_api_key"


def get_key() -> str | None:
    """环境变量优先（WorkBuddy 云端、电脑本地用），其次是设置页面保存的。"""
    env = os.getenv(KEY_ENV, "").strip()
    if env:
        return env
    f = _key_file()
    if f.exists():
        return store.private_read(f).strip() or None
    return None


def key_source() -> str | None:
    if os.getenv(KEY_ENV, "").strip():
        return "env"
    return "file" if _key_file().exists() else None


def save_key(key: str) -> None:
    f = _key_file()
    store.private_write(f, key.strip())
    _token_cache().unlink(missing_ok=True)


def delete_key() -> None:
    _key_file().unlink(missing_ok=True)
    _token_cache().unlink(missing_ok=True)


def mask(key: str | None) -> str:
    return f"••••{key[-4:]}" if key and len(key) > 8 else "••••"


def _token_cache() -> Path:
    return store.data_dir() / "official_token.json"


class GarminSession(requests.Session):
    """Restrict credential-bearing SDK traffic to the selected Garmin API host."""
    def __init__(self, base: str):
        super().__init__()
        self._allowed = urlsplit(base).netloc

    def request(self, method, url, **kwargs):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != self._allowed
                or parsed.username or parsed.password or method.upper() not in {"GET", "POST"}):
            raise OfficialError("拒绝向非预期地址发送 Garmin 请求")
        kwargs["allow_redirects"] = False
        response = super().request(method, url, **kwargs)
        if 300 <= response.status_code < 400:
            response.close()
            raise OfficialError("Garmin 接口发生跳转，已停止以保护凭证")
        return response


class PrivateAuthenticator(PersonalApiAuthenticator):
    def _read_cached_token(self, fingerprint):
        path = self.bearer_token_cache_file
        if path.exists() or path.is_symlink():
            store.private_read(path)
        return super()._read_cached_token(fingerprint)

    def _write_cached_token(self, fingerprint, token):
        store.private_write(self.bearer_token_cache_file, json.dumps({
            "fingerprint": fingerprint,
            "access_token": token.access_token,
            "expires_at": token.expires_at,
        }))


class OfficialSource:
    """包装佳明官方客户端：自动换通行证、401 自动重试一次，不改变查询数据。"""

    def __init__(self, api_key: str, region_: str | None = None) -> None:
        self._key = api_key
        self._base = base_url(region_).rstrip("/")
        self._auth = PrivateAuthenticator(bearer_token_cache_file=_token_cache(), session=GarminSession(self._base))
        self._auth.base_url = self._base  # 按区域切换国际区 / 中国区服务器
        self._client: GarminPersonalApiClient | None = None
        self._lock = threading.Lock()

    def _get_client(self, force: bool = False) -> GarminPersonalApiClient:
        with self._lock:
            token = self._auth.obtain_token(self._key, force_refresh=force)
            if self._client is None:
                self._client = GarminPersonalApiClient(token.access_token, session=GarminSession(self._base))
                self._client.base_url = self._base
            else:
                self._client.update_bearer_token(token.access_token)
            return self._client

    def call(self, fn: Callable[[GarminPersonalApiClient], Any]) -> Any:
        try:
            try:
                return fn(self._get_client())
            except HttpError as e:
                if e.status_code != 401:
                    raise
                log.info("通行证被拒绝，用密钥重新换一个")
                return fn(self._get_client(force=True))
        except HttpError as e:
            raise OfficialError(_explain(e)) from None
        except GarminPersonalApiError as e:
            raise OfficialError("佳明官方客户端未能处理响应，请检查配置和接口状态。") from None
        except (OSError, requests.RequestException) as e:  # 不返回含请求详情的异常
            raise OfficialError(f"连不上佳明服务器：{type(e).__name__}") from None


def _redact(text: str) -> str:
    """错误信息里可能带着通行证或密钥，截短并去掉看起来像密钥的长串。"""
    import re  # noqa: PLC0415

    return re.sub(r"[A-Za-z0-9_\-\.]{40,}", "***", text)[:200]


def _explain(e: HttpError) -> str:
    code = e.status_code
    if code == 401:
        return (f"佳明 API 密钥无效、已过期，或账号区域选错了（国际区和中国区的密钥不能混用）。"
                f"请检查区域，或到佳明设置里重新生成：{key_page()}")
    if code == 403:
        return "佳明拒绝了这个请求：你的账号可能没有开通这项数据的权限。"
    if code == 404:
        return "佳明官方接口暂时不提供这项数据。"
    if code == 400:
        return "请求参数不对（可能是日期范围太长或日期格式错误）。"
    if code == 429:
        return "佳明限流了（请求太频繁），过几分钟再试。"
    if code >= 500:
        return "佳明服务器暂时出错，稍后再试。"
    return f"佳明官方接口返回错误（HTTP {code}）。"


def verify(api_key: str, region_: str | None = None) -> dict[str, Any]:
    """检查密钥能不能用：换通行证并读一次个人资料。成功返回资料，失败抛 OfficialError。"""
    src = OfficialSource(api_key, region_)
    return src.call(lambda c: c.get_user_profile_settings()) or {}
