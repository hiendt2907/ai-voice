"""Notifier factory — resolves platform from config."""

from __future__ import annotations

from notify.base import ChatNotifier
from notify.teams import TeamsNotifier
from notify.telegram import TelegramNotifier


def get_notifier(
    platform: str,
    teams_webhook_url: str = "",
    telegram_bot_token: str = "",
    telegram_group_id: str = "",
) -> ChatNotifier:
    if platform == "teams":
        if not teams_webhook_url:
            raise ValueError("teams_webhook_url is required for Teams notifier")
        return TeamsNotifier(teams_webhook_url)
    if platform == "telegram":
        if not telegram_bot_token or not telegram_group_id:
            raise ValueError("telegram_bot_token and telegram_group_id are required")
        return TelegramNotifier(telegram_bot_token, telegram_group_id)
    raise ValueError(f"Unknown notify platform: {platform!r}")
