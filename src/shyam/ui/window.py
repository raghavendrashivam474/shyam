"""Tkinter minimal visual user surface for Shyam."""

from __future__ import annotations

import asyncio
import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable

from shyam.surface.coordinator import SurfaceCoordinator
from shyam.surface.input import TextInputAdapter, VoiceInputAdapter
from shyam.surface.models import InteractionRequest, InteractionResponse, SurfaceState

logger = logging.getLogger("shyam.ui.window")

# State visual metadata
STATE_CONFIG = {
    SurfaceState.IDLE: {
        "symbol": "●",
        "symbol_color": "#4ade80",  # green
        "status": "Ready to help",
    },
    SurfaceState.LISTENING: {
        "symbol": "●",
        "symbol_color": "#60a5fa",  # blue
        "status": "Listening...",
    },
    SurfaceState.UNDERSTANDING: {
        "symbol": "◌",
        "symbol_color": "#a78bfa",  # purple
        "status": "Thinking...",
    },
    SurfaceState.EXECUTING: {
        "symbol": "◌",
        "symbol_color": "#facc15",  # yellow/amber
        "status": "Continuing your work...",
    },
    SurfaceState.COMPLETED: {
        "symbol": "✓",
        "symbol_color": "#4ade80",  # green
        "status": "Completed",
    },
    SurfaceState.FAILED: {
        "symbol": "✕",
        "symbol_color": "#f87171",  # red
        "status": "Unable to complete",
    },
    SurfaceState.DEGRADED: {
        "symbol": "△",
        "symbol_color": "#fb923c",  # orange
        "status": "Ecosystem degraded",
    },
}


class ShyamWindow:
    """Minimal visual window representing Shyam."""

    def __init__(
        self,
        root: tk.Tk | tk.Toplevel,
        coordinator: SurfaceCoordinator,
        loop: asyncio.AbstractEventLoop | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.coordinator = coordinator
        self.loop = loop
        self.on_close = on_close

        self.text_adapter = TextInputAdapter()
        self.voice_adapter = VoiceInputAdapter()
        self._is_busy = False

        self._configure_window()
        self._build_ui()
        self.update_state(self.coordinator.current_state, message=self.coordinator.get_status_message())

    def _configure_window(self) -> None:
        """Configure basic window parameters."""
        self.root.title("Shyam")
        self.root.geometry("420x360")
        self.root.minsize(380, 320)
        self.root.configure(bg="#18181b")  # zinc-900

        # Intercept window close
        self.root.protocol("WM_DELETE_WINDOW", self._handle_window_close)

    def _build_ui(self) -> None:
        """Build the minimal visual surface layout."""
        # Main container card
        self.card = tk.Frame(self.root, bg="#27272a", bd=1, relief="flat")  # zinc-800
        self.card.pack(fill="both", expand=True, padx=16, pady=16)

        # Header / Title
        self.title_label = tk.Label(
            self.card,
            text="Shyam",
            font=("Segoe UI", 16, "bold"),
            fg="#f4f4f5",
            bg="#27272a",
        )
        self.title_label.pack(pady=(16, 8))

        # Status Symbol (The indicator: ●, ◌, ✓, ✕)
        self.symbol_label = tk.Label(
            self.card,
            text="●",
            font=("Segoe UI", 28),
            fg="#4ade80",
            bg="#27272a",
        )
        self.symbol_label.pack(pady=(4, 2))

        # State Tag (e.g. Ready, Thinking, Executing)
        self.state_label = tk.Label(
            self.card,
            text="Ready to help",
            font=("Segoe UI", 11, "bold"),
            fg="#a1a1aa",
            bg="#27272a",
        )
        self.state_label.pack(pady=(0, 6))

        # Message Body (Human-friendly response or prompt)
        self.message_label = tk.Label(
            self.card,
            text="What would you like to do?",
            font=("Segoe UI", 10),
            fg="#e4e4e7",
            bg="#27272a",
            wraplength=340,
            justify="center",
        )
        self.message_label.pack(fill="x", padx=16, pady=(0, 16))

        # Input Area (Entry + Submit Button + Voice Seam)
        self.input_frame = tk.Frame(self.card, bg="#27272a")
        self.input_frame.pack(fill="x", padx=16, pady=(0, 16), side="bottom")

        self.input_entry = tk.Entry(
            self.input_frame,
            font=("Segoe UI", 10),
            bg="#3f3f46",
            fg="#f4f4f5",
            insertbackground="#f4f4f5",
            bd=0,
            relief="flat",
        )
        self.input_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.input_entry.bind("<Return>", lambda event: self.submit_input())

        self.submit_button = tk.Button(
            self.input_frame,
            text="Send",
            font=("Segoe UI", 9, "bold"),
            bg="#3b82f6",
            fg="#ffffff",
            activebackground="#2563eb",
            activeforeground="#ffffff",
            bd=0,
            padx=12,
            pady=4,
            relief="flat",
            cursor="hand2",
            command=self.submit_input,
        )
        self.submit_button.pack(side="right")

    def update_state(self, state: SurfaceState, message: str | None = None) -> None:
        """Update visual state and messages in a thread-safe manner."""
        cfg = STATE_CONFIG.get(state, STATE_CONFIG[SurfaceState.IDLE])

        self.symbol_label.configure(text=cfg["symbol"], fg=cfg["symbol_color"])
        self.state_label.configure(text=cfg["status"])

        if message:
            self.message_label.configure(text=message)

        if state in (SurfaceState.UNDERSTANDING, SurfaceState.EXECUTING):
            self._is_busy = True
            self.submit_button.configure(state="disabled", bg="#71717a")
            self.input_entry.configure(state="disabled")
        else:
            self._is_busy = False
            self.submit_button.configure(state="normal", bg="#3b82f6")
            self.input_entry.configure(state="normal")
            self.input_entry.focus_set()

    def submit_input(self) -> None:
        """Read input from the entry box and dispatch to SurfaceCoordinator."""
        if self._is_busy:
            return

        text = self.input_entry.get().strip()
        if not text:
            return

        # Clear input
        self.input_entry.delete(0, tk.END)

        # Immediate feedback to user
        self.update_state(SurfaceState.UNDERSTANDING, message=f'"{text}"')

        # Create standard InteractionRequest
        req = self.text_adapter.create_request(text)

        # Determine target event loop
        target_loop = self.loop
        if target_loop is None:
            try:
                target_loop = asyncio.get_running_loop()
            except RuntimeError:
                target_loop = None

        if target_loop and target_loop.is_running():
            try:
                current_running_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_running_loop = None

            if current_running_loop is target_loop:
                asyncio.create_task(self._process_request_async(req))
            else:
                asyncio.run_coroutine_threadsafe(self._process_request_async(req), target_loop)
        else:
            # Synchronous fallback when no loop is running
            try:
                loop = asyncio.new_event_loop()
                resp = loop.run_until_complete(self.coordinator.handle_request(req))
                loop.close()
                self._on_response(resp)
            except Exception as exc:
                self._on_error(exc)

    async def _process_request_async(self, req: InteractionRequest) -> None:
        """Asynchronously call the coordinator and marshal back to UI thread."""
        try:
            resp = await self.coordinator.handle_request(req)
            self.root.after(0, self._on_response, resp)
        except Exception as exc:
            logger.exception("Error handling interaction in visual UI: %s", exc)
            self.root.after(0, self._on_error, exc)

    def _on_response(self, resp: InteractionResponse) -> None:
        """Apply InteractionResponse on the Tkinter main thread."""
        self.update_state(resp.state, message=resp.message)

    def _on_error(self, exc: Exception) -> None:
        """Handle execution exception on UI thread."""
        self.update_state(SurfaceState.FAILED, message=f"Error: {exc}")

    def _handle_window_close(self) -> None:
        """Handle window close event gracefully."""
        if self.on_close:
            self.on_close()
        else:
            self.root.destroy()