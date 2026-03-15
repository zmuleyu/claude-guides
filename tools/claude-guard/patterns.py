"""Secret detection and prompt injection patterns for Claude Guard."""

import re

# Each tuple: (name, regex_pattern, severity)
# Severity levels: critical, high, medium, low

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "Anthropic API Key",
        re.compile(r"sk-ant-api03-[A-Za-z0-9_-]{20,}"),
        "critical",
    ),
    (
        "OpenAI Key",
        re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),
        "critical",
    ),
    (
        "OpenAI Legacy Key",
        re.compile(r"sk-[A-Za-z0-9]{48,}"),
        "critical",
    ),
    (
        "GitHub PAT (classic)",
        re.compile(r"ghp_[A-Za-z0-9]{36}"),
        "high",
    ),
    (
        "GitHub OAuth Token",
        re.compile(r"gho_[A-Za-z0-9]{36}"),
        "high",
    ),
    (
        "GitHub Fine-Grained PAT",
        re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
        "high",
    ),
    (
        "Supabase Key",
        re.compile(r"sbp_[A-Za-z0-9]{40,}"),
        "high",
    ),
    (
        "Private Key Block",
        re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        "critical",
    ),
    (
        "AWS Access Key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "critical",
    ),
]

PROMPT_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "Ignore Previous Instructions",
        re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
        "medium",
    ),
    (
        "Ignore All Instructions",
        re.compile(r"ignore\s+all\s+instructions", re.IGNORECASE),
        "medium",
    ),
    (
        "DAN Mode / Jailbreak",
        re.compile(r"(DAN\s+mode|jailbreak)", re.IGNORECASE),
        "high",
    ),
    (
        "Pretend No Restrictions",
        re.compile(r"pretend\s+you\s+have\s+no\s+restrictions", re.IGNORECASE),
        "medium",
    ),
    (
        "Act As No Limits",
        re.compile(r"act\s+as\s+if\s+you\s+have\s+no\s+limits", re.IGNORECASE),
        "medium",
    ),
]
