from __future__ import annotations

from playwright.sync_api import expect

expect.set_options(timeout=5_000)
