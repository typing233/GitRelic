"""Command Line Interface for GitRelic

This module provides the main command-line interface for GitRelic,
allowing users to analyze Git repositories with a single command.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import click

from .git_data import GitDataExtractor
from .ownership import OwnershipAnalyzer
from .zombie import ZombieScanner
from .todo_tracker import TodoScanner
from .metrics import MetricsCalculator, HealthReport
from .renderer import (
    TerminalRenderer, 
    ANSI_BOLD, 
    ANSI_RESET, 
    ANSI_RED, 
    ANSI_GREEN, 
    ANSI_YELLOW, 
    ANSI_CYAN,
    ANSI_BRIGHT_BLACK,
)


def print_header(text: str) -> None:
    """Print a formatted header.

    Args:
        text: Header text.
    """
    click.echo(f"\n{ANSI_BOLD}{'=' * 80}{ANSI_RESET}")
    click.echo(f"{ANSI_BOLD}  {text}{ANSI_RESET}")
    click.echo(f"{ANSI_BOLD}{'=' * 80}{ANSI_RESET}\n")


def print_banner() -> None:
    """Print the GitRelic banner."""
    lines = [
        "",
        f"{ANSI_CYAN}   _______ _ _   _           _ _      {ANSI_RESET}",
        f"{ANSI_CYAN}  |   __ (_) | (_)         | (_)     {ANSI_RESET}",
        f"{ANSI_GREEN}  | |  \\/_| |_ _  ___ _ __| |_  ___ {ANSI_RESET}",
        f"{ANSI_GREEN}  | | __| | __| |/ _ \\ '__| | |/ __|{ANSI_RESET}",
        f"{ANSI_YELLOW}  | |_\\ \\ | |_| |  __/ |  | | | (__ {ANSI_RESET}",
        f"{ANSI_YELLOW}   \\____/_|\\__|_|\\___|_|  |_|_|\\___|{ANSI_RESET}",
        f"{ANSI_BRIGHT_BLACK}  Git Repository Analysis & Health Monitor{ANSI_RESET}",
        "",
    ]
    click.echo("\n".join(lines))


class Context:
    """Context object for passing state between commands."""

    def __init__(self):
        self.repo_path: Optional[Path] = None
        self.verbose: bool = False
        self.terminal_width: int = 80

    def echo(self, message: str, nl: bool = True) -> None:
        """Echo a message if verbose mode is enabled.

        Args:
            message: Message to echo.
            nl: Whether to add newline.
        """
        if self.verbose:
            click.echo(message, nl=nl)


pass_context = click.make_pass_decorator(Context, ensure=True)


@click.group(invoke_without_command=True)
@click.option(
    "-p", "--path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    help="Path to Git repository (default: current directory)"
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Enable verbose output"
)
@click.option(
    "-w", "--width",
    type=int,
    default=80,
    help="Terminal width for output (default: 80)"
)
@pass_context
def cli(ctx: Context, path: str, verbose: bool, width: int):
    """GitRelic - Git Repository Analysis Tool

    Analyze Git repositories for code ownership, zombie functions,
    TODO tracking, and generate technical debt reports.
    """
    ctx.repo_path = Path(path).resolve()
    ctx.verbose = verbose
    ctx.terminal_width = width

    if click.get_current_context().invoked_subcommand is None:
        ctx.echo(f"Analyzing repository: {ctx.repo_path}")
        run_full_analysis(ctx)


def run_full_analysis(ctx: Context) -> None:
    """Run the full analysis pipeline.

    Args:
        ctx: Command context.
    """
    print_banner()

    try:
        extractor = GitDataExtractor(str(ctx.repo_path))
    except ValueError as e:
        click.echo(f"{ANSI_RED}Error: {e}{ANSI_RESET}")
        click.echo(f"{ANSI_YELLOW}Please run this command from within a Git repository.{ANSI_RESET}")
        sys.exit(1)

    renderer = TerminalRenderer(width=ctx.terminal_width)
    metrics_calc = MetricsCalculator()

    click.echo(f"{ANSI_CYAN}📊 Collecting data from Git repository...{ANSI_RESET}")

    click.echo(f"{ANSI_CYAN}  → Analyzing code ownership...{ANSI_RESET}")
    ownership_analyzer = OwnershipAnalyzer(extractor)
    heatmap_data = ownership_analyzer.get_ownership_heatmap_data(max_depth=2)
    activity_data = ownership_analyzer.get_commit_activity_summary(months=12)

    click.echo(f"{ANSI_CYAN}  → Scanning for zombie functions...{ANSI_RESET}")
    zombie_scanner = ZombieScanner(str(ctx.repo_path), days_threshold=90)
    zombie_result = zombie_scanner.scan()
    zombie_summary = zombie_scanner.get_zombie_summary(zombie_result)

    click.echo(f"{ANSI_CYAN}  → Tracking TODO/FIXME comments...{ANSI_RESET}")
    todo_scanner = TodoScanner(str(ctx.repo_path))
    todo_result = todo_scanner.scan()
    todo_summary = todo_scanner.get_todo_summary(todo_result)
    high_priority_todos = todo_scanner.get_high_priority_todos(todo_result, limit=10)

    click.echo(f"{ANSI_CYAN}  → Calculating health metrics...{ANSI_RESET}\n")

    ownership_data = {"root": heatmap_data.get("root")}
    health_report = metrics_calc.generate_health_report(
        ownership_data=ownership_data,
        zombie_data=zombie_summary,
        todo_data=todo_summary,
        activity_data=activity_data,
    )

    click.clear()
    print_banner()

    print_header("CODE OWNERSHIP HEATMAP")
    click.echo(renderer.render_heatmap(heatmap_data, max_items=20))

    print_header("DEVELOPER ACTIVITY")
    click.echo(renderer.render_activity_barchart(activity_data, months_to_show=12))

    print_header("ZOMBIE FUNCTIONS REPORT")
    if zombie_summary["zombie_count"] > 0:
        click.echo(f"\n{ANSI_BOLD}Summary:{ANSI_RESET}")
        click.echo(f"  Total functions analyzed: {zombie_summary['total_functions']}")
        click.echo(f"  Zombie functions found: {ANSI_RED}{zombie_summary['zombie_count']}{ANSI_RESET}")
        click.echo(f"  Zombie rate: {ANSI_RED}{zombie_summary['zombie_rate']:.1f}%{ANSI_RESET}")

        if zombie_result.zombie_functions:
            click.echo(f"\n{ANSI_BOLD}Zombie Functions (Top 15):{ANSI_RESET}")
            for func in zombie_result.zombie_functions[:15]:
                visibility = "Public" if func.is_public else "Private"
                click.echo(
                    f"  {ANSI_RED}●{ANSI_RESET} {func.name} "
                    f"({ANSI_CYAN}{func.file_path}:{func.line_number}{ANSI_RESET}) "
                    f"[{visibility}, {func.language}]"
                )
    else:
        click.echo(f"\n{ANSI_GREEN}✅ No zombie functions detected!{ANSI_RESET}")
        click.echo(f"  Total functions analyzed: {zombie_summary['total_functions']}")

    print_header("TODO / COMMENT TAGS REPORT")
    click.echo(f"\n{ANSI_BOLD}Summary:{ANSI_RESET}")
    click.echo(f"  Total tags found: {todo_summary['total_tags']}")
    click.echo(f"  TODO density: {todo_summary['todo_density_per_kilo']:.2f} per 1000 lines")

    by_severity = todo_summary.get('by_severity', {})
    if by_severity:
        click.echo(f"\n{ANSI_BOLD}By Severity:{ANSI_RESET}")
        for severity, count in by_severity.items():
            color = ANSI_RED if severity == "high" else (ANSI_YELLOW if severity == "normal" else ANSI_GREEN)
            click.echo(f"  {severity.title()}: {color}{count}{ANSI_RESET}")

    if todo_summary['by_tag']:
        click.echo(f"\n{ANSI_BOLD}By Tag Type:{ANSI_RESET}")
        for tag, count in list(todo_summary['by_tag'].items())[:10]:
            click.echo(f"  {tag}: {count}")

    if high_priority_todos:
        click.echo(f"\n{ANSI_BOLD}High Priority Issues (Top 10):{ANSI_RESET}")
        for tag in high_priority_todos:
            content_preview = tag.content[:60] + "..." if len(tag.content) > 60 else tag.content
            click.echo(
                f"  {ANSI_RED}{tag.tag}{ANSI_RESET} "
                f"({ANSI_CYAN}{tag.file_path}:{tag.line_number}{ANSI_RESET}): "
                f"{content_preview}"
            )

    print_header("PROJECT HEALTH RADAR")
    radar_data = health_report.radar_data
    click.echo(renderer.render_radar_chart(
        metrics=radar_data.get("raw_values", {}),
        scores=radar_data.get("scores", {}),
        overall_score=health_report.overall_score,
    ))

    if health_report.recommendations:
        print_header("RECOMMENDATIONS")
        for i, rec in enumerate(health_report.recommendations, 1):
            click.echo(f"  {i}. {rec}")

    click.echo(f"\n{ANSI_BOLD}{'=' * 80}{ANSI_RESET}")
    click.echo(f"{ANSI_BOLD}  Analysis complete!{ANSI_RESET}")
    click.echo(f"{ANSI_BOLD}{'=' * 80}{ANSI_RESET}\n")


@cli.command("heatmap")
@pass_context
def heatmap_cmd(ctx: Context):
    """Generate code ownership heatmap only."""
    print_banner()

    try:
        extractor = GitDataExtractor(str(ctx.repo_path))
    except ValueError as e:
        click.echo(f"{ANSI_RED}Error: {e}{ANSI_RESET}")
        sys.exit(1)

    renderer = TerminalRenderer(width=ctx.terminal_width)
    ownership_analyzer = OwnershipAnalyzer(extractor)
    heatmap_data = ownership_analyzer.get_ownership_heatmap_data(max_depth=3)

    click.echo(renderer.render_heatmap(heatmap_data, max_items=30))


@cli.command("activity")
@click.option(
    "-m", "--months",
    type=int,
    default=12,
    help="Number of months to analyze (default: 12)"
)
@pass_context
def activity_cmd(ctx: Context, months: int):
    """Show developer commit activity only."""
    print_banner()

    try:
        extractor = GitDataExtractor(str(ctx.repo_path))
    except ValueError as e:
        click.echo(f"{ANSI_RED}Error: {e}{ANSI_RESET}")
        sys.exit(1)

    renderer = TerminalRenderer(width=ctx.terminal_width)
    ownership_analyzer = OwnershipAnalyzer(extractor)
    activity_data = ownership_analyzer.get_commit_activity_summary(months=months)

    click.echo(renderer.render_activity_barchart(activity_data, months_to_show=months))


@cli.command("zombie")
@click.option(
    "-d", "--days",
    type=int,
    default=90,
    help="Days threshold for zombie detection (default: 90)"
)
@click.option(
    "--show-all",
    is_flag=True,
    help="Show all zombie functions (not just top 15)"
)
@pass_context
def zombie_cmd(ctx: Context, days: int, show_all: bool):
    """Scan for zombie functions only."""
    print_banner()

    zombie_scanner = ZombieScanner(str(ctx.repo_path), days_threshold=days)
    zombie_result = zombie_scanner.scan()
    zombie_summary = zombie_scanner.get_zombie_summary(zombie_result)

    click.echo(f"\n{ANSI_BOLD}ZOMBIE FUNCTIONS ANALYSIS{ANSI_RESET}")
    click.echo("-" * ctx.terminal_width)

    click.echo(f"\nThreshold: Functions not modified in {days} days and not called anywhere")
    click.echo(f"Files analyzed: {zombie_summary['files_analyzed']}")
    click.echo(f"Total functions: {zombie_summary['total_functions']}")
    click.echo(f"Zombie functions: {ANSI_RED}{zombie_summary['zombie_count']}{ANSI_RESET}")
    click.echo(f"Zombie rate: {ANSI_RED}{zombie_summary['zombie_rate']:.1f}%{ANSI_RESET}")

    if zombie_summary['by_language']:
        click.echo(f"\n{ANSI_BOLD}By Language:{ANSI_RESET}")
        for lang, count in zombie_summary['by_language'].items():
            click.echo(f"  {lang}: {count}")

    if zombie_result.zombie_functions:
        limit = None if show_all else 30
        click.echo(f"\n{ANSI_BOLD}Zombie Functions{' (Top 30)' if not show_all else ''}:{ANSI_RESET}")
        for func in zombie_result.zombie_functions[:limit]:
            visibility = "Public" if func.is_public else "Private"
            date_str = func.last_modified.strftime("%Y-%m-%d") if func.last_modified else "Unknown"
            click.echo(
                f"  {ANSI_RED}●{ANSI_RESET} {func.name:30} "
                f"{ANSI_CYAN}{func.file_path}:{func.line_number:<5}{ANSI_RESET} "
                f"Last: {date_str:12} [{visibility}]"
            )


@cli.command("todo")
@click.option(
    "--show-all",
    is_flag=True,
    help="Show all TODOs (not just top ones)"
)
@pass_context
def todo_cmd(ctx: Context, show_all: bool):
    """Scan for TODO/FIXME/HACK comments only."""
    print_banner()

    todo_scanner = TodoScanner(str(ctx.repo_path))
    todo_result = todo_scanner.scan()
    todo_summary = todo_scanner.get_todo_summary(todo_result)
    high_priority = todo_scanner.get_high_priority_todos(todo_result, limit=50)

    click.echo(f"\n{ANSI_BOLD}TODO / COMMENT TAGS ANALYSIS{ANSI_RESET}")
    click.echo("-" * ctx.terminal_width)

    click.echo(f"\nFiles analyzed: {todo_summary['files_analyzed']}")
    click.echo(f"Total lines: {todo_summary['total_lines']:,}")
    click.echo(f"Total tags: {ANSI_YELLOW}{todo_summary['total_tags']}{ANSI_RESET}")
    click.echo(f"TODO density: {todo_summary['todo_density_per_kilo']:.2f} per 1000 lines")

    if todo_summary['by_severity']:
        click.echo(f"\n{ANSI_BOLD}By Severity:{ANSI_RESET}")
        for severity, count in todo_summary['by_severity'].items():
            color = ANSI_RED if severity == "high" else (ANSI_YELLOW if severity == "normal" else ANSI_GREEN)
            bar = "█" * min(int(count / max(todo_summary['by_severity'].values(), default=1) * 20), 20)
            click.echo(f"  {severity.title():8} {color}{count:5}{ANSI_RESET} {bar}")

    if todo_summary['by_tag']:
        click.echo(f"\n{ANSI_BOLD}By Tag Type:{ANSI_RESET}")
        max_count = max(todo_summary['by_tag'].values(), default=1)
        for tag, count in todo_summary['by_tag'].items():
            is_high = tag in ('FIXME', 'HACK', 'XXX', 'BUG', 'SECURITY', 'SAFETY')
            color = ANSI_RED if is_high else ANSI_YELLOW
            bar = "█" * min(int(count / max_count * 30), 30)
            click.echo(f"  {tag:12} {color}{count:5}{ANSI_RESET} {bar}")

    if todo_summary['by_file']:
        click.echo(f"\n{ANSI_BOLD}Files with Most Tags (Top 10):{ANSI_RESET}")
        for file_path, count in list(todo_summary['by_file'].items())[:10]:
            click.echo(f"  {count:4} tags in {ANSI_CYAN}{file_path}{ANSI_RESET}")

    if high_priority:
        click.echo(f"\n{ANSI_BOLD}High Priority Issues (FIXME, HACK, BUG, etc.):{ANSI_RESET}")
        limit = None if show_all else 20
        for tag in high_priority[:limit]:
            content_preview = tag.content[:50] + "..." if len(tag.content) > 50 else tag.content
            click.echo(
                f"  {ANSI_RED}{tag.tag:8}{ANSI_RESET} "
                f"{ANSI_CYAN}{tag.file_path}:{tag.line_number:<5}{ANSI_RESET} "
                f"{content_preview}"
            )


@cli.command("health")
@pass_context
def health_cmd(ctx: Context):
    """Show project health report and radar chart only."""
    print_banner()

    try:
        extractor = GitDataExtractor(str(ctx.repo_path))
    except ValueError as e:
        click.echo(f"{ANSI_RED}Error: {e}{ANSI_RESET}")
        sys.exit(1)

    renderer = TerminalRenderer(width=ctx.terminal_width)
    metrics_calc = MetricsCalculator()

    click.echo(f"{ANSI_CYAN}📊 Analyzing project health...{ANSI_RESET}\n")

    ownership_analyzer = OwnershipAnalyzer(extractor)
    heatmap_data = ownership_analyzer.get_ownership_heatmap_data(max_depth=1)
    activity_data = ownership_analyzer.get_commit_activity_summary(months=12)

    zombie_scanner = ZombieScanner(str(ctx.repo_path))
    zombie_result = zombie_scanner.scan()
    zombie_summary = zombie_scanner.get_zombie_summary(zombie_result)

    todo_scanner = TodoScanner(str(ctx.repo_path))
    todo_result = todo_scanner.scan()
    todo_summary = todo_scanner.get_todo_summary(todo_result)

    ownership_data = {"root": heatmap_data.get("root")}
    health_report = metrics_calc.generate_health_report(
        ownership_data=ownership_data,
        zombie_data=zombie_summary,
        todo_data=todo_summary,
        activity_data=activity_data,
    )

    radar_data = health_report.radar_data
    click.echo(renderer.render_radar_chart(
        metrics=radar_data.get("raw_values", {}),
        scores=radar_data.get("scores", {}),
        overall_score=health_report.overall_score,
    ))

    if health_report.recommendations:
        print_header("RECOMMENDATIONS")
        for i, rec in enumerate(health_report.recommendations, 1):
            click.echo(f"  {i}. {rec}")


def main():
    """Entry point for the command line interface."""
    cli()


if __name__ == "__main__":
    main()
