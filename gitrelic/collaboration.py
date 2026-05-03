"""Collaboration Network Analysis Module

This module analyzes collaboration patterns between developers by examining
who modifies the same files, generates ASCII network diagrams, and calculates
bus factor risk for files with single authors.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any

from .git_data import GitDataExtractor, GitCommit, FileModificationHistory


@dataclass
class AuthorCollaboration:
    """Data class representing collaboration between two authors."""
    
    author1: str
    author2: str
    shared_files: int
    shared_commits: int
    collaboration_score: float
    shared_file_list: List[str] = field(default_factory=list)
    
    def get_pair_key(self) -> Tuple[str, str]:
        """Get a normalized key for this collaboration pair.
        
        Returns:
            Tuple of (author1, author2) sorted alphabetically.
        """
        if self.author1 < self.author2:
            return (self.author1, self.author2)
        return (self.author2, self.author1)


@dataclass
class BusFactorRisk:
    """Data class representing bus factor risk for a file."""
    
    file_path: str
    total_authors: int
    primary_author: str
    primary_author_percentage: float
    risk_level: str
    risk_score: float
    total_lines: int
    last_modified: Optional[datetime] = None
    total_commits: int = 0
    
    def is_high_risk(self) -> bool:
        """Check if this file is high risk.
        
        Returns:
            True if high risk (single author), False otherwise.
        """
        return self.total_authors <= 1


@dataclass
class CollaborationNetwork:
    """Data class representing the complete collaboration network."""
    
    authors: List[str] = field(default_factory=list)
    collaborations: List[AuthorCollaboration] = field(default_factory=list)
    bus_factor_risks: List[BusFactorRisk] = field(default_factory=list)
    
    total_files: int = 0
    high_risk_files: int = 0
    medium_risk_files: int = 0
    low_risk_files: int = 0
    
    network_density: float = 0.0
    most_connected_author: Optional[str] = None
    most_isolated_files: List[str] = field(default_factory=list)


class CollaborationAnalyzer:
    """Analyzer for developer collaboration patterns.
    
    This class analyzes:
    1. Which authors frequently modify the same files
    2. The strength of collaboration between authors
    3. Bus factor risk - files with only one contributor
    """
    
    def __init__(self, extractor: GitDataExtractor):
        """Initialize the CollaborationAnalyzer.
        
        Args:
            extractor: GitDataExtractor instance for accessing repository data.
        """
        self.extractor = extractor
    
    def analyze_collaborations(
        self,
        months: Optional[int] = None,
        min_shared_files: int = 1,
    ) -> List[AuthorCollaboration]:
        """Analyze collaborations between authors based on shared file modifications.
        
        Args:
            months: Optional number of months to look back.
                If None, analyzes all commits.
            min_shared_files: Minimum number of shared files to be considered.
        
        Returns:
            List of AuthorCollaboration objects sorted by strength.
        """
        commits = self.extractor.get_commits()
        
        if months is not None:
            cutoff_date = datetime.now() - timedelta(days=months * 30)
            commits = [c for c in commits if c.date >= cutoff_date]
        
        file_authors: Dict[str, Set[str]] = {}
        author_files: Dict[str, Set[str]] = {}
        
        for commit in commits:
            author = commit.author
            
            if author not in author_files:
                author_files[author] = set()
            
            for file_path in commit.files_changed:
                if file_path not in file_authors:
                    file_authors[file_path] = set()
                
                file_authors[file_path].add(author)
                author_files[author].add(file_path)
        
        all_authors = list(author_files.keys())
        collaborations: Dict[Tuple[str, str], AuthorCollaboration] = {}
        
        for i, author1 in enumerate(all_authors):
            for author2 in all_authors[i + 1:]:
                files1 = author_files.get(author1, set())
                files2 = author_files.get(author2, set())
                
                shared = files1.intersection(files2)
                
                if len(shared) >= min_shared_files:
                    union = files1.union(files2)
                    jaccard = len(shared) / len(union) if union else 0.0
                    
                    shared_commits = self._count_shared_commits(
                        commits, author1, author2, shared
                    )
                    
                    score = (len(shared) * 0.6) + (shared_commits * 0.4)
                    
                    collab = AuthorCollaboration(
                        author1=author1,
                        author2=author2,
                        shared_files=len(shared),
                        shared_commits=shared_commits,
                        collaboration_score=score,
                        shared_file_list=list(shared),
                    )
                    
                    collaborations[collab.get_pair_key()] = collab
        
        result = list(collaborations.values())
        result.sort(key=lambda x: x.collaboration_score, reverse=True)
        
        return result
    
    def _count_shared_commits(
        self,
        commits: List[GitCommit],
        author1: str,
        author2: str,
        shared_files: Set[str],
    ) -> int:
        """Count commits where both authors touched the same file.
        
        Args:
            commits: List of commits to analyze.
            author1: First author.
            author2: Second author.
            shared_files: Set of files both authors have modified.
        
        Returns:
            Count of file instances where both contributed.
        """
        count = 0
        
        for file_path in shared_files:
            file_commits = [
                c for c in commits 
                if file_path in c.files_changed
            ]
            
            authors_in_file = set(c.author for c in file_commits)
            
            if author1 in authors_in_file and author2 in authors_in_file:
                count += 1
        
        return count
    
    def analyze_bus_factor(
        self,
        risk_threshold_high: float = 90.0,
        risk_threshold_medium: float = 60.0,
    ) -> List[BusFactorRisk]:
        """Analyze bus factor risk for all files.
        
        Bus factor risk measures how critical a single developer is to
        understanding and maintaining a file.
        
        Args:
            risk_threshold_high: Percentage above which a file is high risk.
            risk_threshold_medium: Percentage above which a file is medium risk.
        
        Returns:
            List of BusFactorRisk objects sorted by risk (highest first).
        """
        all_files = self.extractor.get_all_files()
        
        risks: List[BusFactorRisk] = []
        
        for file_path in all_files:
            history = self.extractor.get_file_modification_history(file_path)
            
            if not history.author_stats:
                continue
            
            total_lines = sum(history.author_stats.values())
            num_authors = len(history.authors)
            
            if num_authors == 0:
                continue
            
            primary_author = max(
                history.author_stats.items(),
                key=lambda x: x[1]
            )[0]
            
            primary_lines = history.author_stats[primary_author]
            primary_percentage = (primary_lines / total_lines * 100) if total_lines > 0 else 0.0
            
            if primary_percentage >= risk_threshold_high or num_authors <= 1:
                risk_level = "high"
                risk_score = 1.0
            elif primary_percentage >= risk_threshold_medium:
                risk_level = "medium"
                risk_score = 0.5
            else:
                risk_level = "low"
                risk_score = 0.2
            
            risk = BusFactorRisk(
                file_path=file_path,
                total_authors=num_authors,
                primary_author=primary_author,
                primary_author_percentage=primary_percentage,
                risk_level=risk_level,
                risk_score=risk_score,
                total_lines=total_lines,
                last_modified=history.last_modified,
                total_commits=history.total_commits,
            )
            
            risks.append(risk)
        
        risks.sort(key=lambda x: (x.risk_score, x.primary_author_percentage), reverse=True)
        
        return risks
    
    def generate_full_network(
        self,
        months: Optional[int] = None,
        min_shared_files: int = 1,
    ) -> CollaborationNetwork:
        """Generate the complete collaboration network analysis.
        
        Args:
            months: Optional number of months to look back.
            min_shared_files: Minimum shared files for collaboration.
        
        Returns:
            CollaborationNetwork object with all analysis data.
        """
        collaborations = self.analyze_collaborations(
            months=months,
            min_shared_files=min_shared_files,
        )
        
        bus_risks = self.analyze_bus_factor()
        
        commits = self.extractor.get_commits()
        if months is not None:
            cutoff_date = datetime.now() - timedelta(days=months * 30)
            commits = [c for c in commits if c.date >= cutoff_date]
        
        all_authors = set(c.author for c in commits)
        
        author_connections: Dict[str, int] = {}
        for collab in collaborations:
            author_connections[collab.author1] = author_connections.get(collab.author1, 0) + 1
            author_connections[collab.author2] = author_connections.get(collab.author2, 0) + 1
        
        most_connected = None
        if author_connections:
            most_connected = max(
                author_connections.items(),
                key=lambda x: x[1]
            )[0]
        
        num_authors = len(all_authors)
        max_possible_collabs = num_authors * (num_authors - 1) // 2 if num_authors > 1 else 0
        actual_collabs = len(collaborations)
        density = actual_collabs / max_possible_collabs if max_possible_collabs > 0 else 0.0
        
        high_risk = sum(1 for r in bus_risks if r.risk_level == "high")
        medium_risk = sum(1 for r in bus_risks if r.risk_level == "medium")
        low_risk = sum(1 for r in bus_risks if r.risk_level == "low")
        
        high_risk_files = [r for r in bus_risks if r.risk_level == "high"]
        high_risk_files.sort(key=lambda x: x.total_lines, reverse=True)
        most_isolated = [r.file_path for r in high_risk_files[:10]]
        
        return CollaborationNetwork(
            authors=list(all_authors),
            collaborations=collaborations,
            bus_factor_risks=bus_risks,
            total_files=len(bus_risks),
            high_risk_files=high_risk,
            medium_risk_files=medium_risk,
            low_risk_files=low_risk,
            network_density=density,
            most_connected_author=most_connected,
            most_isolated_files=most_isolated,
        )


class ASCIINetworkRenderer:
    """Renderer for ASCII-based collaboration network diagrams.
    
    This class creates visual representations of the collaboration
    network using ASCII characters and ANSI colors.
    """
    
    def __init__(self, width: int = 80, height: int = 24):
        """Initialize the ASCIINetworkRenderer.
        
        Args:
            width: Width of the drawing area in characters.
            height: Height of the drawing area in characters.
        """
        self.width = width
        self.height = height
        
        from .renderer import (
            ANSI_RESET, ANSI_BOLD, ANSI_GREEN, ANSI_BLUE, 
            ANSI_YELLOW, ANSI_RED, ANSI_CYAN, ANSI_MAGENTA,
            ANSI_BRIGHT_BLACK,
        )
        
        self.ANSI_RESET = ANSI_RESET
        self.ANSI_BOLD = ANSI_BOLD
        self.ANSI_GREEN = ANSI_GREEN
        self.ANSI_BLUE = ANSI_BLUE
        self.ANSI_YELLOW = ANSI_YELLOW
        self.ANSI_RED = ANSI_RED
        self.ANSI_CYAN = ANSI_CYAN
        self.ANSI_MAGENTA = ANSI_MAGENTA
        self.ANSI_BRIGHT_BLACK = ANSI_BRIGHT_BLACK
        
        self.author_colors = [
            ANSI_GREEN, ANSI_BLUE, ANSI_YELLOW, ANSI_MAGENTA, ANSI_CYAN,
            ANSI_BRIGHT_BLACK,
        ]
    
    def render_network(
        self,
        network: CollaborationNetwork,
        show_all_authors: bool = True,
    ) -> str:
        """Render the collaboration network as an ASCII diagram.
        
        Args:
            network: CollaborationNetwork to render.
            show_all_authors: Whether to include all authors or just connected ones.
        
        Returns:
            String containing the ASCII diagram with ANSI colors.
        """
        lines = []
        
        lines.append(f"\n{self.ANSI_BOLD}┌{'─' * (self.width - 2)}┐{self.ANSI_RESET}")
        lines.append(f"{self.ANSI_BOLD}│{self.ANSI_RESET}  "
                     f"{self.ANSI_CYAN}{self.ANSI_BOLD}DEVELOPER COLLABORATION NETWORK{self.ANSI_RESET}"
                     f"{' ' * (self.width - 34)}{self.ANSI_BOLD}│{self.ANSI_RESET}")
        lines.append(f"{self.ANSI_BOLD}└{'─' * (self.width - 2)}┘{self.ANSI_RESET}")
        lines.append("")
        
        if not network.authors:
            lines.append(f"{self.ANSI_BRIGHT_BLACK}  No collaboration data available.{self.ANSI_RESET}")
            return "\n".join(lines)
        
        authors = network.authors
        
        author_color_map = {
            author: self.author_colors[i % len(self.author_colors)]
            for i, author in enumerate(authors)
        }
        
        if len(authors) <= 8:
            diagram = self._render_circular_layout(authors, network.collaborations, author_color_map)
        else:
            diagram = self._render_compact_layout(authors, network.collaborations, author_color_map)
        
        lines.extend(diagram)
        lines.append("")
        
        lines.append(f"{self.ANSI_BOLD}  Network Statistics:{self.ANSI_RESET}")
        lines.append(f"    Total authors: {len(authors)}")
        lines.append(f"    Collaboration pairs: {len(network.collaborations)}")
        lines.append(f"    Network density: {network.network_density:.1%}")
        
        if network.most_connected_author:
            color = author_color_map.get(network.most_connected_author, self.ANSI_CYAN)
            lines.append(f"    Most connected: {color}{network.most_connected_author}{self.ANSI_RESET}")
        
        lines.append("")
        
        if network.collaborations:
            lines.append(f"{self.ANSI_BOLD}  Strongest Collaborations:{self.ANSI_RESET}")
            
            max_score = max(c.collaboration_score for c in network.collaborations) if network.collaborations else 1
            
            for collab in network.collaborations[:8]:
                color1 = author_color_map.get(collab.author1, self.ANSI_CYAN)
                color2 = author_color_map.get(collab.author2, self.ANSI_GREEN)
                
                strength = int(collab.collaboration_score / max_score * 10) if max_score > 0 else 0
                bar = "█" * strength + "░" * (10 - strength)
                
                lines.append("")
                lines.append(
                    f"    {color1}{collab.author1:<15}{self.ANSI_RESET} "
                    f"{self.ANSI_BRIGHT_BLACK}⟷{self.ANSI_RESET} "
                    f"{color2}{collab.author2:<15}{self.ANSI_RESET} "
                    f"[{bar}] {collab.shared_files} files, {collab.shared_commits} commits"
                )
                
                if collab.shared_file_list:
                    lines.append(f"    {self.ANSI_BRIGHT_BLACK}    Shared files:{self.ANSI_RESET}")
                    for i, file_path in enumerate(collab.shared_file_list[:5]):
                        display_path = file_path
                        if len(display_path) > 50:
                            display_path = "..." + display_path[-47:]
                        lines.append(f"      {self.ANSI_CYAN}•{self.ANSI_RESET} {display_path}")
                    if len(collab.shared_file_list) > 5:
                        lines.append(f"      {self.ANSI_BRIGHT_BLACK}... and {len(collab.shared_file_list) - 5} more files{self.ANSI_RESET}")
        
        return "\n".join(lines)
    
    def _render_circular_layout(
        self,
        authors: List[str],
        collaborations: List[AuthorCollaboration],
        author_color_map: Dict[str, str],
    ) -> List[str]:
        """Render authors in a circular layout with connection lines.
        
        Args:
            authors: List of author names.
            collaborations: List of collaboration pairs.
            author_color_map: Mapping of authors to colors.
        
        Returns:
            List of strings representing the diagram lines.
        """
        lines = []
        
        diagram_width = min(self.width - 4, 60)
        diagram_height = min(self.height - 10, 16)
        
        center_x = diagram_width // 2
        center_y = diagram_height // 2
        radius = min(center_x, center_y) - 2
        
        collab_map: Dict[Tuple[str, str], AuthorCollaboration] = {}
        for collab in collaborations:
            collab_map[collab.get_pair_key()] = collab
        
        canvas = [[" " for _ in range(diagram_width)] for _ in range(diagram_height)]
        
        num_authors = len(authors)
        author_positions: Dict[str, Tuple[int, int]] = {}
        
        for i, author in enumerate(authors):
            angle = 2 * math.pi * i / num_authors - math.pi / 2
            x = int(center_x + radius * math.cos(angle))
            y = int(center_y + radius * math.sin(angle))
            
            if 0 <= x < diagram_width and 0 <= y < diagram_height:
                author_positions[author] = (x, y)
        
        for i, author1 in enumerate(authors):
            for author2 in authors[i + 1:]:
                pair_key = (author1, author2) if author1 < author2 else (author2, author1)
                
                if pair_key in collab_map:
                    pos1 = author_positions.get(author1)
                    pos2 = author_positions.get(author2)
                    
                    if pos1 and pos2:
                        self._draw_line(canvas, pos1[0], pos1[1], pos2[0], pos2[1])
        
        for author, (x, y) in author_positions.items():
            if 0 <= x < diagram_width and 0 <= y < diagram_height:
                canvas[y][x] = "●"
        
        for row in canvas:
            lines.append("  " + "".join(row))
        
        lines.append("")
        
        legend_parts = []
        for author in authors:
            color = author_color_map.get(author, self.ANSI_CYAN)
            legend_parts.append(f"{color}●{self.ANSI_RESET} {author}")
        
        lines.append("  " + "  ".join(legend_parts))
        
        return lines
    
    def _draw_line(
        self,
        canvas: List[List[str]],
        x1: int, y1: int,
        x2: int, y2: int,
    ) -> None:
        """Draw a line on the canvas using Bresenham's algorithm.
        
        Args:
            canvas: The canvas to draw on.
            x1, y1: Start coordinates.
            x2, y2: End coordinates.
        """
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        
        x, y = x1, y1
        
        while True:
            if 0 <= y < len(canvas) and 0 <= x < len(canvas[0]):
                if canvas[y][x] == " ":
                    canvas[y][x] = "·"
            
            if x == x2 and y == y2:
                break
            
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
    
    def _render_compact_layout(
        self,
        authors: List[str],
        collaborations: List[AuthorCollaboration],
        author_color_map: Dict[str, str],
    ) -> List[str]:
        """Render a compact layout for larger numbers of authors.
        
        Args:
            authors: List of author names.
            collaborations: List of collaboration pairs.
            author_color_map: Mapping of authors to colors.
        
        Returns:
            List of strings representing the diagram.
        """
        lines = []
        
        lines.append(f"  {self.ANSI_BOLD}Author Collaboration Matrix{self.ANSI_RESET}")
        lines.append("")
        
        collab_matrix: Dict[str, Dict[str, AuthorCollaboration]] = {}
        for collab in collaborations:
            if collab.author1 not in collab_matrix:
                collab_matrix[collab.author1] = {}
            if collab.author2 not in collab_matrix:
                collab_matrix[collab.author2] = {}
            collab_matrix[collab.author1][collab.author2] = collab
            collab_matrix[collab.author2][collab.author1] = collab
        
        max_authors_to_show = min(len(authors), 15)
        displayed_authors = authors[:max_authors_to_show]
        
        lines.append(
            "  " + " " * 12 + 
            " ".join(f"{i+1:2}" for i in range(len(displayed_authors)))
        )
        lines.append("  " + " " * 12 + "─" * (len(displayed_authors) * 3))
        
        for i, author1 in enumerate(displayed_authors):
            color = author_color_map.get(author1, self.ANSI_CYAN)
            
            row = f"  {color}{i+1:2}. {author1[:8]:<8}{self.ANSI_RESET} │"
            
            for j, author2 in enumerate(displayed_authors):
                if i == j:
                    row += " ●"
                else:
                    collab = collab_matrix.get(author1, {}).get(author2)
                    if collab:
                        if collab.shared_files >= 5:
                            row += f" {self.ANSI_GREEN}█{self.ANSI_RESET}"
                        elif collab.shared_files >= 2:
                            row += f" {self.ANSI_YELLOW}▓{self.ANSI_RESET}"
                        else:
                            row += f" {self.ANSI_BRIGHT_BLACK}·{self.ANSI_RESET}"
                    else:
                        row += "  "
            
            lines.append(row)
        
        lines.append("")
        lines.append(f"  {self.ANSI_BRIGHT_BLACK}Legend:{self.ANSI_RESET}")
        lines.append(f"    {self.ANSI_GREEN}█{self.ANSI_RESET} Strong collaboration (5+ files)")
        lines.append(f"    {self.ANSI_YELLOW}▓{self.ANSI_RESET} Moderate collaboration (2-4 files)")
        lines.append(f"    {self.ANSI_BRIGHT_BLACK}·{self.ANSI_RESET} Weak collaboration (1 file)")
        
        if len(authors) > max_authors_to_show:
            lines.append("")
            lines.append(f"  ... and {len(authors) - max_authors_to_show} more authors")
        
        return lines
    
    def render_bus_factor_report(
        self,
        network: CollaborationNetwork,
        max_items: int = 20,
    ) -> str:
        """Render the bus factor risk report.
        
        Args:
            network: CollaborationNetwork with bus factor data.
            max_items: Maximum number of files to show per risk category.
        
        Returns:
            String containing the formatted report.
        """
        lines = []
        
        lines.append(f"\n{self.ANSI_BOLD}┌{'─' * (self.width - 2)}┐{self.ANSI_RESET}")
        lines.append(f"{self.ANSI_BOLD}│{self.ANSI_RESET}  "
                     f"{self.ANSI_RED}{self.ANSI_BOLD}BUS FACTOR RISK ANALYSIS{self.ANSI_RESET}"
                     f"{' ' * (self.width - 31)}{self.ANSI_BOLD}│{self.ANSI_RESET}")
        lines.append(f"{self.ANSI_BOLD}└{'─' * (self.width - 2)}┘{self.ANSI_RESET}")
        lines.append("")
        
        total = network.total_files
        high = network.high_risk_files
        medium = network.medium_risk_files
        low = network.low_risk_files
        
        high_pct = high / total * 100 if total > 0 else 0
        medium_pct = medium / total * 100 if total > 0 else 0
        low_pct = low / total * 100 if total > 0 else 0
        
        lines.append(f"{self.ANSI_BOLD}  Risk Summary:{self.ANSI_RESET}")
        lines.append(f"    Total files analyzed: {total}")
        lines.append("")
        
        bar_width = 40
        high_bar = int(high_pct / 100 * bar_width)
        medium_bar = int(medium_pct / 100 * bar_width)
        low_bar = int(low_pct / 100 * bar_width)
        
        total_bar = high_bar + medium_bar + low_bar
        if total_bar < bar_width:
            high_bar += (bar_width - total_bar)
        
        risk_bar = (
            f"{self.ANSI_RED}{'█' * high_bar}{self.ANSI_RESET}"
            f"{self.ANSI_YELLOW}{'█' * medium_bar}{self.ANSI_RESET}"
            f"{self.ANSI_GREEN}{'█' * low_bar}{self.ANSI_RESET}"
        )
        
        lines.append(f"    [{risk_bar}]")
        lines.append(
            f"    {self.ANSI_RED}High Risk:   {high:5} files ({high_pct:.1f}%){self.ANSI_RESET}  "
            f"{self.ANSI_YELLOW}Medium: {medium:5} ({medium_pct:.1f}%){self.ANSI_RESET}  "
            f"{self.ANSI_GREEN}Low: {low:5} ({low_pct:.1f}%){self.ANSI_RESET}"
        )
        lines.append("")
        
        high_risk_files = [
            r for r in network.bus_factor_risks 
            if r.risk_level == "high"
        ]
        
        if high_risk_files:
            lines.append(f"{self.ANSI_BOLD}  {self.ANSI_RED}🔴 HIGH RISK FILES{self.ANSI_RESET}")
            lines.append(f"  {'─' * (self.width - 4)}")
            lines.append(
                f"  {self.ANSI_BOLD}"
                f"{'File':<40} {'Owner':<20} {'Lines':>8} {'Ownership':>12}"
                f"{self.ANSI_RESET}"
            )
            lines.append(f"  {'─' * (self.width - 4)}")
            
            for risk in high_risk_files[:max_items]:
                path_display = risk.file_path
                if len(path_display) > 38:
                    path_display = "..." + path_display[-35:]
                
                owner_color = self._get_author_color(risk.primary_author)
                
                lines.append(
                    f"  {path_display:<40} "
                    f"{owner_color}{risk.primary_author[:18]:<20}{self.ANSI_RESET} "
                    f"{risk.total_lines:>8,} "
                    f"{self.ANSI_RED}{risk.primary_author_percentage:>10.0f}%{self.ANSI_RESET}"
                )
            
            if len(high_risk_files) > max_items:
                lines.append(f"  {self.ANSI_BRIGHT_BLACK}... and {len(high_risk_files) - max_items} more high-risk files{self.ANSI_RESET}")
        
        medium_risk_files = [
            r for r in network.bus_factor_risks 
            if r.risk_level == "medium"
        ]
        
        if medium_risk_files and len(high_risk_files) < 5:
            lines.append("")
            lines.append(f"{self.ANSI_BOLD}  {self.ANSI_YELLOW}🟡 MEDIUM RISK FILES{self.ANSI_RESET}")
            lines.append(f"  {'─' * (self.width - 4)}")
            
            for risk in medium_risk_files[:10]:
                path_display = risk.file_path
                if len(path_display) > 38:
                    path_display = "..." + path_display[-35:]
                
                owner_color = self._get_author_color(risk.primary_author)
                
                lines.append(
                    f"  {path_display:<40} "
                    f"{owner_color}{risk.primary_author[:18]:<20}{self.ANSI_RESET} "
                    f"{risk.total_lines:>8,} "
                    f"{self.ANSI_YELLOW}{risk.primary_author_percentage:>10.0f}%{self.ANSI_RESET}"
                )
        
        lines.append("")
        lines.append(f"{self.ANSI_BOLD}  Risk Level Definitions:{self.ANSI_RESET}")
        lines.append(f"    {self.ANSI_RED}High Risk:{self.ANSI_RESET}   Single author OR >90% owned by one person")
        lines.append(f"    {self.ANSI_YELLOW}Medium Risk:{self.ANSI_RESET} 60-90% owned by primary author")
        lines.append(f"    {self.ANSI_GREEN}Low Risk:{self.ANSI_RESET}    <60% owned by primary author, multiple contributors")
        
        lines.append("")
        lines.append(f"  {self.ANSI_BRIGHT_BLACK}💡 Tip: Files with high bus factor risk should have knowledge sharing sessions{self.ANSI_RESET}")
        
        return "\n".join(lines)
    
    def _get_author_color(self, author: str) -> str:
        """Get a consistent color for an author.
        
        Args:
            author: Author name.
        
        Returns:
            ANSI color code.
        """
        hash_val = sum(ord(c) for c in author)
        return self.author_colors[hash_val % len(self.author_colors)]
