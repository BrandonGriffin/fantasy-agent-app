from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    espn_s2: SecretStr | None = None
    espn_swid: SecretStr | None = None
    draftkings_cookie: SecretStr | None = None
    underdog_token: SecretStr | None = None
    google_sheet_publish_id: SecretStr | None = None
    google_sheet_teams_gid: str | None = None
    google_sheet_adp_gid: str | None = None
