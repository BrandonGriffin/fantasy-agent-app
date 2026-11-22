from pydantic import Field, FilePath, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    espn_s2: SecretStr | None = None
    espn_swid: SecretStr | None = None
    draftkings_cookie: SecretStr | None = None
    draftkings_username: str | None = None
    draftkings_draft_group_ids: list[int] = []
    draftkings_max_concurrent_requests: int = Field(default=4, gt=0)
    draftkings_replay_db: FilePath | None = None
    underdog_token: SecretStr | None = None
    google_sheet_publish_id: SecretStr | None = None
    google_sheet_teams_gid: str | None = None
    google_sheet_adp_gid: str | None = None
