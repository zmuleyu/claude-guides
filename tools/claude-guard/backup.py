"""Backup Claude Code assets to a compressed archive."""

import tarfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

console = Console()

# Base paths
CLAUDE_DIR = Path("C:/Users/Admin/.claude")
PROJECTS_DIR = Path("D:/projects")
TOOLS_DIR = Path("C:/tools")
BACKUP_DIR = Path("C:/Users/Admin/claude-backups")


def _collect_files() -> list[Path]:
    """Collect all files that should be backed up.

    Returns:
        List of absolute Path objects to back up.
    """
    files: list[Path] = []

    # 1. Memory files: C:/Users/Admin/.claude/projects/*/memory/*.md
    memory_root = CLAUDE_DIR / "projects"
    if memory_root.exists():
        for md_file in memory_root.rglob("memory/*.md"):
            if md_file.is_file():
                files.append(md_file)

    # 2. Global settings
    settings = CLAUDE_DIR / "settings.json"
    if settings.is_file():
        files.append(settings)

    # 3. CLAUDE.md files in D:/projects/ and C:/tools/
    for base_dir in [PROJECTS_DIR, TOOLS_DIR]:
        if base_dir.exists():
            for claude_md in base_dir.rglob("CLAUDE.md"):
                if claude_md.is_file():
                    files.append(claude_md)

    # 4. Agent logs from the last 30 days
    agent_logs_dir = CLAUDE_DIR / "agent-logs"
    if agent_logs_dir.exists():
        cutoff = datetime.now() - timedelta(days=30)
        for log_file in agent_logs_dir.iterdir():
            if log_file.is_file():
                try:
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime >= cutoff:
                        files.append(log_file)
                except OSError:
                    continue

    # 5. Cron log
    cron_log = CLAUDE_DIR / "data" / "cron-log.jsonl"
    if cron_log.is_file():
        files.append(cron_log)

    # 6. Lessons file
    lessons = CLAUDE_DIR / "lessons.md"
    if lessons.is_file():
        files.append(lessons)

    return files


def _human_size(size_bytes: int) -> str:
    """Convert byte count to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def backup_assets(emergency: bool = False) -> str:
    """Create a backup archive of Claude Code assets.

    Args:
        emergency: If True, skip the confirmation prompt.

    Returns:
        Path to the created backup archive.
    """
    files = _collect_files()

    if not files:
        console.print("[yellow]No files found to back up.[/yellow]")
        return ""

    # Calculate total size
    total_size = 0
    for f in files:
        try:
            total_size += f.stat().st_size
        except OSError:
            pass

    # Show what will be backed up
    console.print(f"\n[bold]Claude Guard Backup[/bold]\n")
    console.print(f"  Files to archive: [bold]{len(files)}[/bold]")
    console.print(f"  Total size (uncompressed): [bold]{_human_size(total_size)}[/bold]\n")

    # Confirmation unless emergency mode
    if not emergency:
        try:
            confirm = console.input("[bold]Proceed with backup? [Y/n]:[/bold] ")
            if confirm.strip().lower() in ("n", "no"):
                console.print("[yellow]Backup cancelled.[/yellow]")
                return ""
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Backup cancelled.[/yellow]")
            return ""

    # Ensure backup directory exists
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Create archive
    date_str = datetime.now().strftime("%Y-%m-%d")
    archive_name = f"{date_str}.tar.gz"
    archive_path = BACKUP_DIR / archive_name

    # If a backup already exists for today, add a suffix
    counter = 1
    while archive_path.exists():
        archive_name = f"{date_str}_{counter}.tar.gz"
        archive_path = BACKUP_DIR / archive_name
        counter += 1

    archived_count = 0
    archived_size = 0
    skipped: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Archiving files...", total=len(files))

        try:
            with tarfile.open(str(archive_path), "w:gz") as tar:
                for file_path in files:
                    try:
                        # Use a relative archive name based on drive letter
                        # e.g., C:/Users/Admin/.claude/... -> C/Users/Admin/.claude/...
                        drive = file_path.drive.replace(":", "")
                        relative = Path(drive) / file_path.relative_to(file_path.anchor)
                        tar.add(str(file_path), arcname=str(relative))
                        archived_count += 1
                        try:
                            archived_size += file_path.stat().st_size
                        except OSError:
                            pass
                    except (OSError, PermissionError, tarfile.TarError) as exc:
                        skipped.append(f"{file_path}: {exc}")

                    progress.update(task, advance=1)
        except (OSError, tarfile.TarError) as exc:
            console.print(f"[red]Error creating archive:[/red] {exc}")
            return ""

    # Final summary
    try:
        compressed_size = archive_path.stat().st_size
    except OSError:
        compressed_size = 0

    summary_table = Table(title="Backup Summary")
    summary_table.add_column("Property", style="bold")
    summary_table.add_column("Value")

    summary_table.add_row("Archive", str(archive_path))
    summary_table.add_row("Files archived", str(archived_count))
    summary_table.add_row("Uncompressed size", _human_size(archived_size))
    summary_table.add_row("Compressed size", _human_size(compressed_size))
    summary_table.add_row("Compression ratio",
                          f"{(1 - compressed_size / archived_size) * 100:.1f}%"
                          if archived_size > 0 else "N/A")

    console.print()
    console.print(summary_table)

    if skipped:
        console.print(f"\n[yellow]Skipped {len(skipped)} file(s):[/yellow]")
        for msg in skipped[:10]:
            console.print(f"  [dim]{msg}[/dim]")
        if len(skipped) > 10:
            console.print(f"  [dim]... and {len(skipped) - 10} more[/dim]")

    console.print(f"\n[green]Backup complete:[/green] {archive_path}\n")
    return str(archive_path)
