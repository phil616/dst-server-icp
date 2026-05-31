"""从 app.state 取依赖(内网部署,无鉴权)。"""

from __future__ import annotations

from fastapi import HTTPException, Request

from ..config import Settings
from ..db import Database
from ..models import Instance
from ..services import instances as inst_svc
from ..supervisor import Supervisor


def db(request: Request) -> Database:
    return request.app.state.db


def settings(request: Request) -> Settings:
    return request.app.state.settings


def sup(request: Request) -> Supervisor:
    return request.app.state.supervisor


def require_instance(request: Request, instance_id: int) -> Instance:
    inst = inst_svc.get_instance(db(request), instance_id)
    if inst is None:
        raise HTTPException(404, f"实例 {instance_id} 不存在")
    return inst
