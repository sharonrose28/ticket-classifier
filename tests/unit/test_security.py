import time
import uuid

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_round_trip_and_random_salts():
    first = hash_password("StrongPassword123")
    second = hash_password("StrongPassword123")
    assert first != second
    assert verify_password("StrongPassword123", first)
    assert not verify_password("wrong", first)


def test_password_verifier_rejects_malformed_hashes():
    assert not verify_password("x", "bad")
    assert not verify_password("x", "unknown$1$eA$eA")


def test_jwt_round_trip_tampering_and_expiry(monkeypatch):
    user_id = uuid.uuid4()
    token = create_access_token(subject=user_id, secret="secret", lifetime_seconds=60)
    assert decode_access_token(token, secret="secret").subject == user_id
    assert decode_access_token(token + "x", secret="secret") is None
    assert decode_access_token("bad", secret="secret") is None
    monkeypatch.setattr(time, "time", lambda: 9_999_999_999)
    assert decode_access_token(token, secret="secret") is None
