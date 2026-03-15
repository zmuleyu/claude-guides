"""Scan directories for secrets and prompt injection patterns."""

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from patterns import PATTERNS, PROMPT_INJECTION_PATTERNS

console = Console()

# Directories to always skip during scanning
SKIP_DIRS = {
    "node_modules",
    ".next",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".turbo",
    ".expo",
    ".cache",
    "coverage",
}

# Binary / non-text extensions to skip
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".pyc", ".pyo", ".class",
    ".db", ".sqlite", ".sqlite3",
    ".lock",
}

# Max file size to scan (1 MB)
MAX_FILE_SIZE = 1_048_576


def _severity_badge(severity: str) -> Text:
    """Return a Rich Text badge colored by severity."""
    color_map = {
        "critical": "bold white on red",
        "high": "bold white on dark_orange",
        "medium": "bold black on yellow",
        "low": "bold black on cyan",
    }
    style = color_map.get(severity, "")
    return Text(f" {severity.upper()} ", style=style)


def _should_skip_dir(dir_path: Path) -> bool:
    """Check if a directory should be skipped."""
    return dir_path.name in SKIP_DIRS


def _should_skip_file(file_path: Path) -> bool:
    """Check if a file should be skipped."""
    if file_path.suffix.lower() in SKIP_EXTENSIONS:
        return True
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return True
    except OSError:
        return True
    return False


def _check_env_in_gitignore(directory: Path) -> list[dict]:
    """Check if .env files exist and whether they are covered by .gitignore."""
    findings = []
    env_files = list(directory.rglob(".env")) + list(directory.rglob(".env.*"))

    if not env_files:
        return findings

    gitignore_path = directory / ".gitignore"
    gitignore_content = ""
    if gitignore_path.exists():
        try:
            gitignore_content = gitignore_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    for env_file in env_files:
        relative = env_file.relative_to(directory)
        # Simple check: see if .env or the relative path appears in .gitignore
        env_covered = False
        for line in gitignore_content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                if stripped in (".env", ".env.*", ".env*", "*.env"):
                    env_covered = True
                    break
                if str(relative) == stripped:
                    env_covered = True
                    break

        if not env_covered:
            findings.append({
                "file": str(env_file),
                "line": 0,
                "pattern": ".env not in .gitignore",
                "severity": "high",
                "snippet": f"{relative} exists but may not be covered by .gitignore",
            })

    return findings


def _check_no_proxy(directory: Path) -> list[dict]:
    """Check if NO_PROXY is configured in .env files."""
    findings = []
    env_files = list(directory.rglob(".env")) + list(directory.rglob(".env.*"))

    for env_file in env_files:
        try:
            content = env_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        has_proxy = False
        has_no_proxy = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("HTTP_PROXY") or stripped.startswith("HTTPS_PROXY"):
                has_proxy = True
            if stripped.startswith("NO_PROXY"):
                has_no_proxy = True

        if has_proxy and not has_no_proxy:
            findings.append({
                "file": str(env_file),
                "line": 0,
                "pattern": "NO_PROXY not configured",
                "severity": "medium",
                "snippet": "Proxy is configured but NO_PROXY is missing",
            })

    return findings


def _calculate_score(summary: dict[str, int]) -> str:
    """Calculate an A-F grade based on finding severity counts."""
    penalty = (
        summary.get("critical", 0) * 40
        + summary.get("high", 0) * 15
        + summary.get("medium", 0) * 5
        + summary.get("low", 0) * 1
    )
    if penalty == 0:
        return "A"
    elif penalty <= 10:
        return "B"
    elif penalty <= 30:
        return "C"
    elif penalty <= 60:
        return "D"
    else:
        return "F"


def scan_directory(path: str, output_json: bool = False) -> dict:
    """Scan a directory for secrets and prompt injection patterns.

    Args:
        path: Directory path to scan.
        output_json: If True, output results as JSON instead of Rich tables.

    Returns:
        Dictionary with findings, summary, and score.
    """
    directory = Path(path).resolve()

    if not directory.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {directory}")
        return {"findings": [], "summary": {}, "score": "A"}

    if not directory.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {directory}")
        return {"findings": [], "summary": {}, "score": "A"}

    findings: list[dict] = []
    files_scanned = 0
    all_patterns = [(name, pat, sev, "secret") for name, pat, sev in PATTERNS]
    all_patterns += [(name, pat, sev, "injection") for name, pat, sev in PROMPT_INJECTION_PATTERNS]

    if not output_json:
        console.print(f"\n[bold]Scanning:[/bold] {directory}\n")

    # Walk the directory tree
    try:
        for file_path in directory.rglob("*"):
            # Skip directories in the skip list
            skip = False
            for part in file_path.parts:
                if part in SKIP_DIRS:
                    skip = True
                    break
            if skip:
                continue

            if not file_path.is_file():
                continue

            if _should_skip_file(file_path):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue

            files_scanned += 1
            lines = content.splitlines()

            for line_num, line in enumerate(lines, start=1):
                for name, pattern, severity, category in all_patterns:
                    match = pattern.search(line)
                    if match:
                        # Truncate the snippet to avoid leaking full secrets
                        snippet = line.strip()
                        if len(snippet) > 120:
                            snippet = snippet[:117] + "..."

                        findings.append({
                            "file": str(file_path),
                            "line": line_num,
                            "pattern": name,
                            "severity": severity,
                            "category": category,
                            "snippet": snippet,
                        })
    except PermissionError:
        console.print(f"[yellow]Warning:[/yellow] Permission denied for some files in {directory}")

    # Additional checks
    findings.extend(_check_env_in_gitignore(directory))
    findings.extend(_check_no_proxy(directory))

    # Build summary
    summary: dict[str, int] = {}
    for finding in findings:
        sev = finding["severity"]
        summary[sev] = summary.get(sev, 0) + 1

    score = _calculate_score(summary)

    result = {
        "findings": findings,
        "summary": summary,
        "score": score,
        "files_scanned": files_scanned,
        "directory": str(directory),
    }

    if output_json:
        console.print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _render_results(result)

    return result


def _render_results(result: dict) -> None:
    """Render scan results as Rich tables."""
    findings = result["findings"]
    summary = result["summary"]
    score = result["score"]
    files_scanned = result["files_scanned"]

    # Score display
    score_colors = {
        "A": "bold green", "B": "bold cyan", "C": "bold yellow",
        "D": "bold dark_orange", "F": "bold red",
    }
    score_style = score_colors.get(score, "")
    console.print(f"  Files scanned: [bold]{files_scanned}[/bold]")
    console.print(f"  Security score: [{score_style}]{score}[/{score_style}]\n")

    if not findings:
        console.print("[green]No security issues found.[/green]\n")
        return

    # Findings table
    table = Table(title="Findings", show_lines=True)
    table.add_column("Severity", justify="center", width=10)
    table.add_column("Pattern", width=28)
    table.add_column("File", width=50)
    table.add_column("Line", justify="right", width=6)
    table.add_column("Snippet", width=60)

    # Sort by severity: critical > high > medium > low
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_findings = sorted(findings, key=lambda f: severity_order.get(f["severity"], 99))

    for finding in sorted_findings:
        badge = _severity_badge(finding["severity"])
        table.add_row(
            badge,
            finding["pattern"],
            finding["file"],
            str(finding["line"]),
            finding.get("snippet", ""),
        )

    console.print(table)

    # Summary table
    summary_table = Table(title="\nSummary")
    summary_table.add_column("Severity", justify="center")
    summary_table.add_column("Count", justify="right")

    for sev in ["critical", "high", "medium", "low"]:
        count = summary.get(sev, 0)
        if count > 0:
            badge = _severity_badge(sev)
            summary_table.add_row(badge, str(count))

    console.print(summary_table)
    console.print()
