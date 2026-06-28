"""Vision report parsing with staged fallback (plan §7.7).

Order: direct JSON -> extract JSON block -> (caller does one corrective retry)
-> lossless fallback (raw_text preserved, parse_degraded=True).
"""

from __future__ import annotations

import json
import re

from ..core.models import VisionIssue, VisionReportBody

# Schema instruction appended to every prompt for backends without native
# structured output (plan §7.7).
SCHEMA_INSTRUCTION = (
    "\n\nRespond with ONLY the following JSON schema. Output a single JSON object "
    "with no code fences and no extra prose.\n"
    '{\n'
    '  "summary": "<one-line summary>",\n'
    '  "issues": [\n'
    '    {"severity": "high|medium|low", "region": "<where>", "element": "<element>",\n'
    '     "description": "<description>", "css_hint": "<likely CSS/style cause>"}\n'
    '  ]\n'
    '}'
)

CORRECTIVE_INSTRUCTION = (
    "Your previous reply was not in the required JSON format. Re-output the content "
    "below as a single JSON object matching the schema, with no prose or code fences:\n\n"
)

_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _coerce_report(data: dict, raw_text: str) -> VisionReportBody:
    issues_raw = data.get("issues") or []
    issues: list[VisionIssue] = []
    for it in issues_raw:
        if isinstance(it, dict):
            sev = str(it.get("severity", "medium")).lower()
            if sev not in ("high", "medium", "low"):
                sev = "medium"
            issues.append(
                VisionIssue(
                    severity=sev,
                    region=str(it.get("region", "")),
                    element=str(it.get("element", "")),
                    description=str(it.get("description", "")),
                    css_hint=str(it.get("css_hint", "")),
                )
            )
    return VisionReportBody(
        summary=str(data.get("summary", "")),
        issues=issues,
        raw_text=raw_text,
        parse_degraded=False,
    )


def try_parse(raw_text: str) -> VisionReportBody | None:
    """Attempt to parse a structured report; None if not parseable."""
    text = raw_text.strip()
    # 1) direct
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return _coerce_report(data, raw_text)
    except json.JSONDecodeError:
        pass
    # 2) fenced block, then any brace block
    for pattern in (_FENCE_RE, _BLOCK_RE):
        m = pattern.search(text)
        if m:
            candidate = m.group(1) if pattern is _FENCE_RE else m.group(0)
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return _coerce_report(data, raw_text)
            except json.JSONDecodeError:
                continue
    return None


def degraded(raw_text: str) -> VisionReportBody:
    """Lossless fallback when parsing fails (plan §7.7 step 4)."""
    summary = raw_text.strip().splitlines()[0][:300] if raw_text.strip() else ""
    return VisionReportBody(
        summary=summary,
        issues=[],
        raw_text=raw_text,
        parse_degraded=True,
    )
