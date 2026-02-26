"""Data management layer - handles application state and persistence."""

from __future__ import annotations

import threading
from typing import Any, Callable

from ..storage import save_character


class DataManager:
    """
    Manages application state (data dict) and handles debounced saving to database.
    
    Centralizes the save/load logic that was previously scattered in app.py callbacks.
    """

    def __init__(self, initial_data: dict[str, Any] | None = None):
        """
        Initialize DataManager with optional initial data.
        
        Args:
            initial_data: Initial state dictionary. If None, creates empty state.
        """
        self.data = initial_data or {
            "inventario": [],
            "money": {"corone": 0, "scellini": 0, "rame": 0},
            "qualita": [],
            "imparato": [],
            "inventario_raw": "",
            "appunti": "",
            "xp_raw": "",
        }
        self.current_character_id: int | None = None
        self._save_timer: threading.Timer | None = None
        self._save_callback: Callable[[str], None] | None = None

    def set_character(self, character_id: int | None) -> None:
        """Set the active character ID for save operations."""
        self.current_character_id = character_id

    def set_save_callback(self, callback: Callable[[str], None]) -> None:
        """
        Set optional callback for save feedback (e.g., UI snackbar updates).
        
        Args:
            callback: Function that takes an error message string.
        """
        self._save_callback = callback

    def do_save(self) -> None:
        """Execute immediate save to database."""
        if self.current_character_id is None:
            return

        try:
            save_character(self.current_character_id, self.data)
        except Exception as ex:
            error_msg = f"[SAVE ERROR] Failed to save: {ex}"
            print(error_msg)
            if self._save_callback:
                self._save_callback(error_msg)

    def schedule_save(self) -> None:
        """
        Schedule a debounced save (0.5s delay).
        
        Multiple calls within 0.5s will be coalesced into a single save.
        Uses Timer for debouncing to prevent excessive database writes.
        """
        try:
            # Cancel existing timer if any
            if self._save_timer:
                try:
                    self._save_timer.cancel()
                except Exception:
                    pass

            # Create new timer
            self._save_timer = threading.Timer(0.5, self.do_save)
            self._save_timer.daemon = True
            self._save_timer.start()
        except Exception:
            # Fallback: immediate save on error
            self.do_save()

    def cancel_pending_save(self) -> None:
        """Cancel any pending scheduled save."""
        if self._save_timer:
            try:
                self._save_timer.cancel()
            except Exception:
                pass
            self._save_timer = None

    def flush_save(self) -> None:
        """
        Cancel any pending save and perform immediate save.
        
        Useful when closing app or switching characters to ensure data is saved.
        """
        self.cancel_pending_save()
        self.do_save()
