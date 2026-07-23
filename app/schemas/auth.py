"""Authentication request contracts."""

import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SignUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not _EMAIL.fullmatch(normalized):
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not (re.search(r"[A-Z]", value) and re.search(r"[a-z]", value) and re.search(r"\d", value)):
            raise ValueError("Password must include uppercase, lowercase, and a number")
        return value

    @model_validator(mode="after")
    def passwords_match(self) -> "SignUpRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not _EMAIL.fullmatch(normalized):
            raise ValueError("Enter a valid email address")
        return normalized
