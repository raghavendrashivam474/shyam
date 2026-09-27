"""Input adapters for human-facing surface interactions.

Normalizes voice, text, or external inputs into standardized InteractionRequest models.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Protocol

from shyam.surface.models import InteractionRequest


class InputAdapter(Protocol):
    """Protocol defining human input ingestion."""

    async def get_request(self) -> InteractionRequest:
        """Retrieve the next normalized user interaction request."""
        ...


class TextInputAdapter:
    """Ingests direct text strings or prompts from a text interface."""

    def __init__(self, prompt_fn: Callable[[], str] | None = None) -> None:
        self._prompt_fn = prompt_fn

    def create_request(self, text: str) -> InteractionRequest:
        """Create a direct InteractionRequest from a text string."""
        return InteractionRequest(text=text, source="text")

    async def get_request(self) -> InteractionRequest:
        """Prompt for text input asynchronously."""
        if self._prompt_fn:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._prompt_fn)
            return self.create_request(text)
        raise NotImplementedError("No prompt function configured for TextInputAdapter.")


class VoiceInputAdapter:
    """Ingests transcribed voice strings or audio provider hooks."""

    def __init__(self, stt_transcriber: Callable[[bytes], str] | None = None) -> None:
        self._stt_transcriber = stt_transcriber

    def create_request_from_transcription(self, transcribed_text: str) -> InteractionRequest:
        """Wrap transcribed speech into a voice-tagged InteractionRequest."""
        return InteractionRequest(text=transcribed_text, source="voice")

    async def transcribe_and_create(self, audio_data: bytes) -> InteractionRequest:
        """Transcribe raw audio bytes using the configured speech-to-text hook."""
        if not self._stt_transcriber:
            raise RuntimeError("No STT transcriber configured in VoiceInputAdapter.")

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, self._stt_transcriber, audio_data)
        return self.create_request_from_transcription(text)
