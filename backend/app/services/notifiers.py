"""Web Push (VAPID) and Discord Webhook notification transports."""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from pywebpush import WebPushException, webpush

DISCORD_ID_RE = re.compile(r"^\d{15,22}$")
STATUS_LABELS = {
    "O": "OPEN",
    "C": "CLOSED",
    "W": "WAITLIST",
}


def format_status(code: Optional[str]) -> str:
    if not code:
        return "UNKNOWN"
    return STATUS_LABELS.get(code.upper(), code.upper())


def is_valid_discord_user_id(user_id: Optional[str]) -> bool:
    return bool(user_id and DISCORD_ID_RE.match(user_id.strip()))


def is_valid_discord_webhook_url(url: Optional[str]) -> bool:
    if not url:
        return False
    parsed = urlparse(url.strip())
    return (
        parsed.scheme == "https"
        and parsed.netloc in {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}
        and parsed.path.startswith("/api/webhooks/")
    )


@dataclass(slots=True)
class DeliveryOutcome:
    channel_kind: str
    status: str  # "sent" | "failed" | "pruned"
    latency_ms: int
    error_text: str = ""
    subscription_id: int | None = None


def build_student_center_url() -> str:
    return "https://studentcenter.cornell.edu"


def build_roster_course_url(roster: str, subject: str, catalog_nbr: str) -> str:
    return f"https://classes.cornell.edu/browse/roster/{roster.upper()}/class/{subject.upper()}/{catalog_nbr}"


class WebPushNotifier:
    """Non-blocking VAPID Web Push sender via pywebpush inside asyncio.to_thread."""

    def __init__(self, vapid_private_key: str, vapid_subject: str) -> None:
        self.vapid_private_key = vapid_private_key
        self.vapid_subject = vapid_subject

    async def send(
        self,
        subscription: dict[str, Any],
        title: str,
        body: str,
        url: str,
        class_nbr: int | None = None,
        tag: str = "classsniper-alert",
    ) -> DeliveryOutcome:
        started = time.perf_counter()
        sub_info = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"],
            },
        }
        payload = json.dumps(
            {
                "title": title,
                "body": body,
                "url": url,
                "classNbr": class_nbr,
                "tag": tag,
            }
        )

        def _send_sync() -> None:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=self.vapid_private_key,
                vapid_claims={"sub": self.vapid_subject},
                ttl=300,
                timeout=6,
            )

        try:
            await asyncio.to_thread(_send_sync)
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            return DeliveryOutcome(
                channel_kind="web_push",
                status="sent",
                latency_ms=latency_ms,
                subscription_id=subscription.get("id"),
            )
        except WebPushException as exc:
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 410}:
                return DeliveryOutcome(
                    channel_kind="web_push",
                    status="pruned",
                    latency_ms=latency_ms,
                    error_text=f"Subscription expired (HTTP {status_code})",
                    subscription_id=subscription.get("id"),
                )
            return DeliveryOutcome(
                channel_kind="web_push",
                status="failed",
                latency_ms=latency_ms,
                error_text=str(exc)[:300],
                subscription_id=subscription.get("id"),
            )
        except Exception as exc:
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            return DeliveryOutcome(
                channel_kind="web_push",
                status="failed",
                latency_ms=latency_ms,
                error_text=str(exc)[:300],
                subscription_id=subscription.get("id"),
            )


class DiscordWebhookNotifier:
    """Async Discord Webhook sender supporting coalesced user @mentions."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(6.0, connect=4.0),
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def build_seat_payload(
        roster: str,
        subject: str,
        catalog_nbr: str,
        course_title: str,
        section_label: str,
        class_nbr: int,
        old_status: Optional[str],
        new_status: str,
        meetings_summary: str,
        instructors_summary: str,
        mention_user_ids: list[str],
        poll_rtt_ms: int = 0,
        app_origin: str = "",
    ) -> dict[str, Any]:
        """Construct Discord webhook payload with safe user mentions in top-level content."""
        valid_ids: list[str] = []
        seen: set[str] = set()
        for uid in mention_user_ids:
            uid_clean = uid.strip()
            if is_valid_discord_user_id(uid_clean) and uid_clean not in seen:
                seen.add(uid_clean)
                valid_ids.append(uid_clean)

        mentions_str = " ".join(f"<@{uid}>" for uid in valid_ids)
        status_pretty = format_status(new_status)
        old_pretty = format_status(old_status) if old_status else "TRACKED"
        course_code = f"{subject.upper()} {catalog_nbr}"

        headline = f"**{course_code} ({section_label})** is now **{status_pretty}** — Class #`{class_nbr}`"
        content = f"{mentions_str} {headline}".strip()

        color = 0x22C55E if new_status.upper() == "O" else 0xF59E0B
        roster_url = build_roster_course_url(roster, subject, catalog_nbr)
        student_center_url = build_student_center_url()

        fields = [
            {"name": "Class Nbr", "value": f"`{class_nbr}`", "inline": True},
            {"name": "Transition", "value": f"{old_pretty} -> **{status_pretty}**", "inline": True},
            {"name": "Term", "value": roster.upper(), "inline": True},
            {"name": "Schedule", "value": meetings_summary or "TBA", "inline": True},
            {"name": "Instructor", "value": instructors_summary or "Staff", "inline": True},
            {
                "name": "Quick Enroll",
                "value": f"[Student Center]({student_center_url}) | [Class Roster]({roster_url})",
                "inline": False,
            },
        ]
        if app_origin:
            fields.append({"name": "Dashboard", "value": f"[Open ClassSniper]({app_origin})", "inline": False})

        return {
            "username": "ClassSniper",
            "content": content,
            "allowed_mentions": {"parse": [], "users": valid_ids},
            "embeds": [
                {
                    "title": f"{course_code}: {course_title}",
                    "description": f"Section **{section_label}** changed to **{status_pretty}**.",
                    "color": color,
                    "fields": fields,
                    "footer": {"text": f"Cornell Poll RTT: {poll_rtt_ms}ms"},
                }
            ],
        }

    async def send_payload(
        self,
        webhook_url: str,
        payload: dict[str, Any],
        channel_kind: str = "discord_shared",
    ) -> DeliveryOutcome:
        started = time.perf_counter()
        if not is_valid_discord_webhook_url(webhook_url):
            return DeliveryOutcome(
                channel_kind=channel_kind,
                status="failed",
                latency_ms=0,
                error_text="Invalid Discord webhook URL",
            )
        try:
            resp = await self._client.post(webhook_url.strip(), json=payload)
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            if 200 <= resp.status_code < 300:
                return DeliveryOutcome(
                    channel_kind=channel_kind,
                    status="sent",
                    latency_ms=latency_ms,
                )
            return DeliveryOutcome(
                channel_kind=channel_kind,
                status="failed",
                latency_ms=latency_ms,
                error_text=f"Discord HTTP {resp.status_code}: {resp.text[:200]}",
            )
        except Exception as exc:
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            return DeliveryOutcome(
                channel_kind=channel_kind,
                status="failed",
                latency_ms=latency_ms,
                error_text=str(exc)[:300],
            )
