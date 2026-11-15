"""Demo configuration guards; importing the seed must never connect to a database."""
from dataclasses import replace

import pytest

from medicore.domain.enums import Role
from medicore.domain.shared.errors import QuotaExceeded
from scripts import seed_demo as seed


def test_demo_staff_fits_each_plan():
    seed._check_demo_seats()


def test_over_capacity_is_rejected_before_opening_database(monkeypatch):
    solo = seed.DEMO_CLINICS[-1]
    extra = ("Extra Support", "extra", Role.RECEPTIONIST, None, True)
    monkeypatch.setattr(seed, "DEMO_CLINICS", (replace(solo, staff=(*solo.staff, extra)),))
    monkeypatch.setattr(seed, "_check_demo_password", lambda: None)
    monkeypatch.setattr("sys.argv", ["seed_demo.py", "--reset"])

    def unexpected_connection():
        pytest.fail("quota guard must run before opening any database connection")

    monkeypatch.setattr(seed, "get_session_factory", unexpected_connection)
    with pytest.raises(QuotaExceeded, match="quota_support_users"):
        seed.main()


def test_invited_user_counts_toward_capacity(monkeypatch):
    solo = replace(seed.DEMO_CLINICS[-1], invited=("Extra Support", "extra"))
    monkeypatch.setattr(seed, "DEMO_CLINICS", (solo,))
    with pytest.raises(QuotaExceeded, match="quota_support_users"):
        seed._check_demo_seats()
