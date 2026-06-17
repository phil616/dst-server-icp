"""OpenAI-compatible AI 设置与 MOD 配置翻译。"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Literal

from ..db import Database

TranslationTarget = Literal["labels", "choices"]

_DEFAULT_API_BASE = "https://api.openai.com/v1"


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
    if not options:
        return {"labels": {}, "choices": {}}

    payload = _translation_payload(schema, mod, target)
    response = _chat_completion(settings, _messages(payload, target))
    parsed = _parse_json_object(response)
    return {
        "labels": _normalize_str_map(parsed.get("labels")),
        "choices": _normalize_nested_str_map(parsed.get("choices")),
    }


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
                "输出格式必须是:\n"
                "{"
                "\"labels\":{\"option.name\":\"中文配置项名\"},"
                "\"choices\":{\"option.name\":{\"data_key\":\"中文配置值\"}}"
                "}\n"
                "如果本次目标不需要某个字段,返回空对象。data_key 必须原样使用输入中的 data_key。\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def _chat_completion(settings: dict, messages: list[dict]) -> str:
    base = _normalize_api_base(settings.get("api_base") or _DEFAULT_API_BASE)
    body = json.dumps({
        "model": (settings.get("model") or "").strip(),
        "messages": messages,
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
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
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise ValueError(f"AI 翻译接口返回 {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"AI 翻译接口连接失败:{exc.reason}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
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


def _normalize_str_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None and str(v).strip()}


def _normalize_nested_str_map(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, val in raw.items():
        nested = _normalize_str_map(val)
        if nested:
            out[str(key)] = nested
    return out


def _data_key(v: Any) -> str:
    encoded = json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "undefined" if encoded is None else encoded
