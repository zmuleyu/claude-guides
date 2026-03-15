"""Claude Guard — Security audit & backup tool for Claude Code users.

CLI entry point using Click.
"""

import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(version="1.0.0", prog_name="claude-guard")
def main():
    """Claude Guard — Security audit & backup tool for Claude Code users."""
    pass


@main.command()
@click.argument("path", default=".")
@click.option("--json", "output_json", is_flag=True, help="Output results as JSON")
def scan(path: str, output_json: bool):
    """Scan a directory for secrets and prompt injection patterns.

    PATH defaults to the current directory.
    """
    try:
        from scanner import scan_directory
        result = scan_directory(path, output_json=output_json)
        # Exit with non-zero code if critical findings exist
        if result.get("summary", {}).get("critical", 0) > 0:
            sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scan interrupted.[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"[red]Scan failed:[/red] {exc}")
        sys.exit(2)


@main.command()
@click.option("--emergency", is_flag=True, help="Skip confirmation, backup everything immediately")
def backup(emergency: bool):
    """Back up Claude Code assets (memory, settings, logs) to a compressed archive."""
    try:
        from backup import backup_assets
        result = backup_assets(emergency=emergency)
        if not result:
            sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Backup interrupted.[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"[red]Backup failed:[/red] {exc}")
        sys.exit(2)


@main.command()
def audit():
    """Run a health audit on the Claude Code environment."""
    try:
        from audit import audit_health
        result = audit_health()
        # Exit with non-zero code if grade is D or F
        if result.get("grade", "A") in ("D", "F"):
            sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Audit interrupted.[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"[red]Audit failed:[/red] {exc}")
        sys.exit(2)


if __name__ == "__main__":
    main()
