"""MOD 配置定义读取。

DST 的 MOD 在 `modinfo.lua` 里用 `configuration_options = { ... }` 声明可配置项,
运行时实际取值写在每个 Shard 的 `modoverrides.lua` 中。本模块只读取已安装 MOD 的
声明定义,保存仍沿用 `services.instances.set_mod()` 写回 `modoverrides.lua`。
"""

from __future__ import annotations

import re
from typing import Any

from ..config import Settings
from ..lua import parse_lua_table
from ..models import Mod


_IDENT_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def describe_mod_config(settings: Settings, mod: Mod) -> dict:
    """返回前端生成配置表单所需的配置项定义。"""
    path = settings.server_dir / "mods" / mod.ref / "modinfo.lua"
    if not path.is_file():
        return {"installed": False, "info": {}, "options": [], "error": ""}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        table = _extract_assignment_table(text, "configuration_options")
        info = _extract_mod_info(text)
        if not table:
            return {"installed": True, "info": info, "options": [], "error": ""}
        parsed = parse_lua_table(_mask_dynamic_values(table))
        return {"installed": True, "info": info, "options": _normalize_options(parsed), "error": ""}
    except Exception as exc:  # noqa: BLE001 表单元数据解析失败不应影响实例视图
        return {"installed": True, "info": {}, "options": [], "error": str(exc)}


def _normalize_options(raw: Any) -> list[dict]:
    out: list[dict] = []
    for item in _as_sequence(raw):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        choices = _normalize_choices(item.get("options"))
        has_default = "default" in item
        default = _jsonable(item.get("default"))
        if has_default and default is None and choices and all(c.get("data") is not None for c in choices):
            default = choices[0]["data"]
        out.append({
            "name": name,
            "label": _text(item.get("label")) or name,
            "hover": _text(item.get("hover")),
            "has_default": has_default,
            "default": default,
            "options": choices,
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


def _extract_mod_info(text: str) -> dict[str, Any]:
    keys = [
        "name", "version", "description", "author", "forumthread", "api_version",
        "dst_compatible", "all_clients_require_mod", "client_only_mod",
    ]
    return {key: val for key in keys if (val := _extract_scalar_assignment(text, key)) is not None}


def _extract_scalar_assignment(text: str, name: str) -> Any:
    i = 0
    n = len(text)
    while i < n:
        i = _skip_ws_and_comments(text, i)
        if _at_identifier(text, i, name):
            j = _skip_ws_and_comments(text, i + len(name))
            if j < n and text[j] == "=":
                j = _skip_ws_and_comments(text, j + 1)
                return _read_scalar(text, j)
        if i < n and text[i] in "\"'":
            i = _skip_string(text, i)
        else:
            i += 1
    return None


def _read_scalar(text: str, i: int) -> Any:
    if i >= len(text):
        return None
    if text[i] in "\"'":
        return _read_lua_string(text, i)[0]
    for literal, value in (("true", True), ("false", False), ("nil", None)):
        if text.startswith(literal, i):
            return value
    m = re.match(r"[+-]?\d+(?:\.\d+)?", text[i:])
    if not m:
        return None
    raw = m.group(0)
    return float(raw) if "." in raw else int(raw)


def _read_lua_string(text: str, i: int) -> tuple[str, int]:
    quote = text[i]
    i += 1
    out: list[str] = []
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            nxt = text[i + 1] if i + 1 < n else ""
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            i += 2
        elif c == quote:
            return "".join(out), i + 1
        else:
            out.append(c)
            i += 1
    return "".join(out), n


def _mask_dynamic_values(text: str) -> str:
    """把解析器不支持的表达式值替换成 nil,避免它们破坏整个 table。"""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] in "\"'":
            end = _skip_string(text, i)
            out.append(text[i:end])
            i = end
            continue
        if text.startswith("--", i):
            end = _skip_comment(text, i)
            out.append(text[i:end])
            i = end
            continue
        c = text[i]
        out.append(c)
        i += 1
        if c != "=":
            continue
        i = _copy_ws_and_comments(text, i, out)
        if i >= n or _is_supported_value_start(text, i):
            continue
        out.append("nil")
        i = _skip_dynamic_expr(text, i)
    return "".join(out)


def _copy_ws_and_comments(text: str, i: int, out: list[str]) -> int:
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n":
            out.append(text[i])
            i += 1
            continue
        if text.startswith("--", i):
            end = _skip_comment(text, i)
            out.append(text[i:end])
            i = end
            continue
        break
    return i


def _is_supported_value_start(text: str, i: int) -> bool:
    return (
        text[i] in "{'\"+-0123456789"
        or text.startswith("true", i)
        or text.startswith("false", i)
        or text.startswith("nil", i)
    )


def _skip_dynamic_expr(text: str, i: int) -> int:
    parens = 0
    brackets = 0
    n = len(text)
    while i < n:
        if text[i] in "\"'":
            i = _skip_string(text, i)
            continue
        if text.startswith("--", i):
            i = _skip_comment(text, i)
            continue
        c = text[i]
        if c == "(":
            parens += 1
        elif c == ")" and parens:
            parens -= 1
        elif c == "[":
            brackets += 1
        elif c == "]" and brackets:
            brackets -= 1
        elif c in ",}" and parens == 0 and brackets == 0:
            return i
        i += 1
    return i


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
