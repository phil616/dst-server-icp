"""MOD 配置定义读取。

DST 的 MOD 在 `modinfo.lua` 里用 `configuration_options = { ... }` 声明可配置项,
运行时实际取值写在每个 Shard 的 `modoverrides.lua` 中。本模块只读取已安装 MOD 的
声明定义,保存仍沿用 `services.instances.set_mod()` 写回 `modoverrides.lua`。
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..lua import parse_lua_table
from ..models import Mod


_IDENT_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def describe_mod_config(settings: Settings, mod: Mod) -> dict:
    """返回前端生成配置表单所需的配置项定义。"""
    path = settings.server_dir / "mods" / mod.ref / "modinfo.lua"
    if not path.is_file():
        return {"installed": False, "options": [], "error": ""}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        table = _extract_assignment_table(text, "configuration_options")
        if not table:
            return {"installed": True, "options": [], "error": ""}
        parsed = parse_lua_table(table)
        return {"installed": True, "options": _normalize_options(parsed), "error": ""}
    except Exception as exc:  # noqa: BLE001 表单元数据解析失败不应影响实例视图
        return {"installed": True, "options": [], "error": str(exc)}


def _normalize_options(raw: Any) -> list[dict]:
    out: list[dict] = []
    for item in _as_sequence(raw):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        out.append({
            "name": name,
            "label": _text(item.get("label")) or name,
            "hover": _text(item.get("hover")),
            "default": _jsonable(item.get("default")),
            "options": _normalize_choices(item.get("options")),
        })
    return out


def _normalize_choices(raw: Any) -> list[dict]:
    choices: list[dict] = []
    for item in _as_sequence(raw):
        if not isinstance(item, dict) or "data" not in item:
            continue
        data = _jsonable(item.get("data"))
        choices.append({
            "description": _text(item.get("description")) or _text(data),
            "hover": _text(item.get("hover")),
            "data": data,
        })
    return choices


def _as_sequence(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        numeric = [(k, v) for k, v in raw.items() if isinstance(k, int)]
        if numeric:
            return [v for _, v in sorted(numeric, key=lambda kv: kv[0])]
    return []


def _jsonable(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        return [_jsonable(i) for i in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(val) for k, val in v.items()}
    return str(v)


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _extract_assignment_table(text: str, name: str) -> str:
    i = 0
    n = len(text)
    while i < n:
        i = _skip_ws_and_comments(text, i)
        if _at_identifier(text, i, name):
            j = _skip_ws_and_comments(text, i + len(name))
            if j < n and text[j] == "=":
                j = _skip_ws_and_comments(text, j + 1)
                if j < n and text[j] == "{":
                    end = _find_table_end(text, j)
                    return text[j:end]
        if i < n and text[i] in "\"'":
            i = _skip_string(text, i)
        else:
            i += 1
    return ""


def _at_identifier(text: str, i: int, name: str) -> bool:
    if not text.startswith(name, i):
        return False
    before = text[i - 1] if i > 0 else ""
    after_i = i + len(name)
    after = text[after_i] if after_i < len(text) else ""
    return before not in _IDENT_CHARS and after not in _IDENT_CHARS


def _find_table_end(text: str, start: int) -> int:
    depth = 0
    i = start
    n = len(text)
    while i < n:
        if text[i] in "\"'":
            i = _skip_string(text, i)
            continue
        if text.startswith("--", i):
            i = _skip_comment(text, i)
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _skip_ws_and_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n":
            i += 1
            continue
        if text.startswith("--", i):
            i = _skip_comment(text, i)
            continue
        break
    return i


def _skip_comment(text: str, i: int) -> int:
    if text.startswith("--[[", i):
        end = text.find("]]", i + 4)
        return len(text) if end < 0 else end + 2
    end = text.find("\n", i + 2)
    return len(text) if end < 0 else end + 1


def _skip_string(text: str, i: int) -> int:
    quote = text[i]
    i += 1
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
        elif text[i] == quote:
            return i + 1
        else:
            i += 1
    return n
