"""极简 Lua table 字面量解析器 —— 解析 DST 的 modoverrides.lua / worldgenoverride.lua。

只支持 DST 实际用到的子集:`return { ... }`,表项形如 `["key"]=value` / `key=value` /
positional value;value 取值 true/false/nil、数字、带引号字符串、嵌套表。够用且无第三方依赖。
"""

from __future__ import annotations

from typing import Any

_NUM = set("+-0123456789.")


class _Parser:
    def __init__(self, s: str) -> None:
        self.s = s
        self.i = 0
        self.n = len(s)

    def _ws(self) -> None:
        while self.i < self.n:
            c = self.s[self.i]
            if c in " \t\r\n,;":
                self.i += 1
            elif c == "-" and self.s[self.i : self.i + 2] == "--":
                self.i += 2
                if self.s[self.i : self.i + 2] == "[[":
                    end = self.s.find("]]", self.i)
                    self.i = end + 2 if end >= 0 else self.n
                else:
                    nl = self.s.find("\n", self.i)
                    self.i = nl + 1 if nl >= 0 else self.n
            else:
                break

    def value(self) -> Any:
        self._ws()
        if self.i >= self.n:
            return None
        c = self.s[self.i]
        if c == "{":
            return self.table()
        if c in "\"'":
            return self.string()
        if self.s[self.i : self.i + 4] == "true":
            self.i += 4
            return True
        if self.s[self.i : self.i + 5] == "false":
            self.i += 5
            return False
        if self.s[self.i : self.i + 3] == "nil":
            self.i += 3
            return None
        return self.number()

    def string(self) -> str:
        q = self.s[self.i]
        self.i += 1
        out: list[str] = []
        while self.i < self.n:
            c = self.s[self.i]
            if c == "\\":
                nxt = self.s[self.i + 1] if self.i + 1 < self.n else ""
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                self.i += 2
            elif c == q:
                self.i += 1
                break
            else:
                out.append(c)
                self.i += 1
        return "".join(out)

    def number(self) -> Any:
        start = self.i
        while self.i < self.n and self.s[self.i] in _NUM:
            self.i += 1
        tok = self.s[start:self.i]
        if not tok:  # 兜底:吃一个字符避免死循环
            self.i += 1
            return None
        try:
            return int(tok)
        except ValueError:
            try:
                return float(tok)
            except ValueError:
                return tok

    def _ident(self) -> str | None:
        start = self.i
        while self.i < self.n and (self.s[self.i].isalnum() or self.s[self.i] == "_"):
            self.i += 1
        return self.s[start:self.i] if self.i > start else None

    def table(self) -> Any:
        self.i += 1  # '{'
        d: dict[Any, Any] = {}
        lst: list[Any] = []
        while True:
            self._ws()
            if self.i >= self.n or self.s[self.i] == "}":
                self.i += 1
                break
            if self.s[self.i] == "[":
                self.i += 1
                key = self.value()
                self._ws()
                if self.i < self.n and self.s[self.i] == "]":
                    self.i += 1
                self._ws()
                if self.i < self.n and self.s[self.i] == "=":
                    self.i += 1
                d[key] = self.value()
            else:
                save = self.i
                ident = self._ident()
                self._ws()
                if ident is not None and self.i < self.n and self.s[self.i] == "=" \
                        and self.s[self.i : self.i + 2] != "==":
                    self.i += 1
                    d[ident] = self.value()
                else:
                    self.i = save
                    lst.append(self.value())
        if lst and not d:
            return lst
        for idx, v in enumerate(lst, 1):
            d[idx] = v
        return d


def parse_lua_table(text: str) -> Any:
    """解析 `return { ... }`(或裸 `{ ... }`)为 Python dict/list。失败返回 {}。"""
    s = text.strip()
    if s.startswith("return"):
        s = s[len("return"):]
    p = _Parser(s)
    p._ws()
    if p.i < p.n and p.s[p.i] == "{":
        try:
            return p.table()
        except Exception:  # noqa: BLE001 解析失败兜底
            return {}
    return {}
