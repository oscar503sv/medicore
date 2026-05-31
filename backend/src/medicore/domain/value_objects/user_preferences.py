"""UserPreferences value object (embedded in User)."""

from __future__ import annotations

from dataclasses import dataclass, field

from medicore.domain.enums import LangPref, NotificationChannel, ThemePref


@dataclass(frozen=True, slots=True)
class NotificationPreferences:
    """Per-topic delivery channel for notifications."""

    appointments: NotificationChannel = NotificationChannel.EMAIL
    reminders: NotificationChannel = NotificationChannel.EMAIL
    lab_results: NotificationChannel = NotificationChannel.EMAIL
    internal_messages: NotificationChannel = NotificationChannel.PUSH
    weekly_reports: NotificationChannel = NotificationChannel.NONE


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """User UI and notification preferences."""

    theme: ThemePref = ThemePref.SYSTEM
    language: LangPref = LangPref.ES
    notifications: NotificationPreferences = field(default_factory=NotificationPreferences)
