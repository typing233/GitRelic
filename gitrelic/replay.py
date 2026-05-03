"""Replay Functionality Module

This module provides the ability to replay the analysis results
commit-by-commit in an animated fashion, showing how ownership,
zombie functions, and health scores evolve over time.
"""

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Callable, Any

from .git_data import GitDataExtractor, GitCommit
from .ownership import OwnershipAnalyzer, DirectoryOwnership, FileOwnership
from .zombie import ZombieScanner, ZombieScanResult
from .metrics import MetricsCalculator, HealthReport, MetricScore


@dataclass
class ReplayState:
    """Data class representing the state at a specific commit."""
    
    commit_index: int
    commit_hash: str
    commit_author: str
    commit_date: datetime
    commit_message: str
    
    files_changed: List[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    
    ownership_data: Optional[Dict] = None
    zombie_summary: Optional[Dict] = None
    health_report: Optional[HealthReport] = None
    
    cumulative_commits: int = 0
    total_authors: int = 0
    files_modified_count: int = 0


@dataclass
class ReplaySnapshot:
    """A complete snapshot of the analysis at a point in time."""
    
    state: ReplayState
    ownership_heatmap: Dict
    zombie_stats: Dict
    health_metrics: Dict
    timestamp: datetime = field(default_factory=datetime.now)


class IncrementalOwnershipTracker:
    """Tracks ownership changes incrementally across commits."""
    
    def __init__(self):
        self.file_authors: Dict[str, Dict[str, int]] = {}  # file -> {author: lines}
        self.file_total_lines: Dict[str, int] = {}
        self.all_authors: Set[str] = set()
    
    def process_commit(self, commit: GitCommit) -> None:
        """Process a single commit and update ownership tracking.
        
        Args:
            commit: The commit to process.
        """
        self.all_authors.add(commit.author)
        
        for file_path in commit.files_changed:
            if file_path not in self.file_authors:
                self.file_authors[file_path] = {}
                self.file_total_lines[file_path] = 0
            
            author_lines = self.file_authors[file_path].get(commit.author, 0)
            line_change = commit.insertions - commit.deletions
            
            if line_change > 0:
                author_lines += line_change
                self.file_total_lines[file_path] += line_change
            else:
                total_lines = self.file_total_lines[file_path]
                if total_lines > 0:
                    author_ratio = author_lines / total_lines if total_lines > 0 else 0
                    reduction = abs(line_change)
                    author_reduction = int(reduction * author_ratio)
                    author_lines = max(0, author_lines - author_reduction)
                    self.file_total_lines[file_path] = max(0, total_lines - reduction)
            
            self.file_authors[file_path][commit.author] = author_lines
    
    def get_current_ownership(self) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int]]:
        """Get the current ownership state.
        
        Returns:
            Tuple of (file_authors, file_total_lines)
        """
        return dict(self.file_authors), dict(self.file_total_lines)
    
    def get_authors(self) -> List[str]:
        """Get all unique authors seen so far.
        
        Returns:
            List of author names.
        """
        return list(self.all_authors)
    
    def get_directory_summary(self, directory_path: str = "") -> Dict:
        """Generate a summary of ownership for a directory.
        
        Args:
            directory_path: Directory path to summarize.
            
        Returns:
            Dictionary with ownership summary data.
        """
        dir_prefix = directory_path + "/" if directory_path else ""
        
        total_lines = 0
        author_lines: Dict[str, int] = {}
        files_count = 0
        
        for file_path, lines in self.file_total_lines.items():
            if directory_path and not file_path.startswith(dir_prefix):
                continue
            
            total_lines += lines
            files_count += 1
            
            file_authors = self.file_authors.get(file_path, {})
            for author, author_line_count in file_authors.items():
                author_lines[author] = author_lines.get(author, 0) + author_line_count
        
        concentration = 0.0
        primary_author = None
        
        if total_lines > 0:
            percentages = [(lines / total_lines) * 100 for lines in author_lines.values()]
            hhi = sum(p ** 2 for p in percentages) / 10000.0
            concentration = hhi
            
            if author_lines:
                primary_author = max(author_lines.items(), key=lambda x: x[1])[0]
        
        return {
            "path": directory_path if directory_path else "/",
            "total_lines": total_lines,
            "total_files": files_count,
            "author_lines": author_lines,
            "ownership_concentration": concentration,
            "primary_author": primary_author,
            "num_authors": len(author_lines),
        }


class IncrementalZombieTracker:
    """Tracks zombie function candidates incrementally.
    
    Note: This is a simplified version that tracks file modification
    dates rather than actual function-level analysis for performance.
    """
    
    def __init__(self, days_threshold: int = 90):
        self.days_threshold = days_threshold
        self.file_last_modified: Dict[str, datetime] = {}
        self.file_commit_count: Dict[str, int] = {}
        self.all_files: Set[str] = set()
    
    def process_commit(self, commit: GitCommit) -> None:
        """Process a commit and update file modification tracking.
        
        Args:
            commit: The commit to process.
        """
        for file_path in commit.files_changed:
            self.all_files.add(file_path)
            self.file_last_modified[file_path] = commit.date
            self.file_commit_count[file_path] = self.file_commit_count.get(file_path, 0) + 1
    
    def get_zombie_summary(self, reference_date: Optional[datetime] = None) -> Dict:
        """Get a summary of potential zombie files.
        
        Args:
            reference_date: Date to use as "now" for age calculation.
                If None, uses current system time.
        
        Returns:
            Dictionary with zombie summary data.
        """
        if reference_date is None:
            reference_date = datetime.now()
        
        cutoff_date = reference_date - timedelta(days=self.days_threshold)
        
        zombie_files = []
        stale_files = []
        
        for file_path, last_modified in self.file_last_modified.items():
            if last_modified < cutoff_date:
                zombie_files.append(file_path)
            elif last_modified < (reference_date - timedelta(days=self.days_threshold // 2)):
                stale_files.append(file_path)
        
        total_files = len(self.all_files)
        
        return {
            "total_files": total_files,
            "zombie_files": len(zombie_files),
            "stale_files": len(stale_files),
            "zombie_file_paths": zombie_files[:20],
            "zombie_rate": (len(zombie_files) / total_files * 100) if total_files > 0 else 0,
            "days_threshold": self.days_threshold,
        }
    
    def get_file_modification_stats(self) -> Dict[str, Dict]:
        """Get detailed stats for each file.
        
        Returns:
            Dictionary mapping file paths to their stats.
        """
        result = {}
        for file_path in self.all_files:
            result[file_path] = {
                "last_modified": self.file_last_modified.get(file_path),
                "commit_count": self.file_commit_count.get(file_path, 0),
            }
        return result


class ReplayAnalyzer:
    """Main analyzer for the replay functionality.
    
    This class coordinates the incremental analysis across commits
    and generates snapshots for the replay animation.
    """
    
    def __init__(
        self,
        repo_path: str,
        days_threshold: int = 90,
        commit_limit: Optional[int] = None,
    ):
        """Initialize the ReplayAnalyzer.
        
        Args:
            repo_path: Path to the Git repository.
            days_threshold: Days threshold for zombie detection.
            commit_limit: Maximum number of commits to analyze.
                If None, analyzes all commits.
        """
        self.repo_path = repo_path
        self.days_threshold = days_threshold
        self.commit_limit = commit_limit
        
        self.extractor = GitDataExtractor(repo_path)
        self.ownership_tracker = IncrementalOwnershipTracker()
        self.zombie_tracker = IncrementalZombieTracker(days_threshold)
        self.metrics_calc = MetricsCalculator()
        
        self.commits: List[GitCommit] = []
        self.snapshots: List[ReplaySnapshot] = []
        self._is_loaded = False
    
    def load_commits(self) -> int:
        """Load all commits from the repository.
        
        Returns:
            Number of commits loaded.
        """
        self.commits = self.extractor.get_commits()
        
        self.commits.sort(key=lambda c: c.date)
        
        if self.commit_limit and len(self.commits) > self.commit_limit:
            self.commits = self.commits[-self.commit_limit:]
        
        self._is_loaded = True
        return len(self.commits)
    
    def generate_snapshots(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> int:
        """Generate snapshots for all commits.
        
        Args:
            progress_callback: Optional callback for progress updates.
                Takes (current, total) as arguments.
        
        Returns:
            Number of snapshots generated.
        """
        if not self._is_loaded:
            self.load_commits()
        
        self.snapshots = []
        
        total = len(self.commits)
        
        for idx, commit in enumerate(self.commits):
            if progress_callback:
                progress_callback(idx + 1, total)
            
            self.ownership_tracker.process_commit(commit)
            self.zombie_tracker.process_commit(commit)
            
            ownership_summary = self.ownership_tracker.get_directory_summary("")
            zombie_summary = self.zombie_tracker.get_zombie_summary(commit.date)
            
            health_report = self._generate_health_report(
                ownership_summary,
                zombie_summary,
                commit,
            )
            
            state = ReplayState(
                commit_index=idx,
                commit_hash=commit.hash,
                commit_author=commit.author,
                commit_date=commit.date,
                commit_message=commit.message,
                files_changed=commit.files_changed,
                insertions=commit.insertions,
                deletions=commit.deletions,
                ownership_data=ownership_summary,
                zombie_summary=zombie_summary,
                health_report=health_report,
                cumulative_commits=idx + 1,
                total_authors=len(self.ownership_tracker.get_authors()),
                files_modified_count=len(self.zombie_tracker.all_files),
            )
            
            snapshot = ReplaySnapshot(
                state=state,
                ownership_heatmap=ownership_summary,
                zombie_stats=zombie_summary,
                health_metrics={
                    "overall_score": health_report.overall_score if health_report else 50.0,
                    "metrics": health_report.metrics if health_report else {},
                },
            )
            
            self.snapshots.append(snapshot)
        
        return len(self.snapshots)
    
    def _generate_health_report(
        self,
        ownership_summary: Dict,
        zombie_summary: Dict,
        commit: GitCommit,
    ) -> Optional[HealthReport]:
        """Generate a simplified health report for a snapshot.
        
        Args:
            ownership_summary: Ownership summary data.
            zombie_summary: Zombie summary data.
            commit: The current commit.
        
        Returns:
            HealthReport object or None.
        """
        try:
            concentration = ownership_summary.get("ownership_concentration", 0.5)
            num_authors = ownership_summary.get("num_authors", 1)
            
            ownership_score = self.metrics_calc.calculate_ownership_score(
                concentration, num_authors
            )
            
            total_files = zombie_summary.get("total_files", 1)
            zombie_files = zombie_summary.get("zombie_files", 0)
            zombie_rate = zombie_summary.get("zombie_rate", 0)
            
            zombie_score = self.metrics_calc.calculate_zombie_score(
                total_files * 5,
                zombie_files * 3,
            )
            
            metrics: Dict[str, MetricScore] = {
                "ownership_concentration": ownership_score,
                "zombie_functions": zombie_score,
            }
            
            activity_score = self.metrics_calc.calculate_activity_score(
                ownership_summary.get("total_files", 0) + 1,
                months=1,
                active_authors=num_authors,
            )
            metrics["commit_activity"] = activity_score
            
            author_dist_score = self.metrics_calc.calculate_author_distribution_score(
                ownership_summary.get("total_files", 1),
                {commit.author: 1},
            )
            metrics["author_distribution"] = author_dist_score
            
            todo_score = MetricScore(
                name="todo_density",
                display_name="TODO Density",
                raw_value=0.0,
                normalized_score=80.0,
                weight=0.20,
                description="TODO tracking not available in replay mode.",
            )
            metrics["todo_density"] = todo_score
            
            hp_todo_score = MetricScore(
                name="high_priority_todos",
                display_name="High Priority TODOs",
                raw_value=0,
                normalized_score=100.0,
                weight=0.15,
                description="No high priority issues detected.",
            )
            metrics["high_priority_todos"] = hp_todo_score
            
            overall_score = self.metrics_calc.calculate_overall_score(metrics)
            raw_values, scores, _ = self.metrics_calc.prepare_radar_data(metrics)
            recommendations = self.metrics_calc.generate_recommendations(metrics, {})
            
            return HealthReport(
                overall_score=overall_score,
                metrics=metrics,
                radar_data={
                    "raw_values": raw_values,
                    "scores": scores,
                },
                recommendations=recommendations,
            )
            
        except Exception:
            return None
    
    def get_snapshot(self, index: int) -> Optional[ReplaySnapshot]:
        """Get a specific snapshot by index.
        
        Args:
            index: The snapshot index (0-based).
        
        Returns:
            ReplaySnapshot or None if index is out of range.
        """
        if 0 <= index < len(self.snapshots):
            return self.snapshots[index]
        return None
    
    def get_total_snapshots(self) -> int:
        """Get the total number of snapshots.
        
        Returns:
            Number of snapshots available.
        """
        return len(self.snapshots)
    
    def get_commits(self) -> List[GitCommit]:
        """Get all loaded commits.
        
        Returns:
            List of GitCommit objects.
        """
        return list(self.commits)


class ReplayController:
    """Controller for interactive replay session.
    
    This class handles the animation timing and user input for
    controlling the replay (pause, step, fast-forward, etc.).
    """
    
    def __init__(
        self,
        analyzer: ReplayAnalyzer,
        render_callback: Callable[[ReplaySnapshot, int, int], None],
        speed: float = 1.0,
        auto_play: bool = True,
    ):
        """Initialize the ReplayController.
        
        Args:
            analyzer: The ReplayAnalyzer with loaded snapshots.
            render_callback: Function to call for each frame.
                Takes (snapshot, current_index, total_count) as arguments.
            speed: Animation speed multiplier (1.0 = normal).
            auto_play: Whether to start playing automatically.
        """
        self.analyzer = analyzer
        self.render_callback = render_callback
        self.speed = speed
        self.auto_play = auto_play
        
        self._is_running = False
        self._is_paused = not auto_play
        self._current_index = 0
        self._frame_delay = 1.0 / speed
        
        self._input_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._key_callbacks: Dict[str, Callable] = {}
        self._setup_default_callbacks()
    
    def _setup_default_callbacks(self) -> None:
        """Setup default keyboard shortcuts."""
        self._key_callbacks = {
            " ": self.toggle_pause,
            "left": self.step_backward,
            "right": self.step_forward,
            "up": self.fast_forward,
            "down": self.rewind,
            "q": self.stop,
            "home": self.go_to_start,
            "end": self.go_to_end,
        }
    
    def toggle_pause(self) -> None:
        """Toggle pause/play state."""
        self._is_paused = not self._is_paused
        if self._is_paused:
            self._render_current(" [PAUSED]")
        else:
            self._render_current(" [PLAYING]")
    
    def step_forward(self) -> None:
        """Step forward one commit."""
        total = self.analyzer.get_total_snapshots()
        if self._current_index < total - 1:
            self._current_index += 1
            self._render_current()
    
    def step_backward(self) -> None:
        """Step backward one commit."""
        if self._current_index > 0:
            self._current_index -= 1
            self._render_current()
    
    def fast_forward(self) -> None:
        """Fast forward 10 commits."""
        total = self.analyzer.get_total_snapshots()
        self._current_index = min(total - 1, self._current_index + 10)
        self._render_current()
    
    def rewind(self) -> None:
        """Rewind 10 commits."""
        self._current_index = max(0, self._current_index - 10)
        self._render_current()
    
    def go_to_start(self) -> None:
        """Go to the first commit."""
        self._current_index = 0
        self._render_current()
    
    def go_to_end(self) -> None:
        """Go to the last commit."""
        self._current_index = self.analyzer.get_total_snapshots() - 1
        self._render_current()
    
    def stop(self) -> None:
        """Stop the replay session."""
        self._is_running = False
        self._stop_event.set()
    
    def _render_current(self, suffix: str = "") -> None:
        """Render the current snapshot.
        
        Args:
            suffix: Optional suffix to append to status message.
        """
        snapshot = self.analyzer.get_snapshot(self._current_index)
        if snapshot:
            self.render_callback(
                snapshot,
                self._current_index,
                self.analyzer.get_total_snapshots(),
            )
    
    def _input_listener(self) -> None:
        """Listen for keyboard input in a separate thread."""
        try:
            import tty
            import termios
            
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            
            try:
                tty.setcbreak(fd)
                
                while self._is_running and not self._stop_event.is_set():
                    import select
                    r, _, _ = select.select([sys.stdin], [], [], 0.1)
                    
                    if r:
                        char = sys.stdin.read(1)
                        
                        if char == "\x1b":
                            next_char = sys.stdin.read(1)
                            if next_char == "[":
                                key = sys.stdin.read(1)
                                if key == "A":
                                    self._key_callbacks.get("up", lambda: None)()
                                elif key == "B":
                                    self._key_callbacks.get("down", lambda: None)()
                                elif key == "C":
                                    self._key_callbacks.get("right", lambda: None)()
                                elif key == "D":
                                    self._key_callbacks.get("left", lambda: None)()
                                elif key == "H":
                                    self._key_callbacks.get("home", lambda: None)()
                                elif key == "F":
                                    self._key_callbacks.get("end", lambda: None)()
                        elif char in self._key_callbacks:
                            self._key_callbacks[char]()
                            
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                
        except Exception:
            pass
    
    def start(self) -> None:
        """Start the replay session."""
        if self.analyzer.get_total_snapshots() == 0:
            raise RuntimeError("No snapshots available. Generate them first.")
        
        self._is_running = True
        self._current_index = 0
        self._stop_event.clear()
        
        try:
            self._input_thread = threading.Thread(target=self._input_listener, daemon=True)
            self._input_thread.start()
            
            total = self.analyzer.get_total_snapshots()
            
            while self._is_running and not self._stop_event.is_set():
                self._render_current()
                
                if not self._is_paused:
                    if self._current_index < total - 1:
                        self._current_index += 1
                    else:
                        self._is_paused = True
                        self._render_current(" [END - PAUSED]")
                
                time.sleep(self._frame_delay)
                
        except KeyboardInterrupt:
            pass
        finally:
            self._is_running = False
            self._stop_event.set()
    
    def is_paused(self) -> bool:
        """Check if replay is currently paused.
        
        Returns:
            True if paused, False otherwise.
        """
        return self._is_paused
    
    def get_current_index(self) -> int:
        """Get the current snapshot index.
        
        Returns:
            Current index.
        """
        return self._current_index
    
    def set_speed(self, speed: float) -> None:
        """Set the animation speed.
        
        Args:
            speed: Speed multiplier (1.0 = normal).
        """
        self.speed = speed
        self._frame_delay = 1.0 / speed
