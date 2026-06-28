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
    "\n\n반드시 아래 JSON 스키마로만 답하라. 코드펜스나 설명 없이 JSON 객체 하나만 출력하라.\n"
    '{\n'
    '  "summary": "<한 줄 요약>",\n'
    '  "issues": [\n'
    '    {"severity": "high|medium|low", "region": "<위치>", "element": "<요소>",\n'
    '     "description": "<설명>", "css_hint": "<원인이 될 만한 CSS/스타일 힌트>"}\n'
    '  ]\n'
    '}'
)

CORRECTIVE_INSTRUCTION = (
    "직전 응답이 요구한 JSON 형식이 아니었다. 아래 내용을 지정한 JSON 스키마로만 다시 출력하라. "
    "설명/코드펜스 없이 JSON 객체 하나만:\n\n"
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
