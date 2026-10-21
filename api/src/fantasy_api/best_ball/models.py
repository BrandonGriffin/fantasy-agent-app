from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Platform(StrEnum):
    DRAFTKINGS = "DraftKings"
    DRAFTERS = "Drafters"
    UNDERDOG = "Underdog"


class DraftPick(BaseModel):
    model_config = ConfigDict(frozen=True)

    round: int
    overall: int
    name: str
    slot: str  # roster slot by draft order, e.g. "RB1", "WR3"
    nfl_team: str


class DraftedTeam(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: Platform
    league_id: str
    league_type: str
    league_name: str
    # TODO(step 5): sheet sends "$3.00" and "2/11/26" / "2/11/2026"; plain types reject those.
    entry_fee: Decimal
    draft_speed: str
    draft_date: date
    draft_pick: int
    draft_url: str
    tags: str | None = None
    notes: str | None = None
    picks: list[DraftPick]
