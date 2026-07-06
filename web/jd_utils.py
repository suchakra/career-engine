"""JD metadata extraction utilities for CareerEngine (9G)."""

from __future__ import annotations

import json
from typing import Any


def _safe_str(value: Any) -> str:
    """Return value as a stripped string, or '' for non-string/null values."""
    return value.strip() if isinstance(value, str) else ""


def extract_jd_metadata(jd_text: str, client: Any, model_id: str) -> tuple[str, str]:
    """Returns (title, company).  Raises ModelAPIError on transport/API failures.
    Returns ("", "") when the model response cannot be parsed as JSON.
    """
    from integration.model_client import ModelAPIError

    system = (
        "Extract the job title and hiring company from the text. "
        'Return ONLY valid JSON: {"title": "...", "company": "..."}. '
        "Use empty string for unknown fields."
    )
    try:
        raw = client.generate(model_id, system, jd_text[:3000])
        # Strip markdown fences if present and extract the first JSON object.
        text = raw.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return "", ""
        data = json.loads(text[start : end + 1])
        return _safe_str(data.get("title")), _safe_str(data.get("company"))
    except ModelAPIError:
        raise  # propagate API/transport failures so the UI can surface them
    except Exception:
        return "", ""
