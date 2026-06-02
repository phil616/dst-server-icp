"""本地通讯录 —— 自动记忆每个加入过游戏的玩家(昵称 ↔ Klei ID)。

设计原则:只要有玩家加入到游戏,supervisor 解析日志拿到其 KU_/昵称 后就调用
`record_seen` 入册(见 supervisor/manager.py)。这是一份纯本地的"昵称-ID 备忘录",
方便对好友 ID 做提示与复制,与访问控制(access_entries)互不相干。
"""

from __future__ import annotations

import time

from ..db import Database


def record_seen(db: Database, klei_id: str, name: str = "") -> None:
    """记一次"玩家出现":首见即插入,再见则刷新昵称/时间并累加次数。klei_id 为空则忽略。"""
    klei_id = (klei_id or "").strip()
    if not klei_id:
        return
    name = (name or "").strip()
    now = time.time()
    db.execute(
        "INSERT INTO contacts (klei_id, name, first_seen, last_seen, seen_count) "
        "VALUES (?, ?, ?, ?, 1) "
        "ON CONFLICT(klei_id) DO UPDATE SET "
        # 只有拿到非空昵称才覆盖,避免后续无名次刷掉已记的昵称
        "  name = CASE WHEN excluded.name != '' THEN excluded.name ELSE contacts.name END, "
        "  last_seen = excluded.last_seen, "
        "  seen_count = contacts.seen_count + 1",
        (klei_id, name, now, now),
    )


def list_contacts(db: Database) -> list[dict]:
    """通讯录全部条目,最近加入的排在前面。"""
    return [dict(r) for r in db.query("SELECT * FROM contacts ORDER BY last_seen DESC")]


def update_contact(db: Database, klei_id: str, *, name: str | None = None,
                   note: str | None = None) -> None:
    """更新昵称 / 备注(任一为 None 表示不改)。"""
    sets: list[str] = []
    params: list[object] = []
    if name is not None:
        sets.append("name = ?")
        params.append(name.strip())
    if note is not None:
        sets.append("note = ?")
        params.append(note.strip())
    if not sets:
        return
    params.append(klei_id)
    db.execute(f"UPDATE contacts SET {', '.join(sets)} WHERE klei_id = ?", params)


def delete_contact(db: Database, klei_id: str) -> None:
    db.execute("DELETE FROM contacts WHERE klei_id = ?", (klei_id,))
