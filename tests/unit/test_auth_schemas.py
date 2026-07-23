import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, SignUpRequest


def test_signup_normalizes_email_and_accepts_strong_password():
    value = SignUpRequest(full_name="Alex Morgan", email=" ALEX@Example.com ", password="StrongPassword1", confirm_password="StrongPassword1")
    assert value.email == "alex@example.com"


@pytest.mark.parametrize("change", [
    {"email": "invalid"},
    {"password": "weakpassword", "confirm_password": "weakpassword"},
    {"confirm_password": "DifferentPass1"},
])
def test_signup_rejects_invalid_fields(change):
    values = dict(full_name="Alex Morgan", email="alex@example.com", password="StrongPassword1", confirm_password="StrongPassword1")
    values.update(change)
    with pytest.raises(ValidationError):
        SignUpRequest(**values)


def test_login_validates_and_normalizes_email():
    assert LoginRequest(email="USER@EXAMPLE.COM", password="x").email == "user@example.com"
    with pytest.raises(ValidationError):
        LoginRequest(email="bad", password="x")
