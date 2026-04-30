"""Code Ownership Statistics Module

This module handles statistics calculation for code ownership based on
git log and git blame data, providing data structure for heatmap visualization.
"""

import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

from .git_data import GitCommit, GitDataExtractor, FileModificationHistory


@dataclass
class FileOwnership:
    """Data class representing ownership statistics for a single file."""
    file_path: str
    total_lines: int = 0
    author_lines: Dict[str, int] = field(default_factory=dict)  # author -> line count
    author_percentages: Dict[str, float] = field(default_factory=dict)  # author -> percentage
    primary_author: Optional[str] = None
    ownership_concentration: float = 0.0  # HHI index or primary author percentage
    last_modified: Optional[datetime] = None
    num_authors: int = 0


@dataclass
class DirectoryOwnership:
    """Data class representing ownership statistics for a directory."""
    directory_path: str
    total_lines: int = 0
    total_files: int = 0
    author_lines: Dict[str, int] = field(default_factory=dict)
    author_file_counts: Dict[str, int] = field(default_factory=dict)  # author -> files modified
    author_percentages: Dict[str, float] = field(default_factory=dict)
    primary_author: Optional[str] = None
    ownership_concentration: float = 0.0
    files: List[FileOwnership] = field(default_factory=list)
    subdirectories: Dict[str, 'DirectoryOwnership'] = field(default_factory=dict)


class OwnershipAnalyzer:
    """Analyzer for code ownership statistics.

    This class analyzes git repository data to compute ownership statistics
    at file and directory levels.
    """

    def __init__(self, extractor: GitDataExtractor):
        """Initialize the OwnershipAnalyzer.

        Args:
            extractor: GitDataExtractor instance for accessing repository data.
        """
        self.extractor = extractor

    def analyze_file_ownership(self, file_path: str) -> Optional[FileOwnership]:
        """Analyze ownership for a single file.

        Args:
            file_path: Path to the file relative to repository root.

        Returns:
            FileOwnership object or None if file cannot be analyzed.
        """
        history = self.extractor.get_file_modification_history(file_path)
        
        if not history.author_stats:
            return None

        ownership = FileOwnership(file_path=file_path)

        total_lines = sum(history.author_stats.values())
        ownership.total_lines = total_lines
        ownership.author_lines = dict(history.author_stats)
        ownership.last_modified = history.last_modified
        ownership.num_authors = len(history.authors)

        if total_lines > 0:
            ownership.author_percentages = {
                author: count / total_lines * 100
                for author, count in history.author_stats.items()
            }

            primary_author = max(history.author_stats.items(), key=lambda x: x[1])[0]
            ownership.primary_author = primary_author

            ownership.ownership_concentration = self._calculate_hhi(
                list(history.author_stats.values())
            )

        return ownership

    def _calculate_hhi(self, values: List[int]) -> float:
        """Calculate Herfindahl-Hirschman Index for ownership concentration.

        The HHI ranges from 0 (perfectly distributed) to 10000 (monopoly).
        Normalized to 0-1 range for this tool.

        Args:
            values: List of counts (lines per author).

        Returns:
            Normalized HHI (0-1).
        """
        if not values or sum(values) == 0:
            return 0.0

        total = sum(values)
        percentages = [(v / total) * 100 for v in values]
        
        hhi = sum(p ** 2 for p in percentages)
        
        return hhi / 10000.0

    def analyze_directory_ownership(
        self, 
        directory_path: str = "",
        recursive: bool = True
    ) -> DirectoryOwnership:
        """Analyze ownership for a directory and optionally its subdirectories.

        Args:
            directory_path: Directory path relative to repository root.
                Empty string means root directory.
            recursive: Whether to analyze subdirectories recursively.

        Returns:
            DirectoryOwnership object.
        """
        all_files = self.extractor.get_all_files()

        directory = DirectoryOwnership(directory_path=directory_path)

        dir_prefix = directory_path + "/" if directory_path else ""
        files_in_dir = []
        subdirs_found: Set[str] = set()

        for file_path in all_files:
            if dir_prefix and not file_path.startswith(dir_prefix):
                continue

            relative_to_dir = file_path[len(dir_prefix):] if dir_prefix else file_path
            parts = relative_to_dir.split("/")

            if len(parts) == 1 or (len(parts) == 2 and not parts[0]):
                files_in_dir.append(file_path)
            elif recursive:
                subdir_name = parts[0] if parts[0] else parts[1] if len(parts) > 1 else ""
                if subdir_name:
                    subdirs_found.add(subdir_name)

        for file_path in files_in_dir:
            file_ownership = self.analyze_file_ownership(file_path)
            if file_ownership:
                directory.files.append(file_ownership)
                directory.total_files += 1
                directory.total_lines += file_ownership.total_lines

                for author, lines in file_ownership.author_lines.items():
                    directory.author_lines[author] = directory.author_lines.get(author, 0) + lines
                    directory.author_file_counts[author] = directory.author_file_counts.get(author, 0) + 1

        if directory.total_lines > 0:
            directory.author_percentages = {
                author: lines / directory.total_lines * 100
                for author, lines in directory.author_lines.items()
            }

            if directory.author_lines:
                primary_author = max(directory.author_lines.items(), key=lambda x: x[1])[0]
                directory.primary_author = primary_author

                directory.ownership_concentration = self._calculate_hhi(
                    list(directory.author_lines.values())
                )

        if recursive:
            for subdir in subdirs_found:
                full_subdir = f"{directory_path}/{subdir}" if directory_path else subdir
                subdir_ownership = self.analyze_directory_ownership(
                    full_subdir, recursive=True
                )
                directory.subdirectories[subdir] = subdir_ownership

        return directory

    def get_ownership_heatmap_data(
        self,
        directory_path: str = "",
        max_depth: int = 3
    ) -> Dict:
        """Generate heatmap data structure for visualization.

        Args:
            directory_path: Starting directory path.
            max_depth: Maximum depth to traverse.

        Returns:
            Dictionary with heatmap-ready data structure.
        """
        root_dir = self.analyze_directory_ownership(directory_path, recursive=True)

        def flatten_directory(
            dir_obj: DirectoryOwnership,
            current_depth: int,
            parent_path: str
        ) -> List[Dict]:
            result = []
            
            if parent_path:
                full_path = parent_path.rstrip("/") + "/" + dir_obj.directory_path
            else:
                full_path = dir_obj.directory_path
            
            display_path = full_path if full_path else "/"

            if dir_obj.total_files > 0:
                result.append({
                    "path": display_path,
                    "type": "directory",
                    "depth": current_depth,
                    "total_lines": dir_obj.total_lines,
                    "total_files": dir_obj.total_files,
                    "ownership_concentration": dir_obj.ownership_concentration,
                    "primary_author": dir_obj.primary_author,
                    "author_lines": dir_obj.author_lines,
                })

            for file_own in dir_obj.files:
                if full_path:
                    file_display_path = full_path.rstrip("/") + "/" + file_own.file_path.split("/")[-1]
                else:
                    file_display_path = file_own.file_path.split("/")[-1]
                result.append({
                    "path": file_display_path,
                    "type": "file",
                    "depth": current_depth + 1,
                    "total_lines": file_own.total_lines,
                    "ownership_concentration": file_own.ownership_concentration,
                    "primary_author": file_own.primary_author,
                    "author_lines": file_own.author_lines,
                })

            if current_depth < max_depth:
                for subdir_name, subdir_obj in dir_obj.subdirectories.items():
                    result.extend(
                        flatten_directory(
                            subdir_obj, 
                            current_depth + 1, 
                            full_path + "/" if full_path else ""
                        )
                    )

            return result

        return {
            "root": root_dir,
            "items": flatten_directory(root_dir, 0, ""),
            "all_authors": list(self._get_all_authors(root_dir)),
        }

    def _get_all_authors(self, dir_obj: DirectoryOwnership) -> Set[str]:
        """Get all authors from directory and subdirectories."""
        authors = set(dir_obj.author_lines.keys())
        
        for file_own in dir_obj.files:
            authors.update(file_own.author_lines.keys())
        
        for subdir in dir_obj.subdirectories.values():
            authors.update(self._get_all_authors(subdir))
        
        return authors

    def get_commit_activity_summary(
        self,
        months: int = 12
    ) -> Dict:
        """Get commit activity summary for visualization as bar chart.

        Args:
            months: Number of months to look back.

        Returns:
            Dictionary with activity data grouped by month.
        """
        commits = self.extractor.get_commits()
        
        if not commits:
            return {"months": [], "authors": [], "activity": {}}

        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        recent_commits = [c for c in commits if c.date >= cutoff_date]

        by_month = self.extractor.get_commit_activity_by_month(recent_commits)
        
        sorted_months = sorted(by_month.keys())
        
        all_authors = set()
        for month_data in by_month.values():
            all_authors.update(month_data.keys())
        
        all_authors = sorted(all_authors)

        return {
            "months": sorted_months,
            "authors": all_authors,
            "activity": by_month,
            "total_commits": len(recent_commits),
        }
