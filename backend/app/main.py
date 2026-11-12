"""FastAPI application factory, lifecycle management, and static PWA serving."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_admin, routes_auth, routes_courses, routes_notify, routes_watches
from app.auth import hash_password_async
from app.config import Settings, get_settings
from app.db import Database
from app.providers.base import AvailabilityProvider
from app.providers.cornell import CornellRosterApiProvider
from app.services.catalog import CatalogSyncService
from app.services.dispatcher import AlertDispatcher
from app.services.notifiers import DiscordWebhookNotifier, WebPushNotifier
from app.services.poller import PollerEngine
from app.services.sse import SSEHub

logger = logging.getLogger("classsniper")


async def _bootstrap_env_admin(db: Database, settings: Settings) -> None:
    if not (settings.admin_username.strip() and settings.admin_password.strip()):
        return
    row = await db.fetch_one("SELECT COUNT(*) AS cnt FROM users")
    if row and int(row["cnt"]) > 0:
        return
    pw_hash = await hash_password_async(settings.admin_password)
    await db.execute(
        """
        INSERT INTO users (username, password_hash, role, priority_tier)
        VALUES (?, ?, 'admin', 2)
        """,
        (settings.admin_username.strip(), pw_hash),
    )


async def _startup_catalog_sync(catalog: CatalogSyncService) -> None:
    try:
        await catalog.sync_rosters_and_subjects()
    except Exception as exc:
        logger.warning("Initial Cornell roster/subject sync skipped or failed: %s", exc)


async def _periodic_catalog_loop(catalog: CatalogSyncService, interval_hours: float) -> None:
    interval_sec = max(1800.0, interval_hours * 3600.0)
    while True:
        await asyncio.sleep(interval_sec)
        try:
            await catalog.sync_rosters_and_subjects()
        except Exception as exc:
            logger.warning("Periodic roster sync failed: %s", exc)


def create_app(
    custom_settings: Optional[Settings] = None,
    custom_provider: Optional[AvailabilityProvider] = None,
) -> FastAPI:
    settings = custom_settings or get_settings()
    settings.ensure_persisted_secrets()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.db_path)
        await db.connect()
        await _bootstrap_env_admin(db, settings)

        provider: AvailabilityProvider = custom_provider or CornellRosterApiProvider(
            base_url=settings.cornell_base_url,
            timeout_sec=settings.cornell_api_timeout_sec,
        )
        sse_hub = SSEHub()
        web_push = WebPushNotifier(
            vapid_private_key=settings.vapid_private_key,
            vapid_subject=settings.effective_vapid_subject,
        )
        discord_notifier = DiscordWebhookNotifier()
        catalog = CatalogSyncService(
            db=db,
            provider=provider,
            sync_interval_hours=settings.catalog_sync_interval_hours,
        )
        dispatcher = AlertDispatcher(
            db=db,
            settings=settings,
            sse_hub=sse_hub,
            web_push=web_push,
            discord=discord_notifier,
        )
        poller = PollerEngine(
            db=db,
            settings=settings,
            provider=provider,
            catalog=catalog,
            dispatcher=dispatcher,
            sse_hub=sse_hub,
        )

        app.state.settings = settings
        app.state.db = db
        app.state.provider = provider
        app.state.sse_hub = sse_hub
        app.state.catalog = catalog
        app.state.dispatcher = dispatcher
        app.state.poller = poller

        bg_tasks: list[asyncio.Task[None]] = []
        if settings.enable_background_workers:
            poller.start()
            bg_tasks.append(asyncio.create_task(_startup_catalog_sync(catalog), name="startup-rosters"))
            bg_tasks.append(
                asyncio.create_task(
                    _periodic_catalog_loop(catalog, settings.catalog_sync_interval_hours),
                    name="periodic-rosters",
                )
            )

        try:
            yield
        finally:
            for t in bg_tasks:
                t.cancel()
            await poller.stop()
            await discord_notifier.close()
            await provider.close()
            await db.close()

    app = FastAPI(
        title="ClassSniper",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Override get_settings dependency when custom_settings is passed (e.g. tests)
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.app_origin, "http://localhost:5173", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_auth.router)
    app.include_router(routes_courses.router)
    app.include_router(routes_watches.router)
    app.include_router(routes_notify.router)
    app.include_router(routes_admin.router)

    static_dir: Path = settings.static_dir
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/sw.js", include_in_schema=False)
    async def service_worker() -> FileResponse:
        sw_path = static_dir / "sw.js"
        if not sw_path.exists():
            raise HTTPException(status_code=404, detail="Service worker not built")
        return FileResponse(
            sw_path,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def web_manifest() -> FileResponse:
        manifest_path = static_dir / "manifest.webmanifest"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="Manifest not built")
        return FileResponse(
            manifest_path,
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        candidate = (static_dir / full_path).resolve()
        if full_path and static_dir.exists() and str(candidate).startswith(str(static_dir.resolve())) and candidate.is_file():
            return FileResponse(candidate)
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend not built")

    return app


app = create_app()
