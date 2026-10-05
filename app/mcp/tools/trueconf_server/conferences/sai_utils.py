"""Helper to build the transcription (``sai``) block for create/update.

The TrueConf Server API exposes transcription settings as a single nested
``sai`` object (CreateSAI / PatchSAI). The tools expose them as separate
LLM-friendly parameters; this helper packs only the explicitly provided
values, so PATCH keeps its partial-update semantics (untouched fields are
simply not sent).
"""

from app._client_api._trueconf_server.models import ConferenceSAI


def build_sai(
    transcription_enabled: bool | None,
    transcription_language: str | None,
    transcription_auto_detect_language: bool | None,
) -> ConferenceSAI | None:
    """Build a ConferenceSAI from tool params, or None if nothing was given."""
    if transcription_enabled is None and transcription_language is None and transcription_auto_detect_language is None:
        return None
    return ConferenceSAI(
        recording_enabled=transcription_enabled,
        recognition_language=transcription_language,
        auto_recognition_enabled=transcription_auto_detect_language,
    )
