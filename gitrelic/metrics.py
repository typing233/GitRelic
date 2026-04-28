"""Metrics Calculation and Health Scoring Module

This module aggregates metrics from all analyzers and calculates
an overall project health score with weighted components.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class MetricScore:
    """Data class representing a single metric with score."""
    name: str
    display_name: str
    raw_value: float
    normalized_score: float  # 0-100
    weight: float  # Relative weight for overall score
    description: str


@dataclass
class HealthReport:
    """Data class representing a complete health report."""
    overall_score: float = 0.0
    metrics: Dict[str, MetricScore] = field(default_factory=dict)
    radar_data: Dict = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.now)
    recommendations: List[str] = field(default_factory=list)


class MetricsCalculator:
    """Calculator for project health metrics and overall score.

    This class aggregates data from:
    - Ownership analysis (ownership concentration)
    - Zombie function detection
    - TODO/comment tag tracking
    - Commit activity
    """

    DEFAULT_WEIGHTS = {
        "ownership_concentration": 0.20,
        "zombie_functions": 0.20,
        "todo_density": 0.20,
        "high_priority_todos": 0.15,
        "commit_activity": 0.15,
        "author_distribution": 0.10,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize the MetricsCalculator.

        Args:
            weights: Optional custom weights for metrics. Must sum to 1.0.
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def calculate_ownership_score(
        self,
        concentration: float,
        num_authors: int = 1
    ) -> MetricScore:
        """Calculate score for ownership concentration.

        Args:
            concentration: Ownership concentration (0-1, HHI normalized).
            num_authors: Number of unique authors.

        Returns:
            MetricScore object.
        """
        if num_authors <= 1:
            score = 20.0
        elif concentration <= 0.2:
            score = 100.0
        elif concentration <= 0.4:
            score = 80.0
        elif concentration <= 0.6:
            score = 60.0
        elif concentration <= 0.8:
            score = 40.0
        else:
            score = 20.0

        return MetricScore(
            name="ownership_concentration",
            display_name="Ownership Concentration",
            raw_value=concentration,
            normalized_score=score,
            weight=self.weights.get("ownership_concentration", 0.20),
            description=(
                f"Ownership concentration is {concentration:.1%}. "
                f"{'High concentration may indicate bus factor risk.' if concentration > 0.5 else 'Good distribution of ownership.'}"
            ),
        )

    def calculate_author_distribution_score(
        self,
        total_commits: int,
        author_commits: Dict[str, int]
    ) -> MetricScore:
        """Calculate score for author commit distribution.

        Args:
            total_commits: Total number of commits.
            author_commits: Dictionary mapping authors to their commit counts.

        Returns:
            MetricScore object.
        """
        if not author_commits or total_commits == 0:
            return MetricScore(
                name="author_distribution",
                display_name="Author Distribution",
                raw_value=0.0,
                normalized_score=50.0,
                weight=self.weights.get("author_distribution", 0.10),
                description="No commit data available.",
            )

        num_authors = len(author_commits)
        sorted_counts = sorted(author_commits.values(), reverse=True)

        top_author_percent = sorted_counts[0] / total_commits if total_commits > 0 else 0

        if num_authors == 1:
            score = 10.0
        elif num_authors == 2:
            score = 30.0
        else:
            if top_author_percent <= 0.3:
                score = 90.0
            elif top_author_percent <= 0.5:
                score = 70.0
            elif top_author_percent <= 0.7:
                score = 50.0
            else:
                score = 30.0

        return MetricScore(
            name="author_distribution",
            display_name="Author Distribution",
            raw_value=top_author_percent,
            normalized_score=score,
            weight=self.weights.get("author_distribution", 0.10),
            description=(
                f"Top author contributed {top_author_percent:.1%} of commits. "
                f"{'Good team distribution.' if top_author_percent < 0.5 else 'High concentration by single author.'}"
            ),
        )

    def calculate_zombie_score(
        self,
        total_functions: int,
        zombie_functions: int
    ) -> MetricScore:
        """Calculate score for zombie functions.

        Args:
            total_functions: Total number of functions.
            zombie_functions: Number of zombie functions.

        Returns:
            MetricScore object.
        """
        if total_functions == 0:
            return MetricScore(
                name="zombie_functions",
                display_name="Zombie Functions",
                raw_value=0.0,
                normalized_score=80.0,
                weight=self.weights.get("zombie_functions", 0.20),
                description="No functions found to analyze.",
            )

        zombie_rate = zombie_functions / total_functions

        if zombie_rate == 0:
            score = 100.0
        elif zombie_rate <= 0.05:
            score = 90.0
        elif zombie_rate <= 0.10:
            score = 70.0
        elif zombie_rate <= 0.20:
            score = 50.0
        elif zombie_rate <= 0.30:
            score = 30.0
        else:
            score = 10.0

        return MetricScore(
            name="zombie_functions",
            display_name="Zombie Functions",
            raw_value=zombie_rate,
            normalized_score=score,
            weight=self.weights.get("zombie_functions", 0.20),
            description=(
                f"{zombie_functions} zombie functions found ({zombie_rate:.1%} of total). "
                f"{'Consider cleaning up unused code.' if zombie_rate > 0.05 else 'Minimal dead code detected.'}"
            ),
        )

    def calculate_todo_density_score(
        self,
        todo_density_per_kilo: float,
        total_tags: int
    ) -> MetricScore:
        """Calculate score for TODO density.

        Args:
            todo_density_per_kilo: Number of TODOs per 1000 lines of code.
            total_tags: Total number of comment tags.

        Returns:
            MetricScore object.
        """
        if todo_density_per_kilo <= 1.0:
            score = 100.0
        elif todo_density_per_kilo <= 3.0:
            score = 85.0
        elif todo_density_per_kilo <= 5.0:
            score = 70.0
        elif todo_density_per_kilo <= 10.0:
            score = 50.0
        elif todo_density_per_kilo <= 20.0:
            score = 30.0
        else:
            score = 10.0

        return MetricScore(
            name="todo_density",
            display_name="TODO Density",
            raw_value=todo_density_per_kilo,
            normalized_score=score,
            weight=self.weights.get("todo_density", 0.20),
            description=(
                f"TODO density: {todo_density_per_kilo:.2f} per 1000 lines ({total_tags} total tags). "
                f"{'High number of pending tasks.' if todo_density_per_kilo > 5 else 'Acceptable level of technical debt notes.'}"
            ),
        )

    def calculate_high_priority_todo_score(
        self,
        high_priority_count: int,
        total_tags: int
    ) -> MetricScore:
        """Calculate score for high priority TODOs (FIXME, HACK, BUG, etc.).

        Args:
            high_priority_count: Number of high priority tags.
            total_tags: Total number of comment tags.

        Returns:
            MetricScore object.
        """
        if total_tags == 0:
            ratio = 0.0
        else:
            ratio = high_priority_count / total_tags

        if high_priority_count == 0:
            score = 100.0
        elif high_priority_count <= 2:
            score = 90.0
        elif high_priority_count <= 5:
            score = 70.0
        elif high_priority_count <= 10:
            score = 50.0
        elif high_priority_count <= 20:
            score = 30.0
        else:
            score = 10.0

        return MetricScore(
            name="high_priority_todos",
            display_name="High Priority TODOs",
            raw_value=high_priority_count,
            normalized_score=score,
            weight=self.weights.get("high_priority_todos", 0.15),
            description=(
                f"{high_priority_count} high priority tags (FIXME, HACK, BUG, etc.) "
                f"found ({ratio:.1%} of total). "
                f"{'Critical issues need attention!' if high_priority_count > 5 else 'Few critical issues detected.'}"
            ),
        )

    def calculate_activity_score(
        self,
        commits_in_period: int,
        months: int = 12,
        active_authors: int = 1
    ) -> MetricScore:
        """Calculate score for commit activity.

        Args:
            commits_in_period: Number of commits in the period.
            months: Number of months in the period.
            active_authors: Number of active authors.

        Returns:
            MetricScore object.
        """
        commits_per_month = commits_in_period / max(1, months)

        if commits_per_month >= 20:
            score = 100.0
        elif commits_per_month >= 10:
            score = 90.0
        elif commits_per_month >= 5:
            score = 75.0
        elif commits_per_month >= 2:
            score = 60.0
        elif commits_per_month >= 1:
            score = 40.0
        else:
            score = 10.0

        if active_authors > 3:
            score = min(100.0, score + 10)

        return MetricScore(
            name="commit_activity",
            display_name="Commit Activity",
            raw_value=commits_per_month,
            normalized_score=score,
            weight=self.weights.get("commit_activity", 0.15),
            description=(
                f"Average {commits_per_month:.1f} commits/month with {active_authors} active authors. "
                f"{'Good development velocity.' if commits_per_month >= 5 else 'Low activity - project may be stale.'}"
            ),
        )

    def calculate_overall_score(
        self,
        metrics: Dict[str, MetricScore]
    ) -> float:
        """Calculate weighted overall health score.

        Args:
            metrics: Dictionary of MetricScore objects.

        Returns:
            Overall score (0-100).
        """
        total_weight = 0.0
        weighted_sum = 0.0

        for metric_name, metric in metrics.items():
            weighted_sum += metric.normalized_score * metric.weight
            total_weight += metric.weight

        if total_weight == 0:
            return 50.0

        return weighted_sum / total_weight

    def generate_recommendations(
        self,
        metrics: Dict[str, MetricScore],
        context: Optional[Dict] = None
    ) -> List[str]:
        """Generate actionable recommendations based on metrics.

        Args:
            metrics: Dictionary of MetricScore objects.
            context: Optional context dictionary with additional data.

        Returns:
            List of recommendation strings.
        """
        recommendations = []
        context = context or {}

        ownership = metrics.get("ownership_concentration")
        if ownership and ownership.normalized_score < 50:
            recommendations.append(
                "⚠️  High code ownership concentration detected. "
                "Consider knowledge sharing to reduce bus factor risk."
            )

        zombie = metrics.get("zombie_functions")
        if zombie and zombie.normalized_score < 60:
            zombie_count = context.get("zombie_count", 0)
            recommendations.append(
                f"⚠️  Found {zombie_count} zombie functions (unused, stale code). "
                "Consider cleanup to reduce technical debt."
            )

        high_priority = metrics.get("high_priority_todos")
        if high_priority and high_priority.normalized_score < 60:
            hp_count = context.get("high_priority_count", 0)
            recommendations.append(
                f"🚨 {hp_count} high priority issues (FIXME, HACK, BUG) detected. "
                "These should be addressed urgently."
            )

        todo_density = metrics.get("todo_density")
        if todo_density and todo_density.normalized_score < 50:
            density = todo_density.raw_value
            recommendations.append(
                f"📝 High TODO density ({density:.1f} per 1000 lines). "
                "Consider scheduling time to work through pending tasks."
            )

        activity = metrics.get("commit_activity")
        if activity and activity.normalized_score < 40:
            recommendations.append(
                "📉 Low commit activity detected. "
                "Project may be stale or needs more regular contributions."
            )

        if not recommendations:
            recommendations.append(
                "✅ All metrics look good! Keep up the good work."
            )

        return recommendations

    def prepare_radar_data(
        self,
        metrics: Dict[str, MetricScore]
    ) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Prepare data for radar chart visualization.

        Args:
            metrics: Dictionary of MetricScore objects.

        Returns:
            Tuple of (raw_values_dict, scores_dict, overall_score)
        """
        raw_values: Dict[str, float] = {}
        scores: Dict[str, float] = {}

        display_names = {
            "ownership_concentration": "Ownership",
            "author_distribution": "Team Health",
            "zombie_functions": "Code Quality",
            "todo_density": "TODO Load",
            "high_priority_todos": "Critical Issues",
            "commit_activity": "Activity",
        }

        for metric_name, metric in metrics.items():
            display_name = display_names.get(metric_name, metric.display_name)
            raw_values[display_name] = metric.raw_value
            scores[display_name] = metric.normalized_score

        overall_score = self.calculate_overall_score(metrics)

        return raw_values, scores, overall_score

    def generate_health_report(
        self,
        ownership_data: Dict,
        zombie_data: Dict,
        todo_data: Dict,
        activity_data: Dict,
    ) -> HealthReport:
        """Generate a complete health report from all analyzer data.

        Args:
            ownership_data: Data from ownership analysis.
            zombie_data: Data from zombie function scan.
            todo_data: Data from TODO scan.
            activity_data: Data from commit activity analysis.

        Returns:
            HealthReport object with all metrics and overall score.
        """
        metrics: Dict[str, MetricScore] = {}
        context: Dict = {}

        root_dir = ownership_data.get("root")
        if root_dir:
            concentration = getattr(root_dir, "ownership_concentration", 0.5)
            num_authors = len(getattr(root_dir, "author_lines", {}))
            metrics["ownership_concentration"] = self.calculate_ownership_score(
                concentration, num_authors
            )

        zombie_count = zombie_data.get("zombie_count", 0)
        total_functions = zombie_data.get("total_functions", 1)
        metrics["zombie_functions"] = self.calculate_zombie_score(
            total_functions, zombie_count
        )
        context["zombie_count"] = zombie_count

        todo_density = todo_data.get("todo_density_per_kilo", 0.0)
        total_tags = todo_data.get("total_tags", 0)
        metrics["todo_density"] = self.calculate_todo_density_score(
            todo_density, total_tags
        )

        by_severity = todo_data.get("by_severity", {})
        high_priority_count = by_severity.get("high", 0)
        metrics["high_priority_todos"] = self.calculate_high_priority_todo_score(
            high_priority_count, total_tags
        )
        context["high_priority_count"] = high_priority_count

        total_commits = activity_data.get("total_commits", 0)
        authors = activity_data.get("authors", [])
        activity = activity_data.get("activity", {})

        author_commits: Dict[str, int] = {}
        for month_data in activity.values():
            for author, count in month_data.items():
                author_commits[author] = author_commits.get(author, 0) + count

        if author_commits:
            metrics["author_distribution"] = self.calculate_author_distribution_score(
                total_commits, author_commits
            )

        metrics["commit_activity"] = self.calculate_activity_score(
            total_commits, months=12, active_authors=len(authors)
        )

        overall_score = self.calculate_overall_score(metrics)

        raw_values, scores, _ = self.prepare_radar_data(metrics)

        recommendations = self.generate_recommendations(metrics, context)

        return HealthReport(
            overall_score=overall_score,
            metrics=metrics,
            radar_data={
                "raw_values": raw_values,
                "scores": scores,
            },
            recommendations=recommendations,
        )
