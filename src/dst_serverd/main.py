"""FastAPI 入口。

生命周期(见 DESIGN.md 2.10):
- 启动:初始化 DB → reconcile(重新接管/补起 Shard)→ 启动监管循环。
- 关闭(被 systemd 停止):**只停监管循环,绝不关 Shard** —— 优雅分离,游戏继续跑;
  下次后端启动再重新接管。只有用户显式调用 stop 接口才真正关服。

内网部署,不做认证/鉴权。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .activity import setup_activity_log
from .api import admin_router, core_router, instances_router, ws_router
from .config import get_settings
from .db import Database
from .jobs import JobRunner
from .services.scheduler import BackupScheduler
from .supervisor import Supervisor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dst_serverd")

# 前端构建产物:由 ./make-web.sh 把 frontend/dist 整合到包内 static/
STATIC_DIR = Path(__file__).resolve().parent / "static"
_NOT_BUILT_HTML = (
    "<html><head><meta charset='utf-8'><title>DST Serverd</title></head>"
    "<body style='font-family:monospace;background:#11141a;color:#d7dce5;padding:40px'>"
    "<h2>前端尚未构建</h2><p>请在项目根目录执行 <code>./make-web.sh</code> "
    "(自动 npm install + build,并整合到后端 static/),然后刷新本页。</p>"
    "<p>后端 API 仍可用:<a style='color:#e8b339' href='/api/health'>/api/health</a></p>"
    "</body></html>"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    setup_activity_log(settings.logs_dir / "activity.log")
    db = Database(settings.db)
    sup = Supervisor(settings)
    app.state.settings = settings
    app.state.db = db
    app.state.supervisor = sup
    app.state.jobs = JobRunner()
    scheduler = BackupScheduler(db, settings)
    app.state.scheduler = scheduler

    log.info("=== DST Serverd 启动 ===  base=%s db=%s", settings.base, settings.db)
    log.info("对账(reconcile):扫描 %s 接管/补起已配置的 Shard", settings.run_dir)
    sup.reconcile()
    sup.start_loop()
    scheduler.start()
    log.info("后端就绪,监管循环已启动;Web 控制台:http://%s:%s/", settings.host, settings.port)
    try:
        yield
    finally:
        # 关键:不关 Shard,只停后端自己的循环(游戏进程已 setsid 脱离,继续运行)
        await scheduler.stop()
        await sup.stop_loop()
        db.close()
        log.info("backend stopping; shards left running for re-attach")


# 即使配置了 api_key,这些 /api 端点也始终放行:前端要靠它们探测是否需要鉴权。
_PUBLIC_API_PATHS = frozenset({"/api/health", "/api/auth/required"})


def _register_auth_guard(app: FastAPI) -> None:
    """APIKey 鉴权中间件。

    架构约定:对所有 /api 请求都读取 `APIKey` 头。当 settings.api_key 为空时不保护
    (放行任意值,包括缺省/空);非空时该头必须精确匹配,否则 401。前端据 401 重新索要 APIKey。
    WebSocket(日志流)浏览器无法附带自定义头,故不在此拦截。
    """
    @app.middleware("http")
    async def api_key_guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in _PUBLIC_API_PATHS:
            expected = (request.app.state.settings.api_key or "").strip()
            provided = request.headers.get("APIKey", "")
            if expected and provided != expected:
                return JSONResponse({"detail": "APIKey 无效或缺失,请重新输入"}, status_code=401)
        return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(title="DST Serverd", version="0.1.0", lifespan=lifespan)
    _register_auth_guard(app)
    app.include_router(core_router)
    app.include_router(instances_router)
    app.include_router(admin_router)
    app.include_router(ws_router)
    _mount_web(app)
    return app


def _mount_web(app: FastAPI) -> None:
    """托管前端:把 static/(make-web.sh 整合的构建产物)用 StaticFiles 挂载;支持 SPA 路由回退。"""
    index = STATIC_DIR / "index.html"
    if not index.exists():
        @app.get("/")
        def not_built() -> HTMLResponse:
            return HTMLResponse(_NOT_BUILT_HTML)
        return

    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(index)

    # SPA 客户端路由回退:非 /api、非 /assets 的路径,有同名静态文件就返回,否则回 index.html
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "assets/")):
            raise HTTPException(404, "not found")
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()


def run() -> None:
    """`dst-serverd` 脚本入口;生产由 systemd 调 .venv/bin/uvicorn(见 DESIGN.md 2.10)。"""
    settings = get_settings()
    uvicorn.run("dst_serverd.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
