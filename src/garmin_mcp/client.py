"""个人 API 配置存储；每份服务对应一个账号。"""
from __future__ import annotations

import json
import os
import secrets
import threading
import stat
import tempfile
from pathlib import Path
from typing import Any


REGIONS = ("global", "cn")
REGION_NAMES = {"global": "国际区 garmin.com", "cn": "中国区 garmin.cn"}

_lock = threading.RLock()


def data_dir() -> Path:
    d = Path(os.getenv("GARMIN_MCP_DATA", "~/.garmin-mcp")).expanduser()
    if d.is_symlink():
        raise RuntimeError("凭证目录不能是符号链接")
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        if d.stat().st_uid != os.getuid():
            raise RuntimeError("凭证目录必须属于当前用户")
        d.chmod(0o700)
    return d


def _config_path() -> Path:
    return data_dir() / "config.json"


def load_config() -> dict[str, Any]:
    """读取设置；第一次运行时自动生成连接密钥。"""
    with _lock:
        path = _config_path()
        cfg: dict[str, Any] = {}
        if path.exists():
            cfg = json.loads(private_read(path))
        changed = False
        if not cfg.get("secret"):
            cfg["secret"] = new_secret()
            changed = True
        if not cfg.get("session_key"):
            cfg["session_key"] = secrets.token_hex(32)
            changed = True
        if changed:
            _write(cfg)
        return cfg


def save_config(**updates: Any) -> dict[str, Any]:
    with _lock:
        cfg = load_config()
        cfg.update(updates)
        _write(cfg)
    return cfg


def private_read(path: Path) -> str:
    if path.is_symlink():
        raise OSError("拒绝读取符号链接凭证")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("凭证必须是普通文件")
        if os.name == "posix":
            if info.st_uid != os.getuid():
                raise RuntimeError("凭证文件必须属于当前用户")
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            fd = -1
            return fh.read()
    finally:
        if fd >= 0:
            os.close(fd)


def private_write(path: Path, value: str) -> None:
    if path.is_symlink():
        raise RuntimeError("拒绝写入符号链接凭证")
    fd, temp = tempfile.mkstemp(prefix=".private-", dir=path.parent)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            fh.write(value)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        if fd >= 0:
            os.close(fd)
        Path(temp).unlink(missing_ok=True)


def _write(cfg: dict[str, Any]) -> None:
    private_write(_config_path(), json.dumps(cfg, ensure_ascii=False, indent=2))


def new_secret() -> str:
    """43 个字符的随机密钥，猜中的概率可以忽略不计。"""
    return secrets.token_urlsafe(32)


def get_region() -> str:
    """环境变量 GARMIN_REGION 优先，其次是设置页面里选的区域。"""
    region = (os.getenv("GARMIN_REGION") or load_config().get("region") or "global").strip().lower()
    if region not in REGIONS:
        raise ValueError(f"区域只能是 global 或 cn，现在是：{region!r}")
    return region

