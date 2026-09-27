"""Content-free push notifications via ntfy or Telegram (FR-29). Failures never fail a run."""

from __future__ import annotations

import os

import httpx

from . import log
from .context import Ctx


def configured() -> list[str]:
    out = []
    if os.environ.get("PBS_NTFY_TOPIC"):
        out.append("ntfy")
    if os.environ.get("PBS_TELEGRAM_BOT_TOKEN") and os.environ.get("PBS_TELEGRAM_CHAT_ID"):
        out.append("telegram")
    return out


def send(ctx: Ctx, title: str, message: str, tags: str = "memo", client: httpx.Client | None = None) -> bool:
    channels = configured()
    if not channels:
        return False
    click = ctx.settings.notify.desk_url or os.environ.get("PBS_DESK_URL", "")
    sent = False
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        if "ntfy" in channels:
            server = os.environ.get("PBS_NTFY_SERVER", "https://ntfy.sh").rstrip("/")
            headers = {"Title": title, "Tags": tags}
            if click:
                headers["Click"] = click
            try:
                r = client.post(f"{server}/{os.environ['PBS_NTFY_TOPIC']}", content=message.encode("utf-8"),
                                headers=headers)
                sent = sent or r.status_code < 300
            except httpx.HTTPError as exc:
                log.warn(f"notify: ntfy failed ({type(exc).__name__})")
        if "telegram" in channels:
            token, chat = os.environ["PBS_TELEGRAM_BOT_TOKEN"], os.environ["PBS_TELEGRAM_CHAT_ID"]
            text = f"{title}\n{message}" + (f"\n{click}" if click else "")
            try:
                r = client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                json={"chat_id": chat, "text": text, "disable_web_page_preview": True})
                sent = sent or r.status_code < 300
            except httpx.HTTPError as exc:
                log.warn(f"notify: telegram failed ({type(exc).__name__})")
    finally:
        if own:
            client.close()
    return sent


def delivery_message(counts: dict[str, int], needs_input: int, degraded: str | None) -> tuple[str, str]:
    li, x = counts.get("linkedin", 0), counts.get("x", 0)
    msg = f"{li} LinkedIn and {x} X cards are on your desk"
    if needs_input:
        msg += f" ({needs_input} need{'s' if needs_input == 1 else ''} your input)"
    msg += "."
    if degraded:
        msg += " Some drafts were skipped because of free-tier limits."
    return "Drafts ready", msg
