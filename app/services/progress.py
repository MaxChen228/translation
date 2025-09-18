from __future__ import annotations

from typing import Optional


def update_after_correct(bank_item_id: Optional[str], device_id: Optional[str], score: Optional[int]) -> None:
    """No-op placeholder for progress update (kept for future).

    Historically this was a stub in main.py. Keeping a dedicated service so
    route handlers can call it without importing from main.
    """
    return None

