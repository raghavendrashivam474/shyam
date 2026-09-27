"""Unit tests for Shyam surface models, parser, presenter, and input adapters."""

import pytest
from shyam.core.readiness import EcosystemReadiness
from shyam.surface.input import TextInputAdapter, VoiceInputAdapter
from shyam.surface.models import InteractionRequest, InteractionResponse, SurfaceState, UserIntent
from shyam.surface.parser import IntentParser
from shyam.surface.presenter import Presenter


def test_intent_parser_matching() -> None:
    parser = IntentParser()

    assert parser.parse("continue this work on my other laptop") == UserIntent.CONTINUE_WORK
    assert parser.parse("resume task on computer") == UserIntent.CONTINUE_WORK
    assert parser.parse("transfer project to machine") == UserIntent.CONTINUE_WORK
    assert parser.parse("move this to my other laptop") == UserIntent.CONTINUE_WORK
    assert parser.parse("pick up work on tablet") == UserIntent.CONTINUE_WORK

    # Unmatched / garbage queries
    assert parser.parse("what is the weather today?") == UserIntent.UNKNOWN
    assert parser.parse("") == UserIntent.UNKNOWN
    assert parser.parse("   ") == UserIntent.UNKNOWN


def test_presenter_messages() -> None:
    presenter = Presenter()

    assert "ready" in presenter.readiness_message(EcosystemReadiness.READY).lower()
    assert "getting things ready" in presenter.readiness_message(EcosystemReadiness.STARTING).lower()
    assert "unavailable" in presenter.readiness_message(EcosystemReadiness.DEGRADED).lower()

    success = presenter.success_response()
    assert success.state == SurfaceState.COMPLETED
    assert "done" in success.message.lower()

    executing = presenter.executing_response()
    assert executing.state == SurfaceState.EXECUTING

    failure = presenter.failure_response("details")
    assert failure.state == SurfaceState.FAILED
    assert failure.detail == "details"


def test_input_adapters() -> None:
    text_adapter = TextInputAdapter()
    req = text_adapter.create_request("hello test")
    assert req.text == "hello test"
    assert req.source == "text"

    voice_adapter = VoiceInputAdapter()
    v_req = voice_adapter.create_request_from_transcription("voice test")
    assert v_req.text == "voice test"
    assert v_req.source == "voice"


@pytest.mark.asyncio
async def test_voice_adapter_stt_transcription() -> None:
    def fake_stt(data: bytes) -> str:
        return f"transcribed {len(data)} bytes"

    voice_adapter = VoiceInputAdapter(stt_transcriber=fake_stt)
    req = await voice_adapter.transcribe_and_create(b"12345")
    assert req.text == "transcribed 5 bytes"
    assert req.source == "voice"
