"""Health audit for Claude Code environment."""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

# Known project directories to check
PROJECT_ROOTS = [
    Path("D:/projects"),
    Path("C:/tools"),
]

BACKUP_DIR = Path("C:/Users/Admin/claude-backups")
CLAUDE_DIR = Path("C:/Users/Admin/.claude")
CRON_LOG = CLAUDE_DIR / "data" / "cron-log.jsonl"
MEMORY_ROOT = CLAUDE_DIR / "projects"


def _status_badge(status: str) -> Text:
    """Return a Rich Text badge for pass/warn/fail."""
    styles = {
        "pass": "bold white on green",
        "warn": "bold black on yellow",
        "fail": "bold white on red",
    }
    style = styles.get(status, "")
    label = status.upper()
    return Text(f" {label} ", style=style)


def _check_git_email_consistency() -> dict:
    """Check that git user.email is consistent across known project dirs.

    Returns:
        Dict with status, details, and recommendation.
    """
    emails: dict[str, list[str]] = {}

    for root in PROJECT_ROOTS:
        if not root.exists():
            continue
        # Find directories that contain a .git folder
        try:
            for git_dir in root.rglob(".git"):
                if not git_dir.is_dir():
                    continue
                project_dir = git_dir.parent
                try:
                    result = subprocess.run(
                        ["git", "config", "user.email"],
                        cwd=str(project_dir),
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    email = result.stdout.strip()
                    if email:
                        emails.setdefault(email, []).append(str(project_dir))
                except (subprocess.TimeoutExpired, OSError):
                    continue
        except (PermissionError, OSError):
            continue

    if not emails:
        return {
            "status": "warn",
            "details": "No git repos found to check",
            "recommendation": "Ensure git is configured in your projects",
        }

    if len(emails) == 1:
        email = next(iter(emails))
        count = sum(len(v) for v in emails.values())
        return {
            "status": "pass",
            "details": f"Consistent email ({email}) across {count} repo(s)",
            "recommendation": "",
        }

    detail_lines = []
    for email, dirs in emails.items():
        detail_lines.append(f"{email}: {len(dirs)} repo(s)")
    return {
        "status": "warn",
        "details": f"Multiple emails found: {'; '.join(detail_lines)}",
        "recommendation": "Standardize git user.email across all repos",
    }


def _check_api_key_format() -> dict:
    """Check .env files for valid API key formats (not placeholder/empty).

    Returns:
        Dict with status, details, and recommendation.
    """
    issues: list[str] = []
    env_count = 0

    placeholder_values = {
        "your-api-key-here", "xxx", "placeholder", "changeme",
        "TODO", "FIXME", "your_key_here", "sk-xxx", "",
    }

    for root in PROJECT_ROOTS:
        if not root.exists():
            continue
        try:
            for env_file in root.rglob(".env"):
                if not env_file.is_file():
                    continue
                # Skip files in skip directories
                skip = False
                for part in env_file.parts:
                    if part in {"node_modules", ".venv", "venv", ".git"}:
                        skip = True
                        break
                if skip:
                    continue

                env_count += 1
                try:
                    content = env_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                for line_num, line in enumerate(content.splitlines(), start=1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    if "=" not in stripped:
                        continue

                    key, _, value = stripped.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")

                    # Check if this looks like an API key variable
                    key_lower = key.lower()
                    is_key_var = any(
                        kw in key_lower
                        for kw in ["api_key", "secret", "token", "password", "apikey"]
                    )
                    if is_key_var and value.lower() in placeholder_values:
                        issues.append(f"{env_file.name}:{line_num} - {key} is placeholder")
        except (PermissionError, OSError):
            continue

    if env_count == 0:
        return {
            "status": "pass",
            "details": "No .env files found",
            "recommendation": "",
        }

    if not issues:
        return {
            "status": "pass",
            "details": f"Checked {env_count} .env file(s), no placeholder keys found",
            "recommendation": "",
        }

    return {
        "status": "warn",
        "details": f"{len(issues)} placeholder key(s) found in {env_count} .env file(s)",
        "recommendation": "Replace placeholder values with actual keys or remove unused entries",
    }


def _check_backup_freshness() -> dict:
    """Check if the latest backup is within 7 days.

    Returns:
        Dict with status, details, and recommendation.
    """
    if not BACKUP_DIR.exists():
        return {
            "status": "fail",
            "details": "Backup directory does not exist",
            "recommendation": "Run 'claude-guard backup' to create your first backup",
        }

    backups = sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not backups:
        return {
            "status": "fail",
            "details": "No backup archives found",
            "recommendation": "Run 'claude-guard backup' to create a backup",
        }

    latest = backups[0]
    try:
        mtime = datetime.fromtimestamp(latest.stat().st_mtime)
    except OSError:
        return {
            "status": "warn",
            "details": "Could not read latest backup timestamp",
            "recommendation": "Check backup directory permissions",
        }

    age = datetime.now() - mtime
    age_str = f"{age.days}d {age.seconds // 3600}h ago"

    if age <= timedelta(days=7):
        return {
            "status": "pass",
            "details": f"Latest backup: {latest.name} ({age_str})",
            "recommendation": "",
        }
    elif age <= timedelta(days=14):
        return {
            "status": "warn",
            "details": f"Latest backup is {age_str}: {latest.name}",
            "recommendation": "Consider running a fresh backup soon",
        }
    else:
        return {
            "status": "fail",
            "details": f"Latest backup is {age_str}: {latest.name}",
            "recommendation": "Backup is stale, run 'claude-guard backup' immediately",
        }


def _check_memory_freshness() -> dict:
    """Check if memory files have been updated within 30 days.

    Returns:
        Dict with status, details, and recommendation.
    """
    if not MEMORY_ROOT.exists():
        return {
            "status": "warn",
            "details": "Memory directory does not exist",
            "recommendation": "Memory files will be created as you use Claude Code",
        }

    memory_files = list(MEMORY_ROOT.rglob("memory/*.md"))

    if not memory_files:
        return {
            "status": "warn",
            "details": "No memory files found",
            "recommendation": "Memory files will be auto-generated during sessions",
        }

    cutoff = datetime.now() - timedelta(days=30)
    stale_files: list[str] = []
    total = len(memory_files)

    for mf in memory_files:
        try:
            mtime = datetime.fromtimestamp(mf.stat().st_mtime)
            if mtime < cutoff:
                age_days = (datetime.now() - mtime).days
                stale_files.append(f"{mf.name} ({age_days}d old)")
        except OSError:
            continue

    if not stale_files:
        return {
            "status": "pass",
            "details": f"All {total} memory file(s) updated within 30 days",
            "recommendation": "",
        }

    if len(stale_files) <= 3:
        return {
            "status": "warn",
            "details": f"{len(stale_files)}/{total} stale: {', '.join(stale_files)}",
            "recommendation": "Review stale memory files and update or remove them",
        }

    return {
        "status": "warn",
        "details": f"{len(stale_files)}/{total} memory files are older than 30 days",
        "recommendation": "Review and refresh stale memory files",
    }


def _check_cron_health() -> dict:
    """Parse cron-log.jsonl for the last 7 days and calculate pass/fail/warn ratio.

    Returns:
        Dict with status, details, and recommendation.
    """
    if not CRON_LOG.is_file():
        return {
            "status": "warn",
            "details": "cron-log.jsonl not found",
            "recommendation": "Cron log will be populated when scheduled tasks run",
        }

    cutoff = datetime.now() - timedelta(days=7)
    counts = {"pass": 0, "fail": 0, "warn": 0, "info": 0}
    total = 0
    parse_errors = 0

    try:
        content = CRON_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "status": "warn",
            "details": f"Could not read cron log: {exc}",
            "recommendation": "Check file permissions for cron-log.jsonl",
        }

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            parse_errors += 1
            continue

        # Try to parse timestamp
        ts_str = entry.get("timestamp") or entry.get("ts") or entry.get("time")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00").replace("+00:00", ""))
            except (ValueError, AttributeError):
                ts = None
        else:
            ts = None

        # If no parseable timestamp, skip the cutoff check
        if ts is not None and ts < cutoff:
            continue

        total += 1
        result = str(entry.get("result", entry.get("status", "info"))).lower()
        if result in counts:
            counts[result] += 1
        else:
            counts["info"] += 1

    if total == 0:
        return {
            "status": "warn",
            "details": "No cron entries in the last 7 days",
            "recommendation": "Check if scheduled tasks are running",
        }

    fail_rate = counts["fail"] / total if total > 0 else 0
    detail = f"Last 7d: {counts['pass']} pass, {counts['fail']} fail, {counts['warn']} warn, {counts['info']} info (total {total})"

    if fail_rate == 0:
        status = "pass"
        rec = ""
    elif fail_rate < 0.2:
        status = "warn"
        rec = f"Failure rate {fail_rate:.0%} — review failing tasks"
    else:
        status = "fail"
        rec = f"High failure rate {fail_rate:.0%} — investigate cron task errors"

    return {"status": status, "details": detail, "recommendation": rec}


def _calculate_overall_grade(checks: dict[str, dict]) -> str:
    """Calculate an overall A-F grade from individual check results."""
    penalty = 0
    for check in checks.values():
        status = check["status"]
        if status == "fail":
            penalty += 20
        elif status == "warn":
            penalty += 5

    if penalty == 0:
        return "A"
    elif penalty <= 10:
        return "B"
    elif penalty <= 25:
        return "C"
    elif penalty <= 45:
        return "D"
    else:
        return "F"


def audit_health() -> dict:
    """Run all health checks and display results.

    Returns:
        Dictionary with overall grade, checks, and recommendations.
    """
    console.print("\n[bold]Claude Guard Health Audit[/bold]\n")

    checks = {
        "Git Email Consistency": _check_git_email_consistency(),
        "API Key Format": _check_api_key_format(),
        "Backup Freshness": _check_backup_freshness(),
        "Memory Freshness": _check_memory_freshness(),
        "Cron Health": _check_cron_health(),
    }

    overall_grade = _calculate_overall_grade(checks)

    # Results table
    table = Table(title="Health Checks", show_lines=True)
    table.add_column("Check", width=25, style="bold")
    table.add_column("Status", justify="center", width=8)
    table.add_column("Details", width=60)

    for name, result in checks.items():
        badge = _status_badge(result["status"])
        table.add_row(name, badge, result["details"])

    console.print(table)

    # Overall grade
    grade_colors = {
        "A": "bold green", "B": "bold cyan", "C": "bold yellow",
        "D": "bold dark_orange", "F": "bold red",
    }
    grade_style = grade_colors.get(overall_grade, "")
    console.print(f"\n  Overall health grade: [{grade_style}]{overall_grade}[/{grade_style}]\n")

    # Recommendations
    recommendations = [
        (name, result["recommendation"])
        for name, result in checks.items()
        if result["recommendation"]
    ]

    if recommendations:
        rec_table = Table(title="Recommendations")
        rec_table.add_column("Check", width=25, style="bold")
        rec_table.add_column("Action", width=65)

        for name, rec in recommendations:
            rec_table.add_row(name, rec)

        console.print(rec_table)
        console.print()
    else:
        console.print("[green]No recommendations — everything looks good.[/green]\n")

    return {
        "grade": overall_grade,
        "checks": checks,
        "recommendations": recommendations,
    }
