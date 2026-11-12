"""Concurrent multi-channel alert dispatcher and delivery audit logger."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from app.config import Settings
from app.db import Database
from app.providers.base import CourseRecord, SectionRecord
from app.services.notifiers import (
    DeliveryOutcome,
    DiscordWebhookNotifier,
    WebPushNotifier,
    build_roster_course_url,
    build_student_center_url,
    format_status,
    is_valid_discord_user_id,
    is_valid_discord_webhook_url,
)
from app.services.sse import SSEHub


@dataclass(slots=True)
class MatchedAlert:
    watch: dict[str, Any]
    user: dict[str, Any]
    course: CourseRecord
    section: SectionRecord
    old_status: Optional[str]
    new_status: str
    poll_rtt_ms: int


class AlertDispatcher:
    """Coalesces section alerts and fans out Web Push, Discord, and SSE concurrently."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        sse_hub: SSEHub,
        web_push: WebPushNotifier,
        discord: DiscordWebhookNotifier,
    ) -> None:
        self.db = db
        self.settings = settings
        self.sse_hub = sse_hub
        self.web_push = web_push
        self.discord = discord

    async def get_shared_discord_webhook_url(self) -> str:
        override = await self.db.get_setting("discord_shared_webhook_url", "")
        if override.strip():
            return override.strip()
        return self.settings.discord_shared_webhook_url.strip()

    async def dispatch_alerts(self, alerts: list[MatchedAlert]) -> None:
        if not alerts:
            return

        # Group alerts by (roster, class_nbr, new_status) so Discord pings batch into 1 message
        grouped: dict[tuple[str, int, str], list[MatchedAlert]] = {}
        for alert in alerts:
            key = (alert.course.roster, alert.section.class_nbr, alert.new_status)
            grouped.setdefault(key, []).append(alert)

        shared_webhook_url = await self.get_shared_discord_webhook_url()
        await asyncio.gather(
            *(self._dispatch_group(group, shared_webhook_url) for group in grouped.values()),
            return_exceptions=True,
        )

    async def _dispatch_group(
        self,
        group: list[MatchedAlert],
        shared_webhook_url: str,
    ) -> None:
        rep = group[0]
        course = rep.course
        sec = rep.section
        section_label = f"{sec.ssr_component} {sec.section}".strip()
        course_code = f"{course.subject} {course.catalog_nbr}"
        status_pretty = format_status(rep.new_status)
        app_url = f"{self.settings.app_origin}/?highlight={sec.class_nbr}"

        # Load push subscriptions for matched users in one query
        user_ids = sorted({a.user["id"] for a in group})
        placeholders = ",".join("?" for _ in user_ids)
        subs = await self.db.fetch_all(
            f"SELECT id, user_id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id IN ({placeholders})",
            user_ids,
        )

        push_enabled_users = {a.user["id"] for a in group if a.user.get("web_push_enabled", 1)}

        # 1. Push SSE immediately so open browser tabs update instantaneously
        self.sse_hub.publish(
            "seat_alert",
            {
                "roster": course.roster,
                "subject": course.subject,
                "catalog_nbr": course.catalog_nbr,
                "course_title": course.title_long,
                "class_nbr": sec.class_nbr,
                "section_label": section_label,
                "old_status": rep.old_status,
                "new_status": rep.new_status,
                "poll_rtt_ms": rep.poll_rtt_ms,
                "student_center_url": build_student_center_url(),
                "roster_url": build_roster_course_url(course.roster, course.subject, course.catalog_nbr),
            },
            user_ids=set(user_ids),
        )

        # 2. Build concurrent network dispatch tasks (before SQLite audit writes)
        tasks: list[tuple[int, asyncio.Task[DeliveryOutcome]]] = []

        push_title = f"{course_code} ({section_label}) is {status_pretty}!"
        push_body = f"Class #{sec.class_nbr} | {sec.meetings_summary} | Tap to grab seat"
        for sub in subs:
            if sub["user_id"] not in push_enabled_users:
                continue
            tasks.append(
                (
                    sub["user_id"],
                    asyncio.create_task(
                        self.web_push.send(
                            subscription=sub,
                            title=push_title,
                            body=push_body,
                            url=app_url,
                            class_nbr=sec.class_nbr,
                            tag=f"cs-{course.roster}-{sec.class_nbr}",
                        )
                    ),
                )
            )

        # Coalesced shared Discord channel ping
        shared_mentions: list[str] = []
        shared_user_ids: list[int] = []
        seen_users_shared: set[int] = set()
        for a in group:
            uid = a.user["id"]
            if uid in seen_users_shared:
                continue
            d_uid = a.user.get("discord_user_id")
            if a.user.get("discord_ping_enabled", 1) and is_valid_discord_user_id(d_uid):
                seen_users_shared.add(uid)
                shared_mentions.append(str(d_uid).strip())
                shared_user_ids.append(uid)

        if shared_webhook_url and shared_mentions:
            payload = self.discord.build_seat_payload(
                roster=course.roster,
                subject=course.subject,
                catalog_nbr=course.catalog_nbr,
                course_title=course.title_long,
                section_label=section_label,
                class_nbr=sec.class_nbr,
                old_status=rep.old_status,
                new_status=rep.new_status,
                meetings_summary=sec.meetings_summary,
                instructors_summary=sec.instructors_summary,
                mention_user_ids=shared_mentions,
                poll_rtt_ms=rep.poll_rtt_ms,
                app_origin=self.settings.app_origin,
            )
            shared_coro = self.discord.send_payload(
                webhook_url=shared_webhook_url,
                payload=payload,
                channel_kind="discord_shared",
            )
            # Associate delivery log with the first mentioned user (or log per mentioned user below)
            tasks.append((shared_user_ids[0], asyncio.create_task(shared_coro)))

        # Optional private per-user webhooks
        seen_personal: set[int] = set()
        for a in group:
            uid = a.user["id"]
            if uid in seen_personal:
                continue
            personal_url = (a.user.get("personal_webhook_url") or "").strip()
            if self.settings.allow_custom_personal_webhooks and is_valid_discord_webhook_url(personal_url):
                seen_personal.add(uid)
                mention_list = [str(a.user["discord_user_id"]).strip()] if is_valid_discord_user_id(a.user.get("discord_user_id")) else []
                p_payload = self.discord.build_seat_payload(
                    roster=course.roster,
                    subject=course.subject,
                    catalog_nbr=course.catalog_nbr,
                    course_title=course.title_long,
                    section_label=section_label,
                    class_nbr=sec.class_nbr,
                    old_status=rep.old_status,
                    new_status=rep.new_status,
                    meetings_summary=sec.meetings_summary,
                    instructors_summary=sec.instructors_summary,
                    mention_user_ids=mention_list,
                    poll_rtt_ms=rep.poll_rtt_ms,
                    app_origin=self.settings.app_origin,
                )
                tasks.append(
                    (
                        uid,
                        asyncio.create_task(
                            self.discord.send_payload(
                                webhook_url=personal_url,
                                payload=p_payload,
                                channel_kind="discord_personal",
                            )
                        ),
                    )
                )

        outcomes: list[tuple[int, DeliveryOutcome]] = []
        if tasks:
            results = await asyncio.gather(*(t for _, t in tasks), return_exceptions=True)
            for (uid, _), res in zip(tasks, results):
                if isinstance(res, DeliveryOutcome):
                    outcomes.append((uid, res))
                else:
                    outcomes.append(
                        (
                            uid,
                            DeliveryOutcome(
                                channel_kind="unknown",
                                status="failed",
                                latency_ms=0,
                                error_text=str(res)[:300],
                            ),
                        )
                    )

        # 3. Persist audit trail + prune expired push subscriptions
        async with self.db.write_tx() as conn:
            cur = await conn.execute(
                """
                INSERT INTO status_events (
                    roster, subject, catalog_nbr, class_nbr, section_label,
                    old_status, new_status, poll_rtt_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    course.roster,
                    course.subject,
                    course.catalog_nbr,
                    sec.class_nbr,
                    section_label,
                    rep.old_status,
                    rep.new_status,
                    rep.poll_rtt_ms,
                ),
            )
            event_id = cur.lastrowid

            for uid, out in outcomes:
                await conn.execute(
                    """
                    INSERT INTO delivery_logs (
                        event_id, user_id, channel_kind, status, latency_ms, error_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, uid, out.channel_kind, out.status, out.latency_ms, out.error_text),
                )
                if out.status == "pruned" and out.subscription_id is not None:
                    await conn.execute("DELETE FROM push_subscriptions WHERE id = ?", (out.subscription_id,))

    async def send_test_alerts(self, user: dict[str, Any], target: str = "all") -> list[dict[str, Any]]:
        """Send test notifications for Web Push and/or Discord so users can verify setup."""
        results: list[dict[str, Any]] = []

        if target in {"all", "web_push"}:
            subs = await self.db.fetch_all(
                "SELECT id, endpoint, p256dh, auth, device_label FROM push_subscriptions WHERE user_id = ?",
                (user["id"],),
            )
            if not subs and target == "web_push":
                results.append(
                    {"channel": "web_push", "status": "skipped", "detail": "No browser/PWA push subscription registered yet."}
                )
            for sub in subs:
                out = await self.web_push.send(
                    subscription=sub,
                    title="ClassSniper Test Alert",
                    body=f"Push notifications are working on {sub['device_label']}!",
                    url=self.settings.app_origin,
                    tag="classsniper-test",
                )
                if out.status == "pruned" and out.subscription_id is not None:
                    await self.db.execute("DELETE FROM push_subscriptions WHERE id = ?", (out.subscription_id,))
                results.append(
                    {
                        "channel": f"web_push ({sub['device_label']})",
                        "status": out.status,
                        "latency_ms": out.latency_ms,
                        "detail": out.error_text or "Delivered",
                    }
                )

        if target in {"all", "discord"}:
            shared_url = await self.get_shared_discord_webhook_url()
            d_uid = user.get("discord_user_id")
            if shared_url and is_valid_discord_user_id(d_uid):
                payload = self.discord.build_seat_payload(
                    roster="SP27",
                    subject="TEST",
                    catalog_nbr="1010",
                    course_title="ClassSniper Ping Verification",
                    section_label="LEC 001",
                    class_nbr=12345,
                    old_status="C",
                    new_status="O",
                    meetings_summary="MWF 10:10AM-11:00AM",
                    instructors_summary="Test Bot",
                    mention_user_ids=[str(d_uid)],
                    poll_rtt_ms=1,
                    app_origin=self.settings.app_origin,
                )
                out = await self.discord.send_payload(shared_url, payload, channel_kind="discord_shared")
                results.append(
                    {
                        "channel": "discord_shared",
                        "status": out.status,
                        "latency_ms": out.latency_ms,
                        "detail": out.error_text or "Pinged your Discord User ID in shared channel",
                    }
                )
            elif target == "discord":
                reason = "Shared Discord webhook URL not set by admin" if not shared_url else "Enter a valid 17-19 digit Discord User ID first"
                results.append({"channel": "discord_shared", "status": "skipped", "detail": reason})

            personal_url = (user.get("personal_webhook_url") or "").strip()
            if self.settings.allow_custom_personal_webhooks and is_valid_discord_webhook_url(personal_url):
                mention_list = [str(d_uid)] if is_valid_discord_user_id(d_uid) else []
                payload = self.discord.build_seat_payload(
                    roster="SP27",
                    subject="TEST",
                    catalog_nbr="1010",
                    course_title="ClassSniper Personal Webhook Test",
                    section_label="LEC 001",
                    class_nbr=12345,
                    old_status="C",
                    new_status="O",
                    meetings_summary="MWF 10:10AM-11:00AM",
                    instructors_summary="Test Bot",
                    mention_user_ids=mention_list,
                    poll_rtt_ms=1,
                    app_origin=self.settings.app_origin,
                )
                out = await self.discord.send_payload(personal_url, payload, channel_kind="discord_personal")
                results.append(
                    {
                        "channel": "discord_personal",
                        "status": out.status,
                        "latency_ms": out.latency_ms,
                        "detail": out.error_text or "Sent to personal webhook",
                    }
                )

        return results
