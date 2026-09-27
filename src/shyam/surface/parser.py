"""Deterministic intent parser for the S17.6 first slice.

This is NOT an LLM, RAG, or agent system.
It is a thin keyword-matching adapter that maps natural-language
input to a UserIntent enum value.
"""

from __future__ import annotations

from shyam.surface.models import UserIntent


class IntentParser:
    """Parse human text into a UserIntent."""

    _CONTINUE_SIGNALS = ("continue", "resume", "move", "transfer", "pick up", "handoff")
    _OBJECT_SIGNALS = ("work", "task", "project", "this", "it", "laptop", "device", "computer", "machine", "phone", "tablet")

    def parse(self, text: str) -> UserIntent:
        """Return the best-matching UserIntent for the given text."""
        normalised = text.lower().strip()
        if not normalised:
            return UserIntent.UNKNOWN

        if self._matches_continue_work(normalised):
            return UserIntent.CONTINUE_WORK

        return UserIntent.UNKNOWN

    def _matches_continue_work(self, text: str) -> bool:
        has_action = any(sig in text for sig in self._CONTINUE_SIGNALS)
        has_object = any(sig in text for sig in self._OBJECT_SIGNALS)
        return has_action and has_object
