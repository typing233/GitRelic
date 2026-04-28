"""Terminal Renderer Module

This module handles rendering of various charts and visualizations
using ANSI escape codes for terminal output.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_ITALIC = "\033[3m"
ANSI_UNDERLINE = "\033[4m"

ANSI_BLACK = "\033[30m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN = "\033[36m"
ANSI_WHITE = "\033[37m"

ANSI_BG_BLACK = "\033[40m"
ANSI_BG_RED = "\033[41m"
ANSI_BG_GREEN = "\033[42m"
ANSI_BG_YELLOW = "\033[43m"
ANSI_BG_BLUE = "\033[44m"
ANSI_BG_MAGENTA = "\033[45m"
ANSI_BG_CYAN = "\033[46m"
ANSI_BG_WHITE = "\033[47m"

ANSI_BRIGHT_BLACK = "\033[90m"
ANSI_BRIGHT_RED = "\033[91m"
ANSI_BRIGHT_GREEN = "\033[92m"
ANSI_BRIGHT_YELLOW = "\033[93m"
ANSI_BRIGHT_BLUE = "\033[94m"
ANSI_BRIGHT_MAGENTA = "\033[95m"
ANSI_BRIGHT_CYAN = "\033[96m"
ANSI_BRIGHT_WHITE = "\033[97m"

AUTHOR_COLORS = [
    ANSI_GREEN,
    ANSI_BLUE,
    ANSI_YELLOW,
    ANSI_MAGENTA,
    ANSI_CYAN,
    ANSI_RED,
    ANSI_BRIGHT_GREEN,
    ANSI_BRIGHT_BLUE,
    ANSI_BRIGHT_YELLOW,
    ANSI_BRIGHT_MAGENTA,
]


@dataclass
class ColorScheme:
    """Color scheme configuration for visualizations."""
    good: str = ANSI_GREEN
    moderate: str = ANSI_YELLOW
    bad: str = ANSI_RED
    neutral: str = ANSI_CYAN
    highlight: str = ANSI_MAGENTA
    dim: str = ANSI_BRIGHT_BLACK


DEFAULT_COLOR_SCHEME = ColorScheme()


class TerminalRenderer:
    """Renderer for terminal-based visualizations using ANSI escape codes."""

    def __init__(self, color_scheme: Optional[ColorScheme] = None, width: int = 80):
        """Initialize the terminal renderer.

        Args:
            color_scheme: Color scheme to use.
            width: Terminal width for rendering.
        """
        self.color_scheme = color_scheme or DEFAULT_COLOR_SCHEME
        self.width = width

    def _color_by_value(
        self,
        value: float,
        min_val: float = 0.0,
        max_val: float = 1.0,
        reverse: bool = False
    ) -> str:
        """Get color based on a numerical value.

        Args:
            value: The value to map to a color.
            min_val: Minimum value for scaling.
            max_val: Maximum value for scaling.
            reverse: If True, high values are bad (red), low values good (green).

        Returns:
            ANSI color code.
        """
        if max_val == min_val:
            normalized = 0.5
        else:
            normalized = max(0, min(1, (value - min_val) / (max_val - min_val)))

        if reverse:
            normalized = 1 - normalized

        if normalized >= 0.7:
            return self.color_scheme.good
        elif normalized >= 0.4:
            return self.color_scheme.moderate
        else:
            return self.color_scheme.bad

    def _color_heatmap_cell(self, concentration: float, primary_author: Optional[str], author_index: int = 0) -> str:
        """Get background color for heatmap cell based on ownership concentration.

        Args:
            concentration: Ownership concentration (0-1).
            primary_author: Primary author name.
            author_index: Index for cycling author colors.

        Returns:
            ANSI background color code.
        """
        if concentration >= 0.8:
            return ANSI_BG_RED
        elif concentration >= 0.5:
            return ANSI_BG_YELLOW
        elif concentration >= 0.25:
            return ANSI_BG_GREEN
        else:
            return ANSI_BG_CYAN

    def render_heatmap(
        self,
        heatmap_data: Dict,
        max_items: int = 30,
        show_authors: bool = True
    ) -> str:
        """Render a code ownership heatmap.

        Args:
            heatmap_data: Data from OwnershipAnalyzer.get_ownership_heatmap_data()
            max_items: Maximum number of items to display.
            show_authors: Whether to show author legend.

        Returns:
            String with ANSI escape codes for terminal rendering.
        """
        lines = []

        lines.append(f"\n{ANSI_BOLD}{ANSI_UNDERLINE}CODE OWNERSHIP HEATMAP{ANSI_RESET}\n")

        items = heatmap_data.get("items", [])
        all_authors = heatmap_data.get("all_authors", [])

        if not items:
            lines.append(f"{ANSI_BRIGHT_BLACK}No ownership data available.{ANSI_RESET}")
            return "\n".join(lines)

        author_color_map = {
            author: AUTHOR_COLORS[i % len(AUTHOR_COLORS)]
            for i, author in enumerate(all_authors)
        }

        items = items[:max_items]

        max_path_len = max(len(item["path"]) for item in items) if items else 0
        path_width = min(max_path_len, 35)

        lines.append(
            f"{ANSI_BOLD}{'Path':<{path_width}} {'Heatmap':<12} {'Lines':>8} {'Conc':>6} {'Primary Author'}{ANSI_RESET}"
        )
        lines.append("-" * self.width)

        for item in items:
            path = item["path"]
            if len(path) > path_width:
                path = "..." + path[-(path_width - 3):]

            lines_count = item.get("total_lines", 0)
            concentration = item.get("ownership_concentration", 0)
            primary_author = item.get("primary_author", "N/A")
            item_type = item.get("type", "file")

            type_prefix = "📁 " if item_type == "directory" else "📄 "
            display_path = type_prefix + path

            author_color = author_color_map.get(primary_author, ANSI_RESET)

            intensity = int(concentration * 8)
            blocks = "█" * intensity + "░" * (8 - intensity)

            if concentration >= 0.7:
                heatmap_block = f"{ANSI_BG_RED}{ANSI_WHITE} {blocks} {ANSI_RESET}"
            elif concentration >= 0.4:
                heatmap_block = f"{ANSI_BG_YELLOW}{ANSI_BLACK} {blocks} {ANSI_RESET}"
            else:
                heatmap_block = f"{ANSI_BG_GREEN}{ANSI_BLACK} {blocks} {ANSI_RESET}"

            conc_color = self._color_by_value(concentration, 0, 1, reverse=True)
            conc_str = f"{conc_color}{concentration * 100:.0f}%{ANSI_RESET}"

            lines.append(
                f"{display_path:<{path_width + 2}} {heatmap_block} {lines_count:>8} {conc_str:>6} "
                f"{author_color}{primary_author}{ANSI_RESET}"
            )

        if show_authors and all_authors:
            lines.append("\n" + "-" * self.width)
            lines.append(f"{ANSI_BOLD}AUTHOR LEGEND:{ANSI_RESET}")
            legend_parts = []
            for i, author in enumerate(all_authors[:10]):
                color = author_color_map.get(author, ANSI_RESET)
                legend_parts.append(f"{color}■{ANSI_RESET} {author}")
            lines.append("  " + "  ".join(legend_parts))

        lines.append("\n" + "-" * self.width)
        lines.append(f"{ANSI_BOLD}CONCENTRATION LEGEND:{ANSI_RESET}")
        lines.append(
            f"  {ANSI_BG_GREEN}    {ANSI_RESET} Low (0-25%)  "
            f"{ANSI_BG_YELLOW}    {ANSI_RESET} Moderate (25-50%)  "
            f"{ANSI_BG_RED}    {ANSI_RESET} High (>50%)"
        )

        return "\n".join(lines)

    def render_activity_barchart(
        self,
        activity_data: Dict,
        months_to_show: int = 12
    ) -> str:
        """Render a developer activity bar chart.

        Args:
            activity_data: Data from OwnershipAnalyzer.get_commit_activity_summary()
            months_to_show: Number of months to display.

        Returns:
            String with ANSI escape codes for terminal rendering.
        """
        lines = []

        lines.append(f"\n{ANSI_BOLD}{ANSI_UNDERLINE}DEVELOPER ACTIVITY (Last {months_to_show} Months){ANSI_RESET}\n")

        months = activity_data.get("months", [])
        authors = activity_data.get("authors", [])
        activity = activity_data.get("activity", {})

        if not months:
            lines.append(f"{ANSI_BRIGHT_BLACK}No commit activity data available.{ANSI_RESET}")
            return "\n".join(lines)

        months = months[-months_to_show:] if len(months) > months_to_show else months

        max_commits = 0
        for month in months:
            month_data = activity.get(month, {})
            total = sum(month_data.values())
            max_commits = max(max_commits, total)

        if max_commits == 0:
            max_commits = 1

        author_color_map = {
            author: AUTHOR_COLORS[i % len(AUTHOR_COLORS)]
            for i, author in enumerate(authors)
        }

        bar_width = self.width - 20

        lines.append(f"{ANSI_BOLD}Total commits in period: {activity_data.get('total_commits', 0)}{ANSI_RESET}\n")

        max_label_len = max(len(month) for month in months) if months else 7

        for month in months:
            month_data = activity.get(month, {})
            total = sum(month_data.values())

            bar_length = int(total / max_commits * bar_width) if max_commits > 0 else 0

            segments = []
            current_pos = 0
            sorted_authors = sorted(
                month_data.items(),
                key=lambda x: x[1],
                reverse=True
            )

            for author, count in sorted_authors:
                if count == 0:
                    continue
                color = author_color_map.get(author, ANSI_RESET)
                segment_length = max(1, int(count / total * bar_length)) if total > 0 else 0
                if current_pos + segment_length <= bar_length:
                    segments.append((color, segment_length))
                    current_pos += segment_length

            if bar_length > 0 and current_pos < bar_length:
                segments = [(c, l + 1) for c, l in segments[:1]] + segments[1:]

            bar_str = ""
            for color, length in segments:
                bar_str += f"{color}{'█' * length}{ANSI_RESET}"

            lines.append(
                f"{month:<{max_label_len}} | {bar_str} {ANSI_CYAN}{total}{ANSI_RESET}"
            )

        if authors:
            lines.append("\n" + "-" * self.width)
            lines.append(f"{ANSI_BOLD}DEVELOPER LEGEND:{ANSI_RESET}")
            legend_parts = []
            for i, author in enumerate(authors[:8]):
                color = author_color_map.get(author, ANSI_RESET)
                legend_parts.append(f"{color}█{ANSI_RESET} {author}")
            lines.append("  " + "  ".join(legend_parts))

        return "\n".join(lines)

    def render_radar_chart(
        self,
        metrics: Dict[str, float],
        scores: Dict[str, float],
        overall_score: float
    ) -> str:
        """Render a technical debt radar chart.

        Args:
            metrics: Dictionary of metric names to values.
            scores: Dictionary of metric names to normalized scores (0-100).
            overall_score: Overall health score (0-100).

        Returns:
            String with ANSI escape codes for terminal rendering.
        """
        lines = []

        lines.append(f"\n{ANSI_BOLD}{ANSI_UNDERLINE}TECHNICAL DEBT RADAR{ANSI_RESET}\n")

        metric_names = list(scores.keys())
        num_metrics = len(metric_names)

        if num_metrics == 0:
            lines.append(f"{ANSI_BRIGHT_BLACK}No metrics available for radar chart.{ANSI_RESET}")
            return "\n".join(lines)

        chart_width = 48
        chart_height = 24

        center_x = chart_width // 2
        center_y = chart_height // 2

        canvas = [[" " for _ in range(chart_width)] for _ in range(chart_height)]

        for radius in [4, 8, 12]:
            for angle in range(0, 360, 3):
                rad = math.radians(angle)
                x = int(center_x + radius * 2 * math.cos(rad))
                y = int(center_y - radius * math.sin(rad))
                if 0 <= x < chart_width and 0 <= y < chart_height:
                    if canvas[y][x] == " ":
                        canvas[y][x] = "·"

        axis_labels = []
        for i, metric in enumerate(metric_names):
            score = scores.get(metric, 0)
            angle = 2 * math.pi * i / num_metrics - math.pi / 2

            for radius in range(0, 14):
                x = int(center_x + radius * 2 * math.cos(angle))
                y = int(center_y - radius * math.sin(angle))
                if 0 <= x < chart_width and 0 <= y < chart_height:
                    if radius == 13:
                        canvas[y][x] = "○"
                    elif canvas[y][x] == " ":
                        canvas[y][x] = "·"

            color = self._color_by_value(score, 0, 100)
            label_radius = 16
            label_x = int(center_x + label_radius * 2 * math.cos(angle))
            label_y = int(center_y - label_radius * math.sin(angle))
            
            axis_labels.append({
                "name": metric,
                "score": score,
                "color": color,
                "label_x": label_x,
                "label_y": label_y,
                "angle": angle,
            })

        points = []
        for i, metric in enumerate(metric_names):
            score = scores.get(metric, 0)
            angle = 2 * math.pi * i / num_metrics - math.pi / 2
            radius = score / 100 * 12
            x = int(center_x + radius * 2 * math.cos(angle))
            y = int(center_y - radius * math.sin(angle))
            points.append((x, y, score, metric))
            if 0 <= x < chart_width and 0 <= y < chart_height:
                canvas[y][x] = "●"

        for i in range(len(points)):
            x1, y1, _, _ = points[i]
            x2, y2, _, _ = points[(i + 1) % len(points)]

            steps = max(abs(x2 - x1), abs(y2 - y1))
            if steps == 0:
                continue

            for step in range(1, steps):
                t = step / steps
                x = int(x1 + t * (x2 - x1))
                y = int(y1 + t * (y2 - y1))
                if 0 <= x < chart_width and 0 <= y < chart_height:
                    if canvas[y][x] in (" ", "·"):
                        canvas[y][x] = "○"

        colored_lines = []
        for row_idx, row in enumerate(canvas):
            colored_row = []
            for char in row:
                if char == "●":
                    colored_row.append(f"{ANSI_GREEN}●{ANSI_RESET}")
                elif char == "○":
                    colored_row.append(f"{ANSI_CYAN}○{ANSI_RESET}")
                elif char == "·":
                    colored_row.append(f"{ANSI_BRIGHT_BLACK}·{ANSI_RESET}")
                else:
                    colored_row.append(char)
            colored_lines.append("".join(colored_row))

        for label in axis_labels:
            angle = label["angle"]
            row_idx = int(center_y - 14 * math.sin(angle))
            
            if 0 <= row_idx < len(colored_lines):
                metric_name = label["name"]
                score = label["score"]
                color = label["color"]
                
                deg = math.degrees(angle)
                if -90 <= deg < -45 or 315 <= deg <= 360:
                    label_text = f" {color}{metric_name}: {score:.0f}{ANSI_RESET}"
                    colored_lines[row_idx] = colored_lines[row_idx].rstrip() + label_text
                elif -45 <= deg < 45:
                    label_text = f"{color}{metric_name}: {score:.0f}{ANSI_RESET} "
                    colored_lines[row_idx] = label_text + colored_lines[row_idx]
                elif 45 <= deg < 135:
                    label_text = f"{color}{metric_name}: {score:.0f}{ANSI_RESET} "
                    colored_lines[row_idx] = label_text + colored_lines[row_idx]
                else:
                    label_text = f" {color}{metric_name}: {score:.0f}{ANSI_RESET}"
                    colored_lines[row_idx] = colored_lines[row_idx].rstrip() + label_text

        lines.extend(colored_lines)

        lines.append("\n" + "-" * self.width)
        lines.append(f"{ANSI_BOLD}METRIC DETAILS:{ANSI_RESET}")

        for metric in metric_names:
            score = scores.get(metric, 0)
            value = metrics.get(metric, "N/A")
            color = self._color_by_value(score, 0, 100)
            lines.append(
                f"  {color}{metric:30}{ANSI_RESET} Score: {color}{score:5.1f}{ANSI_RESET}/100  Value: {value}"
            )

        lines.append("\n" + "=" * self.width)
        
        score_color = self._color_by_value(overall_score, 0, 100)
        lines.append(
            f"{ANSI_BOLD}OVERALL PROJECT HEALTH SCORE: {score_color}{overall_score:.1f}{ANSI_RESET}/100"
        )

        if overall_score >= 80:
            lines.append(f"{ANSI_GREEN}Status: Excellent - Project is in great health!{ANSI_RESET}")
        elif overall_score >= 60:
            lines.append(f"{ANSI_YELLOW}Status: Good - Minor improvements recommended.{ANSI_RESET}")
        elif overall_score >= 40:
            lines.append(f"{ANSI_YELLOW}Status: Moderate - Attention needed in some areas.{ANSI_RESET}")
        else:
            lines.append(f"{ANSI_RED}Status: Poor - Significant technical debt detected.{ANSI_RESET}")

        return "\n".join(lines)

    def render_simple_bar(
        self,
        value: float,
        max_value: float,
        width: int = 40,
        show_percent: bool = True
    ) -> str:
        """Render a simple progress bar.

        Args:
            value: Current value.
            max_value: Maximum value.
            width: Width of the bar.
            show_percent: Whether to show percentage.

        Returns:
            String with ANSI colored progress bar.
        """
        if max_value == 0:
            percent = 0
        else:
            percent = min(100, value / max_value * 100)

        filled = int(percent / 100 * width)
        empty = width - filled

        color = self._color_by_value(percent, 0, 100)
        bar = f"{color}{'█' * filled}{ANSI_RESET}{'░' * empty}"

        if show_percent:
            return f"[{bar}] {color}{percent:.1f}%{ANSI_RESET}"
        return f"[{bar}]"

    def render_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        title: Optional[str] = None
    ) -> str:
        """Render a formatted table.

        Args:
            headers: List of column headers.
            rows: List of rows, each row is a list of cell values.
            title: Optional table title.

        Returns:
            Formatted table string.
        """
        lines = []

        if title:
            lines.append(f"\n{ANSI_BOLD}{title}{ANSI_RESET}")

        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        header_line = "|" + "|".join(f" {h:<{w}} " for h, w in zip(headers, col_widths)) + "|"

        lines.append(separator)
        lines.append(f"{ANSI_BOLD}{header_line}{ANSI_RESET}")
        lines.append(separator)

        for row in rows:
            row_line = "|"
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    row_line += f" {str(cell):<{col_widths[i]}} "
                row_line += "|"
            lines.append(row_line)

        lines.append(separator)

        return "\n".join(lines)
