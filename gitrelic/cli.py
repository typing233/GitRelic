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
    ANSI_MAGENTA,
    ANSI_BRIGHT_BLACK,
)
from .replay import ReplayAnalyzer, ReplayController, ReplaySnapshot
from .collaboration import CollaborationAnalyzer, ASCIINetworkRenderer


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


@cli.command("replay")
@click.option(
    "-l", "--limit",
    type=int,
    default=100,
    help="Maximum number of commits to analyze (default: 100)"
)
@click.option(
    "-d", "--days",
    type=int,
    default=90,
    help="Days threshold for zombie detection (default: 90)"
)
@click.option(
    "-s", "--speed",
    type=float,
    default=1.0,
    help="Animation speed multiplier (default: 1.0)"
)
@click.option(
    "--no-auto-play",
    is_flag=True,
    help="Start in paused mode"
)
@pass_context
def replay_cmd(
    ctx: Context, 
    limit: int, 
    days: int, 
    speed: float, 
    no_auto_play: bool
):
    """Replay analysis results commit-by-commit with animation.
    
    Controls:
      SPACE    - Pause/Play
      →        - Step forward one commit
      ←        - Step backward one commit
      ↑        - Fast forward 10 commits
      ↓        - Rewind 10 commits
      Home     - Go to first commit
      End      - Go to last commit
      Q        - Quit
    """
    print_banner()
    
    try:
        click.echo(f"{ANSI_CYAN}📊 Loading commit history...{ANSI_RESET}")
        
        analyzer = ReplayAnalyzer(
            str(ctx.repo_path),
            days_threshold=days,
            commit_limit=limit,
        )
        
        commit_count = analyzer.load_commits()
        
        if commit_count == 0:
            click.echo(f"{ANSI_RED}Error: No commits found in repository.{ANSI_RESET}")
            sys.exit(1)
        
        click.echo(f"{ANSI_CYAN}  Found {commit_count} commits{ANSI_RESET}")
        click.echo(f"{ANSI_CYAN}📈 Generating analysis snapshots...{ANSI_RESET}")
        
        with click.progressbar(length=commit_count, label="Processing") as bar:
            def progress_callback(current, total):
                bar.update(current - bar.pos)
            
            snapshot_count = analyzer.generate_snapshots(progress_callback=progress_callback)
        
        if snapshot_count == 0:
            click.echo(f"{ANSI_RED}Error: Failed to generate snapshots.{ANSI_RESET}")
            sys.exit(1)
        
        click.clear()
        
        def render_snapshot(snapshot: ReplaySnapshot, current: int, total: int):
            click.clear()
            
            state = snapshot.state
            
            lines = []
            lines.append(f"\n{ANSI_BOLD}┌{'─' * (ctx.terminal_width - 2)}┐{ANSI_RESET}")
            lines.append(
                f"{ANSI_BOLD}│{ANSI_RESET}  "
                f"{ANSI_CYAN}{ANSI_BOLD}COMMIT REPLAY{ANSI_RESET} "
                f"{ANSI_BRIGHT_BLACK}[{current + 1}/{total}]{ANSI_RESET}"
                f"{' ' * (ctx.terminal_width - 40)}{ANSI_BOLD}│{ANSI_RESET}"
            )
            lines.append(f"{ANSI_BOLD}└{'─' * (ctx.terminal_width - 2)}┘{ANSI_RESET}")
            lines.append("")
            
            short_hash = state.commit_hash[:8]
            date_str = state.commit_date.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"  {ANSI_BOLD}Commit:{ANSI_RESET} {ANSI_MAGENTA}{short_hash}{ANSI_RESET}  "
                f"{ANSI_BOLD}Author:{ANSI_RESET} {ANSI_GREEN}{state.commit_author}{ANSI_RESET}  "
                f"{ANSI_BOLD}Date:{ANSI_RESET} {date_str}"
            )
            
            msg_preview = state.commit_message[:60]
            if len(state.commit_message) > 60:
                msg_preview += "..."
            lines.append(f"  {ANSI_BOLD}Message:{ANSI_RESET} {msg_preview}")
            lines.append("")
            
            if state.files_changed:
                files_display = ", ".join(state.files_changed[:3])
                if len(state.files_changed) > 3:
                    files_display += f" ... (+{len(state.files_changed) - 3} more)"
                lines.append(
                    f"  {ANSI_BOLD}Files changed:{ANSI_RESET} {files_display} "
                    f"({ANSI_GREEN}+{state.insertions}{ANSI_RESET} / {ANSI_RED}-{state.deletions}{ANSI_RESET})"
                )
            lines.append("")
            
            lines.append(f"  {ANSI_BOLD}─── PROJECT METRICS ───{ANSI_RESET}")
            lines.append("")
            
            ownership = state.ownership_data or {}
            lines.append(f"  {ANSI_BOLD}📁 Code Ownership:{ANSI_RESET}")
            lines.append(f"    Total files: {ownership.get('total_files', 0)}  |  Total lines: {ownership.get('total_lines', 0):,}")
            lines.append(f"    Total authors: {state.total_authors}")
            
            concentration = ownership.get('ownership_concentration', 0)
            conc_color = ANSI_GREEN if concentration < 0.4 else (ANSI_YELLOW if concentration < 0.6 else ANSI_RED)
            primary = ownership.get('primary_author', 'N/A')
            lines.append(
                f"    Ownership concentration: {conc_color}{concentration:.1%}{ANSI_RESET}  "
                f"Primary author: {ANSI_CYAN}{primary}{ANSI_RESET}"
            )
            lines.append("")
            
            zombie = state.zombie_summary or {}
            lines.append(f"  {ANSI_BOLD}💀 Zombie Code (>{days} days stale):{ANSI_RESET}")
            zombie_count = zombie.get('zombie_files', 0)
            zombie_rate = zombie.get('zombie_rate', 0)
            zombie_color = ANSI_GREEN if zombie_rate < 10 else (ANSI_YELLOW if zombie_rate < 30 else ANSI_RED)
            lines.append(
                f"    Zombie files: {zombie_color}{zombie_count}{ANSI_RESET}  "
                f"({zombie_color}{zombie_rate:.1f}%{ANSI_RESET} of total)"
            )
            lines.append("")
            
            health = state.health_report
            if health:
                lines.append(f"  {ANSI_BOLD}❤️  Project Health:{ANSI_RESET}")
                
                score = health.overall_score
                score_color = ANSI_GREEN if score >= 70 else (ANSI_YELLOW if score >= 40 else ANSI_RED)
                
                bar_width = 30
                filled = int(score / 100 * bar_width)
                empty = bar_width - filled
                bar = f"{score_color}{'█' * filled}{ANSI_RESET}{'░' * empty}"
                
                lines.append(f"    Score: [{bar}] {score_color}{score:.1f}{ANSI_RESET}/100")
                
                if score >= 80:
                    status_text = "Excellent"
                    status_color = ANSI_GREEN
                elif score >= 60:
                    status_text = "Good"
                    status_color = ANSI_GREEN
                elif score >= 40:
                    status_text = "Moderate"
                    status_color = ANSI_YELLOW
                else:
                    status_text = "Poor"
                    status_color = ANSI_RED
                
                lines.append(f"    Status: {status_color}{status_text}{ANSI_RESET}")
            lines.append("")
            
            lines.append(f"  {ANSI_BRIGHT_BLACK}Controls: SPACE=Pause/Play  ←→=Step  ↑↓=Fast  Q=Quit{ANSI_RESET}")
            lines.append("")
            
            click.echo("\n".join(lines))
        
        click.echo(f"{ANSI_CYAN}🎬 Starting replay...{ANSI_RESET}")
        click.echo(f"{ANSI_BRIGHT_BLACK}Press any key to continue, or wait for auto-play...{ANSI_RESET}\n")
        
        controller = ReplayController(
            analyzer=analyzer,
            render_callback=render_snapshot,
            speed=speed,
            auto_play=not no_auto_play,
        )
        
        try:
            controller.start()
        except KeyboardInterrupt:
            pass
        
        click.clear()
        print_banner()
        click.echo(f"\n{ANSI_CYAN}✅ Replay session ended.{ANSI_RESET}")
        
    except ValueError as e:
        click.echo(f"{ANSI_RED}Error: {e}{ANSI_RESET}")
        sys.exit(1)


@cli.command("network")
@click.option(
    "-m", "--months",
    type=int,
    default=None,
    help="Number of months to analyze (default: all history)"
)
@click.option(
    "--min-shared",
    type=int,
    default=1,
    help="Minimum shared files for collaboration (default: 1)"
)
@pass_context
def network_cmd(ctx: Context, months: Optional[int], min_shared: int):
    """Show developer collaboration network diagram.
    
    Analyzes which developers frequently modify the same files
    and visualizes their collaboration relationships.
    """
    print_banner()
    
    try:
        extractor = GitDataExtractor(str(ctx.repo_path))
    except ValueError as e:
        click.echo(f"{ANSI_RED}Error: {e}{ANSI_RESET}")
        sys.exit(1)
    
    click.echo(f"{ANSI_CYAN}🕸️  Analyzing developer collaboration network...{ANSI_RESET}")
    
    analyzer = CollaborationAnalyzer(extractor)
    network = analyzer.generate_full_network(
        months=months,
        min_shared_files=min_shared,
    )
    
    renderer = ASCIINetworkRenderer(width=ctx.terminal_width)
    
    click.clear()
    print_banner()
    
    click.echo(renderer.render_network(network))


@cli.command("bus-factor")
@click.option(
    "-n", "--num-files",
    type=int,
    default=20,
    help="Number of high-risk files to show (default: 20)"
)
@click.option(
    "--high-threshold",
    type=float,
    default=90.0,
    help="High risk percentage threshold (default: 90.0%)"
)
@click.option(
    "--medium-threshold",
    type=float,
    default=60.0,
    help="Medium risk percentage threshold (default: 60.0%)"
)
@pass_context
def bus_factor_cmd(
    ctx: Context, 
    num_files: int, 
    high_threshold: float, 
    medium_threshold: float
):
    """Analyze bus factor risk - files with single owners.
    
    Bus factor measures how many developers would need to be "hit by a bus"
    before the project becomes unmaintainable. This command identifies
    files that have only one contributor or are highly concentrated.
    """
    print_banner()
    
    try:
        extractor = GitDataExtractor(str(ctx.repo_path))
    except ValueError as e:
        click.echo(f"{ANSI_RED}Error: {e}{ANSI_RESET}")
        sys.exit(1)
    
    click.echo(f"{ANSI_CYAN}🚨 Analyzing bus factor risk...{ANSI_RESET}")
    
    analyzer = CollaborationAnalyzer(extractor)
    
    risks = analyzer.analyze_bus_factor(
        risk_threshold_high=high_threshold,
        risk_threshold_medium=medium_threshold,
    )
    
    network = analyzer.generate_full_network()
    
    renderer = ASCIINetworkRenderer(width=ctx.terminal_width)
    
    click.clear()
    print_banner()
    
    click.echo(renderer.render_bus_factor_report(network, max_items=num_files))


def main():
    """Entry point for the command line interface."""
    cli()


if __name__ == "__main__":
    main()
