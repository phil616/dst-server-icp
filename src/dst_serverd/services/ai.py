"""OpenAI-compatible AI 设置与 MOD 配置翻译。"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Literal

from ..db import Database

TranslationTarget = Literal["labels", "choices", "guide"]

_DEFAULT_API_BASE = "https://api.openai.com/v1"
_LOG_PREVIEW_CHARS = 3000

log = logging.getLogger("dst_serverd.ai")


def load_ai_settings(db: Database) -> dict:
    return {
        "api_base": db.get_kv("ai_api_base", _DEFAULT_API_BASE),
        "api_key": db.get_kv("ai_api_key", ""),
        "model": db.get_kv("ai_model", ""),
    }


def save_ai_settings(db: Database, data: dict) -> dict:
    db.set_kv("ai_api_base", (data.get("api_base") or _DEFAULT_API_BASE).strip())
    db.set_kv("ai_api_key", (data.get("api_key") or "").strip())
    db.set_kv("ai_model", (data.get("model") or "").strip())
    return load_ai_settings(db)


def translate_mod_config(schema: dict, mod: dict, settings: dict, target: TranslationTarget) -> dict:
    api_key = (settings.get("api_key") or "").strip()
    model = (settings.get("model") or "").strip()
    if not api_key or not model:
        raise ValueError("请先在设置中填写 AI APIKey 和模型名称")

    options = schema.get("options") or []
    choice_count = sum(len(opt.get("options") or []) for opt in options)
    log.info(
        "[ai] MOD配置翻译开始 target=%s mod=%s workshop=%s options=%d choices=%d api_base=%s model=%s",
        target,
        mod.get("ref") or mod.get("name") or mod.get("title") or "-",
        mod.get("workshop_id") or "-",
        len(options),
        choice_count,
        _normalize_api_base(settings.get("api_base") or _DEFAULT_API_BASE),
        model,
    )
    if not options or target == "guide":
        payload = _guidance_payload(schema, mod)
        log.info("[ai] MOD说明生成输入 payload=%s", _short_json(payload))
        response = _chat_completion(settings, _guidance_messages(payload))
        log.info("[ai] LLM原始说明 chars=%d preview=%s", len(response), _short_text(response))
        parsed = _parse_json_object(response)
        result = {"labels": {}, "choices": {}, "guidance": _normalize_guidance(parsed)}
        log.info(
            "[ai] MOD说明生成完成 summary=%s steps=%d files=%d warnings=%d",
            bool(result["guidance"]["summary"]),
            len(result["guidance"]["manual_steps"]),
            len(result["guidance"]["files"]),
            len(result["guidance"]["warnings"]),
        )
        return result

    payload = _translation_payload(schema, mod, target)
    log.info("[ai] MOD配置翻译输入 target=%s payload=%s", target, _short_json(payload))
    response = _chat_completion(settings, _messages(payload, target))
    log.info("[ai] LLM原始文本 target=%s chars=%d preview=%s", target, len(response), _short_text(response))
    parsed = _parse_json_object(response)
    result = _normalize_translation(parsed, schema)
    label_count = len(result["labels"])
    translated_choice_count = sum(len(v) for v in result["choices"].values())
    log.info(
        "[ai] MOD配置翻译完成 target=%s parsed_keys=%s labels=%d choice_options=%d choice_values=%d",
        target,
        sorted(str(k) for k in parsed.keys()),
        label_count,
        len(result["choices"]),
        translated_choice_count,
    )
    if target == "choices" and translated_choice_count == 0 and choice_count:
        log.warning(
            "[ai] MOD配置值翻译未匹配到任何 data_key,通常是模型没有使用输入 choice.data_key 作为返回键"
        )
    return result


def _guidance_payload(schema: dict, mod: dict) -> dict:
    return {
        "mod": {
            "ref": mod.get("ref"),
            "workshop_id": mod.get("workshop_id"),
            "title": mod.get("title"),
            "name": mod.get("name"),
            "source": mod.get("source"),
            "modinfo": schema.get("info") or {},
        },
        "installed": bool(schema.get("installed")),
        "schema_error": schema.get("error") or "",
        "current_configuration_options": mod.get("config") or {},
        "configuration_options_declared": bool(schema.get("options")),
    }


def _guidance_messages(payload: dict) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "你是《饥荒联机版》(Don't Starve Together, DST) 专用服务器 MOD 配置顾问。"
                "你只提供只读说明,不能执行、模拟执行或声称已经执行任何文件、JSON、Lua 修改。"
                "只能依据输入的 MOD 元信息和现有配置作答;无法确认的内容必须明确标为未知。"
                "严禁编造未在输入中出现的 configuration_options 键和值。"
                "输出简体中文 JSON 对象,不要 Markdown,不要 JSON 以外的文字。"
            ),
        },
        {
            "role": "user",
            "content": (
                "该 MOD 没有声明可供面板生成表单的 configuration_options。"
                "请说明它大致是做什么的,用户还能从哪里了解或手工调整它。"
                "如果它本来就没有可配置项,请明确说明。"
                "手工步骤只能是建议,不要生成可直接自动应用的补丁或声称已经修改。\n"
                "返回格式必须是:"
                "{\"guidance\":{"
                "\"summary\":\"MOD用途与是否可配置的简短说明\","
                "\"details\":[\"补充说明\"],"
                "\"manual_steps\":[\"用户可自行检查或修改的步骤\"],"
                "\"files\":[{\"path\":\"文件或界面位置\",\"purpose\":\"用途\"}],"
                "\"warnings\":[\"风险或不确定性\"]"
                "}}。\n"
                "可说明 DST 常见位置:MOD 自身的 modinfo.lua 用于声明元信息和配置定义;"
                "每个 Shard 的 modoverrides.lua 保存启用状态和 configuration_options;"
                "面板下方 JSON 对应当前 MOD 的 configuration_options。"
                "不要建议修改 MOD 源码,除非明确标注那属于 MOD 开发者操作且更新可能覆盖。\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def _translation_payload(schema: dict, mod: dict, target: TranslationTarget) -> dict:
    info = schema.get("info") or {}
    options = []
    for opt in schema.get("options") or []:
        item = {
            "name": opt.get("name"),
            "label": opt.get("label"),
            "hover": opt.get("hover"),
        }
        if target == "choices":
            item["choices"] = [
                {
                    "data_key": _data_key(choice.get("data")),
                    "data": choice.get("data"),
                    "description": choice.get("description"),
                    "hover": choice.get("hover"),
                }
                for choice in opt.get("options") or []
            ]
        options.append(item)

    return {
        "target": target,
        "mod": {
            "ref": mod.get("ref"),
            "workshop_id": mod.get("workshop_id"),
            "title": mod.get("title"),
            "name": mod.get("name"),
            "installed_time_updated": mod.get("installed_time_updated"),
            "workshop_time_updated": mod.get("workshop_time_updated"),
            "modinfo": info,
        },
        "configuration_options": options,
    }


def _messages(payload: dict, target: TranslationTarget) -> list[dict]:
    target_desc = "配置项名称(label/hover)" if target == "labels" else "配置值选项(description/hover)"
    output_contract = (
        "{\"labels\":{\"<option.name>\":\"中文配置项名\"},\"choices\":{}}"
        if target == "labels"
        else "{\"labels\":{},\"choices\":{\"<option.name>\":{\"<choice.data_key>\":\"中文配置值\"}}}"
    )
    data_key_rule = (
        "choices 内层对象的 key 必须使用输入中 choice.data_key 的实际字符串值。"
        "例如输入 data_key 是 true,就返回 \"true\";输入 data_key 是 \"\\\"default\\\"\","
        "就返回 \"\\\"default\\\"\"。严禁把固定字符串 \"data_key\" 当作键名。"
        if target == "choices"
        else "labels 的 key 必须使用输入中的 option.name。"
    )
    return [
        {
            "role": "system",
            "content": (
                "你是《饥荒联机版》(Don't Starve Together, DST) MOD 的专业本地化译者。"
                "你的任务是把 MOD 配置界面文本翻译成简体中文。"
                "保留代码键、枚举值、数字、布尔值、Workshop ID、专有名词中的可识别英文缩写。"
                "译文要短,适合放在网页表单、下拉框和 tooltip 中。"
                "只输出 JSON 对象,不要 Markdown,不要解释。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请翻译以下 DST MOD 的{target_desc}。\n"
                f"输出格式必须是:{output_contract}\n"
                f"{data_key_rule}\n"
                "如果本次目标不需要某个字段,返回空对象。不要增加 JSON 以外的解释文字。\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def _chat_completion(settings: dict, messages: list[dict]) -> str:
    base = _normalize_api_base(settings.get("api_base") or _DEFAULT_API_BASE)
    model = (settings.get("model") or "").strip()
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }).encode("utf-8")
    url = f"{base}/chat/completions"
    log.info("[ai] 请求LLM POST %s model=%s messages=%d body_bytes=%d", url, model, len(messages), len(body))
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {(settings.get('api_key') or '').strip()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "dst-serverd",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 用户配置的兼容 API
            data = json.load(resp)
            log.info(
                "[ai] LLM HTTP响应 status=%s keys=%s choices=%s",
                getattr(resp, "status", "?"),
                sorted(str(k) for k in data.keys()) if isinstance(data, dict) else type(data).__name__,
                len(data.get("choices") or []) if isinstance(data, dict) else "-",
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        log.warning("[ai] LLM HTTP错误 status=%s detail=%s", exc.code, detail)
        raise ValueError(f"AI 翻译接口返回 {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        log.warning("[ai] LLM连接失败 reason=%s", exc.reason)
        raise ValueError(f"AI 翻译接口连接失败:{exc.reason}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        log.warning("[ai] LLM响应格式不兼容 response=%s", _short_json(data))
        raise ValueError("AI 翻译接口返回格式不兼容") from exc


def _normalize_api_base(v: str) -> str:
    base = v.strip().rstrip("/") or _DEFAULT_API_BASE
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    return base.rstrip("/")


def _parse_json_object(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("AI 未返回 JSON 对象") from None
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("AI 未返回 JSON 对象")
    return data


def _normalize_translation(parsed: dict, schema: dict) -> dict:
    return {
        "labels": _normalize_str_map(parsed.get("labels")),
        "choices": _normalize_choices_map(parsed.get("choices"), schema),
        "guidance": None,
    }


def _normalize_guidance(parsed: dict) -> dict:
    raw = parsed.get("guidance", parsed)
    if not isinstance(raw, dict):
        raw = {}
    return {
        "summary": _translation_text(raw.get("summary")),
        "details": _normalize_string_list(raw.get("details")),
        "manual_steps": _normalize_string_list(raw.get("manual_steps")),
        "files": _normalize_guidance_files(raw.get("files")),
        "warnings": _normalize_string_list(raw.get("warnings")),
    }


def _normalize_string_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if not isinstance(raw, list):
        return []
    return [text for item in raw if (text := _translation_text(item))]


def _normalize_guidance_files(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    files: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            if item.strip():
                files.append({"path": item.strip(), "purpose": ""})
            continue
        if not isinstance(item, dict):
            continue
        path = _translation_text(item.get("path"))
        purpose = _translation_text(item.get("purpose"))
        if path or purpose:
            files.append({"path": path, "purpose": purpose})
    return files


def _normalize_str_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None and str(v).strip()}


def _normalize_choices_map(raw: Any, schema: dict) -> dict[str, dict[str, str]]:
    if raw is None:
        return {}
    option_aliases = _option_aliases(schema)
    out: dict[str, dict[str, str]] = {}
    iterable = _choice_option_items(raw)
    for raw_key, val in iterable:
        option_name = option_aliases.get(str(raw_key))
        if option_name is None:
            log.warning("[ai] 忽略无法匹配的配置值翻译 option_key=%s value=%s", raw_key, _short_json(val))
            continue
        option = option_aliases[f"__option__:{option_name}"]
        nested = _normalize_choice_values(str(option_name), option, val)
        if nested:
            out[str(option_name)] = {**out.get(str(option_name), {}), **nested}
    return out


def _choice_option_items(raw: Any) -> list[tuple[str, Any]]:
    if isinstance(raw, dict):
        return [(str(k), v) for k, v in raw.items()]
    if isinstance(raw, list):
        items: list[tuple[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = item.get("name") or item.get("option") or item.get("option_name") or item.get("key")
            val = item.get("choices", item.get("values", item.get("translations", item)))
            if key:
                items.append((str(key), val))
        return items
    log.warning("[ai] 忽略非对象配置值翻译 choices=%s", _short_json(raw))
    return []


def _option_aliases(schema: dict) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    for opt in schema.get("options") or []:
        name = str(opt.get("name") or "")
        if not name:
            continue
        aliases[name] = name
        label = str(opt.get("label") or "").strip()
        if label:
            aliases[label] = name
        aliases[f"__option__:{name}"] = opt
    return aliases


def _normalize_choice_values(option_name: str, option: dict, raw: Any) -> dict[str, str]:
    aliases = _choice_aliases(option)
    expected_keys = {str(k) for k in aliases.values()}
    if isinstance(raw, list):
        out: dict[str, str] = {}
        for item in raw:
            out.update(_normalize_choice_item(option_name, item, aliases, expected_keys))
        return out
    if isinstance(raw, dict):
        if _looks_like_choice_item(raw):
            return _normalize_choice_item(option_name, raw, aliases, expected_keys)

        out: dict[str, str] = {}
        for key, val in raw.items():
            key_s = str(key)
            if key_s == "data_key":
                # 兼容模型照着旧提示词返回 {"data_key":"译文"} 的常见错误。
                if len(expected_keys) == 1:
                    only = next(iter(expected_keys))
                    text = _translation_text(val)
                    if text:
                        out[only] = text
                else:
                    log.warning(
                        "[ai] 配置值翻译返回了固定键 data_key,无法判断对应哪个选项 option=%s value=%s",
                        option_name,
                        _short_json(val),
                    )
                continue
            mapped = aliases.get(key_s)
            text = _translation_text(val)
            if mapped and text:
                out[mapped] = text
            elif isinstance(val, (dict, list)):
                out.update(_normalize_choice_item(option_name, val, aliases, expected_keys))
            else:
                log.warning(
                    "[ai] 忽略无法匹配的配置值翻译 option=%s data_key=%s text=%s",
                    option_name,
                    key_s,
                    _short_text(str(val)),
                )
        return out

    if len(expected_keys) == 1:
        text = _translation_text(raw)
        if text:
            return {next(iter(expected_keys)): text}
    log.warning("[ai] 忽略非对象配置值翻译 option=%s value=%s", option_name, _short_json(raw))
    return {}


def _normalize_choice_item(
    option_name: str, raw: Any, aliases: dict[str, str], expected_keys: set[str],
) -> dict[str, str]:
    if isinstance(raw, list) and len(raw) >= 2:
        mapped = aliases.get(str(raw[0]))
        text = _translation_text(raw[1])
        return {mapped: text} if mapped and text else {}
    if not isinstance(raw, dict):
        return {}

    if isinstance(raw.get("choices"), (dict, list)):
        return _normalize_choice_values_with_aliases(option_name, raw["choices"], aliases, expected_keys)

    key = _first_present(raw, "data_key", "key", "value_key", "value", "data")
    if key is None:
        return {}
    mapped = aliases.get(str(key)) or aliases.get(_data_key(key))
    text = _translation_text(raw)
    if mapped and text:
        return {mapped: text}
    if not mapped:
        log.warning(
            "[ai] 忽略无法匹配的配置值条目 option=%s data_key=%s expected=%s raw=%s",
            option_name,
            key,
            sorted(expected_keys),
            _short_json(raw),
        )
    return {}


def _normalize_choice_values_with_aliases(
    option_name: str, raw: Any, aliases: dict[str, str], expected_keys: set[str],
) -> dict[str, str]:
    if isinstance(raw, list):
        out: dict[str, str] = {}
        for item in raw:
            out.update(_normalize_choice_item(option_name, item, aliases, expected_keys))
        return out
    if isinstance(raw, dict):
        out: dict[str, str] = {}
        for key, val in raw.items():
            mapped = aliases.get(str(key))
            text = _translation_text(val)
            if mapped and text:
                out[mapped] = text
            elif isinstance(val, (dict, list)):
                out.update(_normalize_choice_item(option_name, val, aliases, expected_keys))
        return out
    return {}


def _looks_like_choice_item(raw: dict) -> bool:
    return any(k in raw for k in ("data_key", "value_key", "translation", "text", "zh", "cn"))


def _first_present(raw: dict, *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _choice_aliases(option: dict) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for choice in option.get("options") or []:
        data = choice.get("data")
        key = _data_key(data)
        candidates = {
            key,
            str(data),
            json.dumps(data, ensure_ascii=False),
            json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            str(choice.get("description") or "").strip(),
            str(choice.get("hover") or "").strip(),
        }
        if isinstance(data, str):
            candidates.add(data)
        if data is None:
            candidates.update({"nil", "null", "None"})
        for candidate in candidates:
            if candidate:
                aliases[candidate] = key
    return aliases


def _translation_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("translation", "text", "label", "description", "name", "zh", "cn", "value"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""
    if isinstance(raw, (int, float, bool)):
        return str(raw)
    return ""


def _data_key(v: Any) -> str:
    encoded = json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "undefined" if encoded is None else encoded


def _short_json(v: Any, max_chars: int = _LOG_PREVIEW_CHARS) -> str:
    try:
        text = json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        text = str(v)
    return _short_text(text, max_chars)


def _short_text(text: str, max_chars: int = _LOG_PREVIEW_CHARS) -> str:
    text = (text or "").replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...<truncated {len(text) - max_chars} chars>"
