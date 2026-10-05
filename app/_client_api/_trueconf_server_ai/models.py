"""Pydantic models for the TrueConf AI Server user API.

Field names follow the AI Server JSON (snake_case) — confirmed by a live
probe on 2026-10-01 (see plan spec notes).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class AiTokenPair(BaseModel):
    """Response of POST /api/user/v1/auth/from-tcs and /auth/refresh."""

    access_token: str
    access_token_expires_at: str | None = None
    refresh_token: str
    refresh_token_expires_at: str | None = None


class TranscriptionListFilters(BaseModel):
    """Query params for GET /api/user/v1/transcriptions."""

    page: int | None = None
    page_size: int | None = None
    search: str | None = None
    status: int | None = None
    conference_id: str | None = None
    sort_field: str | None = None  # created_at | display_name | duration | started_at
    sort_order: int | None = None  # 0=ascending, 1=descending (UI default: 1)


class TranscriptionLinesFilters(BaseModel):
    """Query params for GET /api/user/v1/transcriptions/{id}/lines.

    Only params present in the AI Server request schema; page_size is not
    part of it (the server silently ignores it) — verified live 2026-10-05.
    """

    page: int | None = None
    language: str | None = None


# ── Response / Output models ──────────────────────────────────────────


# Transcription status ids returned by the AI Server list/detail endpoints.
# Values confirmed from the AI Server UI bundle and live API (2026-10-05):
# 3 — not recognized, 6 — recognizing, 8 — recognized. Labels follow the
# API enum terminology (recognition_status: recognized | not_recognized).
_TRANSCRIPTION_STATUS_LABELS: dict[int, str] = {
    3: "not recognized",
    6: "recognizing",
    8: "recognized",
}


class TranscriptionOutput(BaseModel):
    """Single transcription details with AI-friendly fields."""

    model_config = ConfigDict(extra="ignore")

    transcription_id: int | None = Field(
        default=None, validation_alias="id", description="Unique transcription identifier"
    )
    conference_id: str | None = None
    session_id: str | None = None
    conference_name: str | None = Field(
        default=None, validation_alias="display_name", description="Conference name / topic"
    )
    duration: float | int | None = None
    language: str | None = None
    transcription_status_id: int | None = None
    recognition_progress: int | None = None
    finished_at: str | None = None
    access_level: str | None = None
    tcs_id: int | None = None
    status_note: str | None = None
    audio_url: str | None = None
    transcription_url: str | None = None
    created_at: str | None = None
    started_at: str | None = None

    @computed_field
    @property
    def status(self) -> str | None:
        """Human-readable status label for the LLM (3/6/8 → not recognized/recognizing/recognized)."""
        if self.transcription_status_id is None:
            return None
        return _TRANSCRIPTION_STATUS_LABELS.get(self.transcription_status_id, str(self.transcription_status_id))

    @computed_field
    @property
    def id(self) -> int | None:
        return self.transcription_id

    @computed_field
    @property
    def display_name(self) -> str | None:
        return self.conference_name

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "transcription" in data and isinstance(data["transcription"], dict):
                data = data["transcription"]
            else:
                data = dict(data)
            if "transcription_id" in data and "id" not in data:
                data["id"] = data["transcription_id"]
            if "conference_name" in data and "display_name" not in data:
                data["display_name"] = data["conference_name"]
        return data


class TranscriptionListOutput(BaseModel):
    """List of transcriptions."""

    model_config = ConfigDict(extra="ignore")

    transcriptions: list[TranscriptionOutput] = Field(default_factory=list)
    page: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"transcriptions": data}
        return data


class TranscriptionLineOutput(BaseModel):
    """Single spoken replica in transcription lines.

    Field names mirror the real GET /transcriptions/{id}/lines response:
    call_id (speaker login), display_name (speaker name), line (text),
    start_time/end_time (seconds), language, transcription_id, user_id.
    Verified against the AI Server UI bundle (2026-10-05).
    """

    model_config = ConfigDict(extra="ignore")

    call_id: str | None = None
    display_name: str | None = None
    id: int | None = None
    language: str | None = None
    line: str | None = None
    start_time: float | int | None = None
    end_time: float | int | None = None
    transcription_id: int | None = None
    user_id: int | None = None


class TranscriptionLinesOutput(BaseModel):
    """List of spoken lines in a transcription."""

    model_config = ConfigDict(extra="ignore")

    lines: list[TranscriptionLineOutput] = Field(default_factory=list)
    page: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"lines": data}
        return data


class TranscriptionSummaryOutput(BaseModel):
    """Summary of a transcription."""

    model_config = ConfigDict(extra="ignore")

    summaries: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"summaries": data}
        return data
