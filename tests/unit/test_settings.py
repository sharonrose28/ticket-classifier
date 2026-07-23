import pytest
from pydantic import ValidationError

from app.core.settings import Settings


def test_settings_normalize_environment_and_models():
    settings = Settings(
        app_env=" Production ",
        openai_primary_model=" gpt-4.1 ",
        cors_allowed_origins=["https://example.com"],
        auth_cookie_secure=True,
    )
    assert settings.app_env == "production"
    assert settings.openai_primary_model == "gpt-4.1"


def test_settings_normalize_railway_postgres_url():
    settings = Settings(database_url="postgresql://user:password@host:5432/database")
    assert settings.database_url.startswith("postgresql+asyncpg://")


@pytest.mark.parametrize(
    "values",
    [
        {"app_env": "production", "debug": True},
        {"cors_allowed_origins": ["*"], "cors_allow_credentials": True},
        {"openai_primary_model": "   "},
        {"app_env": "production", "auth_cookie_secure": False},
    ],
)
def test_settings_reject_unsafe_configuration(values):
    with pytest.raises(ValidationError):
        Settings(**values)
