"""PlatformAdmin second-factor lifecycle."""

from __future__ import annotations

from datetime import datetime

import pytest

from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.shared.errors import DomainError
from medicore.domain.shared.identifiers import PlatformAdminId

NOW = datetime(2026, 11, 14, 9, 0)


def _admin() -> PlatformAdmin:
    return PlatformAdmin(
        id=PlatformAdminId.new(), name="Super", email="s@medicore.test", password_hash="h"
    )


def test_mfa_is_off_by_default():
    assert not _admin().mfa_enabled


def test_enrollment_only_enables_after_confirmation():
    admin = _admin()
    admin.start_mfa_enrollment("sealed")
    assert not admin.mfa_enabled and admin.mfa_pending_secret == "sealed"
    admin.confirm_mfa(NOW, 100)
    assert admin.mfa_enabled
    assert admin.mfa_secret == "sealed" and admin.mfa_pending_secret is None
    assert admin.mfa_enabled_at == NOW and admin.mfa_last_step == 100


def test_cannot_enroll_twice():
    admin = _admin()
    admin.start_mfa_enrollment("sealed")
    admin.confirm_mfa(NOW, 1)
    with pytest.raises(DomainError) as exc:
        admin.start_mfa_enrollment("other")
    assert exc.value.code == "mfa.already_enabled"


def test_cannot_confirm_without_starting():
    with pytest.raises(DomainError) as exc:
        _admin().confirm_mfa(NOW, 1)
    assert exc.value.code == "mfa.not_enrolling"


def test_disable_clears_everything():
    admin = _admin()
    admin.start_mfa_enrollment("sealed")
    admin.confirm_mfa(NOW, 1)
    admin.disable_mfa()
    assert not admin.mfa_enabled
    assert (admin.mfa_secret, admin.mfa_pending_secret) == (None, None)
    assert (admin.mfa_enabled_at, admin.mfa_last_step) == (None, None)


def test_a_totp_step_is_accepted_once_and_only_forward():
    admin = _admin()
    assert admin.accept_totp_step(10) is True
    assert admin.accept_totp_step(10) is False
    assert admin.accept_totp_step(9) is False
    assert admin.accept_totp_step(11) is True
    assert admin.mfa_last_step == 11
