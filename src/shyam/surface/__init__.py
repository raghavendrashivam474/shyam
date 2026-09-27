"""S17.6 — Minimal human-facing Shyam surface layer."""

from shyam.surface.coordinator import SurfaceCoordinator
from shyam.surface.input import InputAdapter, TextInputAdapter, VoiceInputAdapter
from shyam.surface.models import (
    InteractionRequest,
    InteractionResponse,
    SurfaceState,
    UserIntent,
)
from shyam.surface.parser import IntentParser
from shyam.surface.presenter import Presenter

__all__ = [
    "InputAdapter",
    "InteractionRequest",
    "InteractionResponse",
    "IntentParser",
    "Presenter",
    "SurfaceCoordinator",
    "SurfaceState",
    "TextInputAdapter",
    "UserIntent",
    "VoiceInputAdapter",
]
