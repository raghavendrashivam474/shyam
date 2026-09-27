"""Shared fixtures for UI testing."""

from __future__ import annotations

import tkinter as tk
import pytest


@pytest.fixture(scope="session")
def session_tk():
    """Create a single shared hidden Tk root for the entire test session."""
    try:
        root = tk.Tk()
        root.withdraw()
        yield root
        try:
            root.destroy()
        except Exception:
            pass
    except tk.TclError:
        pytest.skip("Tkinter display not available in current test environment.")


@pytest.fixture
def tk_root(session_tk):
    """Provide a clean canvas by destroying all child widgets between tests."""
    for child in session_tk.winfo_children():
        child.destroy()
    yield session_tk