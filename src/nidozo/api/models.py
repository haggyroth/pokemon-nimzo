"""Pydantic request / response models for the Nidozo API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StartBattleRequest(BaseModel):
    p1_provider: str = "random"
    p2_provider: str = "random"
    p1_model: str | None = None
    p2_model: str | None = None
    model: str | None = None
    prompt_version: str = "v2"
    n_battles: int = Field(1, ge=1, le=50)
    tier: str = "random"   # "random" | "ou" | "ubers" | "uu" | "nu" | "lc" | "freeforall"
    draft: bool = False    # If True and tier != "random", run LLM draft phase first
    # Optional coach model per player (None = no coach)
    p1_coach_provider: str | None = None
    p1_coach_model: str | None = None
    p2_coach_provider: str | None = None
    p2_coach_model: str | None = None


class StartBattleResponse(BaseModel):
    battle_ids: list[int]
    message: str


class PlayerSpec(BaseModel):
    provider: str
    model: str | None = None
    # Optional coach — None means this player acts without advisory
    coach_provider: str | None = None
    coach_model: str | None = None


class StartTournamentRequest(BaseModel):
    players: list[PlayerSpec] = Field(..., min_length=2, max_length=12)
    rounds: int = Field(1, ge=1, le=10)
    prompt_version: str = "v2"
    tier: str = "random"   # "random" | "ou" | "ubers" | "uu" | "nu" | "lc" | "freeforall"
    draft: bool = False    # If True and tier != "random", run LLM draft phase before each battle
    tournament_format: str = "round_robin"  # "round_robin" | "single_elim" | "double_elim"


class StartTournamentResponse(BaseModel):
    tournament_id: int
    battle_ids: list[int]
    total_battles: int
    message: str


class StartSeasonRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    players: list[PlayerSpec] = Field(..., min_length=2, max_length=12)
    rounds: int = Field(1, ge=1, le=10)
    prompt_version: str = "v4"
    tier: str = "random"
    draft: bool = False


class StartSeasonResponse(BaseModel):
    season_id: int
    battle_ids: list[int]
    total_battles: int
    message: str
