from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


ConferenceMode = Literal["PxP", "OxP", "S|L", "S|L Auto"]
ConferenceAccess = Literal["private", "public"]
ScheduleType = Literal["none", "once", "week"]
VideoQuality = Literal["180p", "360p", "540p", "720p", "1080p"]
WeekDay = Literal[
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
]


class ConferenceSchedule(BaseModel):
    type: ScheduleType
    start_time: int | None = None
    duration: int | None = None
    days: list[WeekDay] | None = None
    time: str | None = None
    special_time_offset: int | None = None


class ConferenceInvitationCreate(BaseModel):
    id: str
    display_name: str | None = None
    is_moderator: bool | None = None


class ConferenceCreate(BaseModel):
    topic: str
    owner: str
    mode: ConferenceMode
    access: ConferenceAccess = "private"
    id: str | None = None
    description: str | None = None
    schedule: ConferenceSchedule = Field(
        default_factory=lambda: ConferenceSchedule(type="none")
    )
    invitations: list[ConferenceInvitationCreate] | None = None
    allow_guests: bool = False
    auto_invite: int | None = None
    auto_termination_enabled: bool | None = None
    broadcast_enabled: bool | None = None
    broadcast_id: str | None = None
    max_participants: int | None = None
    max_podiums: int | None = None
    on_join_mute_camera: bool | None = None
    on_join_mute_mic: bool | None = None
    pin: str | None = None
    recording_enabled: bool | None = None
    tags: list[str] | None = None
    waiting_room_enabled: bool | None = None


class ConferenceUpdate(BaseModel):
    topic: str | None = None
    owner: str | None = None
    mode: ConferenceMode | None = None
    access: ConferenceAccess | None = None
    description: str | None = None
    schedule: ConferenceSchedule | None = None
    allow_guests: bool | None = None
    auto_invite: int | None = None
    auto_termination_enabled: bool | None = None
    broadcast_enabled: bool | None = None
    broadcast_id: str | None = None
    max_participants: int | None = None
    max_podiums: int | None = None
    on_join_mute_camera: bool | None = None
    on_join_mute_mic: bool | None = None
    pin: str | None = None
    recording_enabled: bool | None = None
    tags: list[str] | None = None
    waiting_room_enabled: bool | None = None


class ConferenceSearchFilters(BaseModel):
    topic: str | None = None
    owner: str | None = None
    state: str | None = None
    access: str | None = None
    mode: str | None = None
    page: int | None = None
    page_size: int | None = None
    sort_field: str | None = None
    sort_order: int | None = None
    timezone: str | None = None
    after: int | None = None
    before: int | None = None
    topic_cid_contains: str | None = None
    invitation: str | None = None
    registration_enabled: bool | None = None


class ConferenceInvitationUpdate(BaseModel):
    display_name: str | None = None


class ConferenceNotifyRequest(BaseModel):
    invitations: list[str] | None = None


class ConferenceRegistrationField(BaseModel):
    value: str


class ConferenceRegistrationRequest(BaseModel):
    fields: dict[str, ConferenceRegistrationField] | None = None
    send_email: bool = True

# ── Query parameter filters ────────────────────────────────────────────


class ConferenceParticipantsFilters(BaseModel):
    is_in_conf: bool | None = None
    display_name: str | None = None
    call_id: str | None = None
    page: int | None = None
    page_size: int | None = None


class RecordingSearchFilters(BaseModel):
    page: int | None = None
    page_size: int | None = None
    date_from: int | None = None
    date_to: int | None = None
    name: str | None = None
    owner: str | None = None
    topic: str | None = None


class ChatExportFilters(BaseModel):
    date_from: int | None = None
    date_to: int | None = None
    from_call_id: str | None = None
    to_call_id: str | None = None
    message: str | None = None
    session_id: str | None = None


class DeepLinksFilters(BaseModel):
    case: str | None = None
    user: str | None = None


class CalculateConferencesFilters(BaseModel):
    access: ConferenceAccess | None = None
    multicast_enabled: bool | None = None
