"""BcryptPasswordHasher against the real bcrypt library (few calls: bcrypt is slow on purpose)."""

from __future__ import annotations

import pytest

from medicore.infrastructure.auth import bcrypt_hasher
from medicore.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher


def _count_calls(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    original = getattr(bcrypt_hasher.bcrypt, name)
    calls: list[int] = []

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(bcrypt_hasher.bcrypt, name, counting)
    return calls


def test_dummy_hash_is_computed_once_per_process(monkeypatch):
    bcrypt_hasher._dummy_hash.cache_clear()
    try:
        hashes = _count_calls(monkeypatch, "hashpw")

        BcryptPasswordHasher().dummy_verify("a")
        BcryptPasswordHasher().dummy_verify("b")

        assert len(hashes) == 1
    finally:
        bcrypt_hasher._dummy_hash.cache_clear()


def test_dummy_verify_runs_one_check_and_never_succeeds(monkeypatch):
    checks = _count_calls(monkeypatch, "checkpw")
    hasher = BcryptPasswordHasher()

    assert hasher.dummy_verify(bcrypt_hasher._DUMMY_SECRET.decode()) is None
    assert hasher.dummy_verify("whatever") is None

    assert len(checks) == 2


def test_dummy_hash_has_same_cost_as_real_hashes():
    real = BcryptPasswordHasher().hash("secret")

    assert bcrypt_hasher._dummy_hash().startswith(b"$2b$12$")
    assert real.startswith("$2b$12$")


def test_hash_and_verify_roundtrip():
    hasher = BcryptPasswordHasher()
    hashed = hasher.hash("secret")

    assert hasher.verify("secret", hashed) is True
    assert hasher.verify("other", hashed) is False


def test_verify_with_malformed_hash_is_false():
    assert BcryptPasswordHasher().verify("secret", "not-a-bcrypt-hash") is False
