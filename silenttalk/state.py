from __future__ import annotations

from enum import StrEnum


class AppState(StrEnum):
    STARTING = "STARTING"
    READY = "READY"
    OWNER_NOT_IN_VOICE = "OWNER_NOT_IN_VOICE"
    VOICE_CONNECTED = "VOICE_CONNECTED"
    SYNTHESIZING = "SYNTHESIZING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    SHUTTING_DOWN = "SHUTTING_DOWN"
