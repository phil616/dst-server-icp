"""基础路由:健康检查 + 全局 Shard 进程总览。

实例 / Shard / MOD / 备份的业务路由见 instances.py;安装更新与代理见 admin.py;
实时日志见 ws.py。本服务部署在内网,不做鉴权(见 DESIGN.md 2.8)。
"""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Request

import dst_serverd

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": dst_serverd.__version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.system(),
    }


@router.get("/shards")
def list_shards(request: Request) -> list[dict]:
    """所有被托管 Shard 进程的实时状态(跨实例)。"""
    return request.app.state.supervisor.status()
