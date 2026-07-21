from __future__ import annotations

import random
import time
from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sleep_biomimetic(min_s: float = 0.4, max_s: float = 1.6) -> None:
    if max_s <= 0:
        return
    lo = max(0.0, min_s)
    hi = max(lo, max_s)
    time.sleep(random.uniform(lo, hi))


def pick_user_agent() -> str:
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]
    return random.choice(uas)

