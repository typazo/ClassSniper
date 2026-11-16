"""Shared FastAPI application state dependencies for route handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.services.catalog import CatalogSyncService
    from app.services.dispatcher import AlertDispatcher
    from app.services.insights import CourseInsightsService
    from app.services.poller import PollerEngine
    from app.services.scheduler import SchedulerService
    from app.services.sse import SSEHub


def get_poller(request: Request) -> PollerEngine:
    return request.app.state.poller


def get_catalog(request: Request) -> CatalogSyncService:
    return request.app.state.catalog


def get_sse(request: Request) -> SSEHub:
    return request.app.state.sse_hub


def get_dispatcher(request: Request) -> AlertDispatcher:
    return request.app.state.dispatcher


def get_insights(request: Request) -> CourseInsightsService:
    return request.app.state.insights


def get_scheduler(request: Request) -> SchedulerService:
    return request.app.state.scheduler
