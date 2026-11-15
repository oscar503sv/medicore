import pytest

from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.record_seal import RecordSeal

DIGEST = "0123456789abcdef" * 4


def test_a_seal_has_a_version_and_a_digest():
    seal = RecordSeal(1, DIGEST)
    assert (seal.version, seal.digest) == (1, DIGEST)
    assert seal.fingerprint == "0123456789abcdef"


@pytest.mark.parametrize("version", [0, -1])
def test_the_version_starts_at_one(version):
    with pytest.raises(InvalidValueObject) as exc:
        RecordSeal(version, DIGEST)
    assert exc.value.code == "record.seal_invalid"


@pytest.mark.parametrize("digest", ["", "abc", DIGEST.upper(), DIGEST + "0", "g" * 64])
def test_the_digest_is_64_lowercase_hex_characters(digest):
    with pytest.raises(InvalidValueObject) as exc:
        RecordSeal(1, digest)
    assert exc.value.code == "record.seal_invalid"
