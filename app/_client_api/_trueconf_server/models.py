from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasPath, BaseModel, ConfigDict, Field, computed_field, model_validator

from app._client_api._trueconf_server.mode_utils import _describe_mode

ConferenceMode = Literal["PxP", "OxP", "S|L", "S|L Auto"]
ConferenceAccess = Literal["private", "public"]
ScheduleType = Literal["none", "once", "week"]
VideoQuality = Literal["180p", "360p", "540p", "720p", "1080p"]
WeekDay = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


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


class ConferenceRegistrationCreate(BaseModel):
    enabled: bool | None = None
    email_verification_required: bool | None = None
    start_at: int | None = None
    end_at: int | None = None
    participants_limit_enabled: bool | None = None
    participants_limit: int | None = None
    allow_users_access: bool | None = None


class ConferenceInvitationAdd(BaseModel):
    """Participant payload for ``POST /conferences/{id}/invitations``.

    InvitationAddEntity exposes only ``id`` and ``display_name`` — an
    ``is_moderator`` field is not part of this endpoint's schema and the
    server silently drops it.
    """

    id: str
    display_name: str | None = None


class ConferenceSAI(BaseModel):
    """Transcription (SAI) settings for a conference.

    Mirrors conference.CreateSAI / PatchSAI / OutputSAI — all three use the
    same field set. All fields optional; the tools build this object only
    from explicitly provided values.
    """

    auto_recognition_enabled: bool | None = None
    recognition_language: str | None = None
    recording_enabled: bool | None = None


class ConferenceCreate(BaseModel):
    topic: str
    owner: str
    mode: ConferenceMode
    access: ConferenceAccess = "private"
    id: str | None = None
    description: str | None = None
    schedule: ConferenceSchedule = Field(default_factory=lambda: ConferenceSchedule(type="none"))
    invitations: list[ConferenceInvitationCreate] | None = None
    registration: ConferenceRegistrationCreate | None = None
    rights: dict[str, dict[str, bool]] | None = None
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
    sai: ConferenceSAI | None = None


class ConferenceUpdate(BaseModel):
    topic: str | None = None
    owner: str | None = None
    mode: ConferenceMode | None = None
    access: ConferenceAccess | None = None
    description: str | None = None
    schedule: ConferenceSchedule | None = None
    rights: dict[str, dict[str, bool]] | None = None
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
    sai: ConferenceSAI | None = None


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


class DeepLinksFilters(BaseModel):
    case: str | None = None
    user: str | None = None


class CalculateConferencesFilters(BaseModel):
    access: ConferenceAccess | None = None
    multicast_enabled: bool | None = None


class AddressBookFilters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    search: str | None = Field(default=None, alias="filter_search")
    page: int | None = Field(default=None, alias="page_id")
    page_size: int | None = None


# ── Response / Output models ──────────────────────────────────────────


class ConferenceOutput(BaseModel):
    """Conference details model with AI-friendly field names and flattened attributes."""

    model_config = ConfigDict(extra="ignore")

    conference_id: str | None = Field(default=None, validation_alias="id", description="Unique conference identifier")
    conference_name: str | None = Field(default=None, validation_alias="topic", description="Conference name / subject")
    owner: str | None = Field(default=None, description="Conference owner user ID")
    description: str | None = None
    status: str | None = Field(
        default=None, validation_alias="state", description="Conference state (running / stopped)"
    )
    conference_mode: str | None = Field(
        default=None, validation_alias="mode", description="Conference mode code (PxP/OxP/S|L/S|L Auto)"
    )
    access: str | None = None
    max_participants: int | None = None
    max_podiums: int | None = None
    recording_enabled: bool | None = None
    broadcast_enabled: bool | None = None
    broadcast_id: str | None = None
    waiting_room_enabled: bool | None = None
    pin: str | None = None
    pin_enabled: bool | None = None
    url: str | None = None
    web_client_url: str | None = None
    created_at: str | None = None
    tags: list[str] | None = None

    schedule_type: str | None = Field(default=None, validation_alias=AliasPath("schedule", "type"))
    schedule_duration: int | None = Field(default=None, validation_alias=AliasPath("schedule", "duration"))
    schedule_days: list[str] | None = Field(default=None, validation_alias=AliasPath("schedule", "days"))
    schedule_start_time: str | int | None = Field(default=None, validation_alias=AliasPath("schedule", "start_time"))
    schedule_time_offset: int | None = Field(
        default=None, validation_alias=AliasPath("schedule", "special_time_offset")
    )

    transcription_enabled: bool | None = Field(default=None, validation_alias=AliasPath("sai", "recording_enabled"))
    transcription_language: str | None = Field(default=None, validation_alias=AliasPath("sai", "recognition_language"))
    transcription_auto_detect: bool | None = Field(
        default=None, validation_alias=AliasPath("sai", "auto_recognition_enabled")
    )

    invitations: list[dict[str, Any]] | None = None
    rights: dict[str, Any] | None = None
    registration: dict[str, Any] | None = None
    connect_urls: dict[str, Any] | None = None
    session_id: str | None = None

    @computed_field
    @property
    def id(self) -> str | None:
        return self.conference_id

    @computed_field
    @property
    def topic(self) -> str | None:
        return self.conference_name

    @computed_field
    @property
    def mode(self) -> str | None:
        """Human-readable conference mode label (PxP → 'all on screen')."""
        return _describe_mode(self.conference_mode)

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "conference" in data and isinstance(data["conference"], dict):
                inner = dict(data["conference"])
                for k, v in data.items():
                    if k != "conference" and k not in inner:
                        inner[k] = v
                data = inner
            else:
                data = dict(data)
            if "status" in data and "state" not in data:
                data["state"] = data["status"]
            if "conference_id" in data and "id" not in data:
                data["id"] = data["conference_id"]
            if "conference_name" in data and "topic" not in data:
                data["topic"] = data["conference_name"]
        return data


class ShortConferenceOutput(BaseModel):
    """Conference summary in conference lists."""

    model_config = ConfigDict(extra="ignore")

    conference_id: str | None = Field(default=None, validation_alias="id", description="Unique conference identifier")
    conference_name: str | None = Field(default=None, validation_alias="topic", description="Conference name / subject")
    owner: str | None = None
    status: str | None = Field(
        default=None, validation_alias="state", description="Conference state (running / stopped)"
    )
    conference_mode: str | None = Field(
        default=None, validation_alias="mode", description="Conference mode code (PxP/OxP/S|L/S|L Auto)"
    )
    access: str | None = None
    recording_enabled: bool | None = None
    created_at: str | None = None

    schedule_type: str | None = Field(default=None, validation_alias=AliasPath("schedule", "type"))
    schedule_duration: int | None = Field(default=None, validation_alias=AliasPath("schedule", "duration"))
    schedule_days: list[str] | None = Field(default=None, validation_alias=AliasPath("schedule", "days"))
    schedule_start_time: str | int | None = Field(default=None, validation_alias=AliasPath("schedule", "start_time"))
    session_id: str | None = None

    @computed_field
    @property
    def id(self) -> str | None:
        return self.conference_id

    @computed_field
    @property
    def topic(self) -> str | None:
        return self.conference_name

    @computed_field
    @property
    def mode(self) -> str | None:
        """Human-readable conference mode label (PxP → 'all on screen')."""
        return _describe_mode(self.conference_mode)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "status" in data and "state" not in data:
                data["state"] = data["status"]
            if "conference_id" in data and "id" not in data:
                data["id"] = data["conference_id"]
            if "conference_name" in data and "topic" not in data:
                data["topic"] = data["conference_name"]
        return data


class ConferenceListOutput(BaseModel):
    """Search/list result of conferences."""

    model_config = ConfigDict(extra="ignore")

    conferences: list[ShortConferenceOutput] = Field(default_factory=list)
    total: int | None = Field(default=None, validation_alias="results")


class InvitationOutput(BaseModel):
    """Participant in conference invitation list."""

    model_config = ConfigDict(extra="ignore")

    invitation_id: str | None = Field(
        default=None, validation_alias="id", description="Participant identifier / user ID"
    )
    display_name: str | None = None
    is_moderator: bool | None = None

    @computed_field
    @property
    def id(self) -> str | None:
        return self.invitation_id

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = data["invitation"] if "invitation" in data and isinstance(data["invitation"], dict) else dict(data)
            if "invitation_id" in data and "id" not in data:
                data["id"] = data["invitation_id"]
        return data


class InvitationListOutput(BaseModel):
    """List of invitations."""

    model_config = ConfigDict(extra="ignore")

    invitations: list[InvitationOutput] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict) and "invitations" in data and isinstance(data["invitations"], list):
            return {"invitations": data["invitations"]}
        return data


class ParticipantOutput(BaseModel):
    """Participant currently or previously connected to a conference."""

    model_config = ConfigDict(extra="ignore")

    participant_id: str | None = Field(default=None, validation_alias="id", description="Participant / connection ID")
    display_name: str | None = None
    role: int | None = Field(default=None, validation_alias="flag")
    duration: int | None = None
    join_time: str | None = None
    leave_time: str | None = None
    app_id: str | None = None
    call_id: str | None = None

    @computed_field
    @property
    def id(self) -> str | None:
        return self.participant_id


class ParticipantListOutput(BaseModel):
    """List of participants with total count."""

    model_config = ConfigDict(extra="ignore")

    participants: list[ParticipantOutput] = Field(default_factory=list, validation_alias="list")
    total: int | None = Field(default=None, validation_alias="cnt")

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"list": data, "cnt": len(data)}
        return data


class ConferenceOwnerOutput(BaseModel):
    """Conference owner account details."""

    model_config = ConfigDict(extra="ignore")

    user_id: str | None = Field(default=None, validation_alias="id", description="Owner user ID")
    display_name: str | None = None
    avatar: str | None = None
    is_active: bool | None = None
    status: int | None = None
    uid: str | None = None

    @computed_field
    @property
    def id(self) -> str | None:
        return self.user_id

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict) and "owner" in data and isinstance(data["owner"], dict):
            return data["owner"]
        return data


class ConferenceMeOutput(BaseModel):
    """Caller's roles in the conference."""

    model_config = ConfigDict(extra="ignore")

    is_owner: bool = Field(default=False, validation_alias="owner")
    is_moderator: bool = Field(default=False, validation_alias="moderator")
    is_operator: bool = Field(default=False, validation_alias="operator")
    is_participant: bool = Field(default=False, validation_alias="participant")

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict) and "conference" in data and isinstance(data["conference"], dict):
            return data["conference"]
        return data


class RecordingOutput(BaseModel):
    """Recording metadata."""

    model_config = ConfigDict(extra="ignore")

    recording_id: int | None = Field(default=None, validation_alias="id", description="Recording ID")
    conference_id: str | None = None
    conference_name: str | None = Field(default=None, validation_alias="topic")
    file_name: str | None = Field(default=None, validation_alias="name")
    owner: str | None = None
    size_bytes: int | None = Field(default=None, validation_alias="size")
    download_url: str | None = None
    stream_url: str | None = None
    started_at: str | None = None
    stopped_at: str | None = None

    @computed_field
    @property
    def id(self) -> int | None:
        return self.recording_id

    @computed_field
    @property
    def topic(self) -> str | None:
        return self.conference_name

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict) and "recording" in data and isinstance(data["recording"], dict):
            return data["recording"]
        return data


class RecordingListOutput(BaseModel):
    """List of conference recordings with total count."""

    model_config = ConfigDict(extra="ignore")

    recordings: list[RecordingOutput] = Field(default_factory=list, validation_alias="list")
    total: int | None = Field(default=None, validation_alias="cnt")

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"list": data, "cnt": len(data)}
        return data


class DeeplinksOutput(BaseModel):
    """Deeplinks for opening conference in TrueConf client apps."""

    model_config = ConfigDict(extra="ignore")

    android: str | None = Field(default=None, validation_alias=AliasPath("deeplinks", "android"))
    default: str | None = Field(default=None, validation_alias=AliasPath("deeplinks", "default"))


class SharedLinksOutput(BaseModel):
    """Embedded and streaming links."""

    model_config = ConfigDict(extra="ignore")

    webrtc_url: str | None = Field(default=None, validation_alias=AliasPath("embedded", "webrtc"))
    rtsp_url: str | None = None


class CalendarsOutput(BaseModel):
    """Calendar integration links."""

    model_config = ConfigDict(extra="ignore")

    google_calendar_url: str | None = Field(default=None, validation_alias=AliasPath("calendars", "google"))
    other_calendar_url: str | None = Field(default=None, validation_alias=AliasPath("calendars", "other"))


class ActionSuccessOutput(BaseModel):
    """Standard success response for action/mutation tools."""

    model_config = ConfigDict(extra="ignore")

    success: bool = True
    status: str = "success"
    conference_id: str | None = None
    message: str | None = None


class RegistrationOutput(BaseModel):
    """Webinar registration result."""

    model_config = ConfigDict(extra="ignore")

    email_notification_created: bool | None = None
    registration_token: str | None = None


class TranslationsOutput(BaseModel):
    """List of translation audio tracks."""

    model_config = ConfigDict(extra="ignore")

    translations: list[str] = Field(default_factory=list)


class CalculateConferencesOutput(BaseModel):
    """Calculated participant and podium limits across conference modes."""

    model_config = ConfigDict(extra="ignore")

    symmetric: dict[str, Any] | None = None
    asymmetric: dict[str, Any] | None = None
    role_based: list[dict[str, Any]] | None = None
    smart_meeting: list[dict[str, Any]] | None = None


class AddressBookContactOutput(BaseModel):
    """Contact entry from user's address book."""

    model_config = ConfigDict(extra="ignore")

    user_id: str | None = Field(default=None, validation_alias="id", description="User ID in address book")
    display_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    status: int | None = None
    is_user: bool | None = None

    @computed_field
    @property
    def id(self) -> str | None:
        return self.user_id

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "user_id" in data and "id" not in data:
                data["id"] = data["user_id"]
        return data


class AddressBookOutput(BaseModel):
    """Address book search result."""

    model_config = ConfigDict(extra="ignore")

    contacts: list[AddressBookContactOutput] = Field(default_factory=list)
    next_page_id: int | None = None
