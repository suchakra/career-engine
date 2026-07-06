"""JD metadata extraction utilities for CareerEngine (9G)."""

from __future__ import annotations

import json
from typing import Any


def extract_jd_metadata(jd_text: str, client: Any, model_id: str) -> tuple[str, str]:
    """Returns (title, company). Returns ("", "") on any failure."""
    system = (
        "Extract the job title and hiring company from the text. "
        'Return ONLY valid JSON: {"title": "...", "company": "..."}. '
        "Use empty string for unknown fields."
    )
    try:
        raw = client.generate(model_id, system, jd_text[:3000])
        data = json.loads(raw)
        return str(data.get("title", "")), str(data.get("company", ""))
    except Exception:
        return "", ""
