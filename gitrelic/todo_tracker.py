"""TODO/Comment Tag Tracker Module

This module scans source code files for comment tags like TODO, FIXME, HACK,
and aggregates statistics by file and directory.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class CommentTag:
    """Data class representing a single comment tag."""
    tag: str  # TODO, FIXME, HACK, etc.
    file_path: str
    line_number: int
    content: str
    language: str
    severity: str = "normal"  # high, normal, low
    has_assignee: bool = False
    assignee: Optional[str] = None
    has_date: bool = False
    date: Optional[str] = None


@dataclass
class TodoScanResult:
    """Data class representing TODO/comment tag scan results."""
    total_tags: int = 0
    tags: List[CommentTag] = field(default_factory=list)
    files_analyzed: int = 0
    languages_found: Set[str] = field(default_factory=set)
    scan_date: datetime = field(default_factory=datetime.now)


class CommentTagPatterns:
    """Patterns for matching comment tags in different languages."""

    TAGS = [
        ("TODO", "normal"),
        ("FIXME", "high"),
        ("HACK", "high"),
        ("XXX", "high"),
        ("BUG", "high"),
        ("OPTIMIZE", "normal"),
        ("OPTIMISE", "normal"),
        ("REVIEW", "normal"),
        ("NOTE", "low"),
        ("DEPRECATED", "normal"),
        ("WIP", "normal"),
        ("TBD", "normal"),
        ("PERF", "normal"),
        ("SECURITY", "high"),
        ("SAFETY", "high"),
    ]

    TAG_PATTERN = re.compile(
        r"(?:^|\s)(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE|OPTIMISE|REVIEW|NOTE|DEPRECATED|WIP|TBD|PERF|SECURITY|SAFETY)"
        r"(?:\s*\(([^)]*)\))?\s*:?\s*(.*?)$",
        re.IGNORECASE | re.MULTILINE
    )

    ASSIGNEE_PATTERN = re.compile(
        r"@([a-zA-Z0-9_-]+)",
        re.IGNORECASE
    )

    DATE_PATTERN = re.compile(
        r"\b(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\b",
        re.IGNORECASE
    )

    @classmethod
    def get_severity(cls, tag: str) -> str:
        """Get the severity level for a tag.

        Args:
            tag: Tag name (case-insensitive).

        Returns:
            Severity level: 'high', 'normal', or 'low'.
        """
        tag_upper = tag.upper()
        for tag_name, severity in cls.TAGS:
            if tag_name == tag_upper:
                return severity
        return "normal"


class TodoScanner:
    """Scanner for detecting TODO and other comment tags in code.

    This scanner looks for common comment tags like TODO, FIXME, HACK, etc.
    across multiple programming languages.
    """

    def __init__(
        self,
        repo_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ):
        """Initialize the TodoScanner.

        Args:
            repo_path: Path to the repository.
            tags: Optional list of specific tags to look for. If None, uses default tags.
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.custom_tags = tags

        if tags:
            self.tag_pattern = re.compile(
                r"(?:^|\s)(" + "|".join(re.escape(t) for t in tags) + ")"
                r"(?:\s*\(([^)]*)\))?\s*:?\s*(.*?)$",
                re.IGNORECASE | re.MULTILINE
            )
        else:
            self.tag_pattern = CommentTagPatterns.TAG_PATTERN

    def _extract_comment_tags(
        self,
        file_path: str,
        language: str
    ) -> List[CommentTag]:
        """Extract comment tags from a file.

        Args:
            file_path: Path to the file.
            language: Language name.

        Returns:
            List of CommentTag objects.
        """
        tags = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                matches = self.tag_pattern.finditer(line)

                for match in matches:
                    tag = match.group(1)
                    paren_content = match.group(2) or ""
                    rest_content = match.group(3) or ""

                    full_content = paren_content + " " + rest_content if paren_content else rest_content

                    severity = CommentTagPatterns.get_severity(tag)

                    assignee = None
                    assignee_match = CommentTagPatterns.ASSIGNEE_PATTERN.search(full_content)
                    if assignee_match:
                        assignee = assignee_match.group(1)

                    date = None
                    date_match = CommentTagPatterns.DATE_PATTERN.search(full_content)
                    if date_match:
                        date = date_match.group(1)

                    tag_info = CommentTag(
                        tag=tag.upper(),
                        file_path=str(Path(file_path).relative_to(self.repo_path)),
                        line_number=line_num,
                        content=full_content.strip(),
                        language=language,
                        severity=severity,
                        has_assignee=assignee is not None,
                        assignee=assignee,
                        has_date=date is not None,
                        date=date,
                    )
                    tags.append(tag_info)

        except Exception as e:
            pass

        return tags

    def scan(
        self,
        files: Optional[List[str]] = None,
        extensions: Optional[List[str]] = None
    ) -> TodoScanResult:
        """Scan for comment tags.

        Args:
            files: Optional list of specific files to scan. If None, scans all supported files.
            extensions: Optional list of file extensions to include.

        Returns:
            TodoScanResult with scan results.
        """
        from .zombie import LanguagePatterns

        result = TodoScanResult()

        if files is None:
            files = self._get_supported_files(extensions)

        for file_path in files:
            full_path = self.repo_path / file_path

            patterns, language = LanguagePatterns.get_patterns(str(full_path))

            if not patterns:
                continue

            result.languages_found.add(language)
            result.files_analyzed += 1

            tags = self._extract_comment_tags(str(full_path), language)
            result.tags.extend(tags)
            result.total_tags += len(tags)

        return result

    def _get_supported_files(self, extensions: Optional[List[str]] = None) -> List[str]:
        """Get all supported files in the repository.

        Args:
            extensions: Optional list of extensions to filter by.

        Returns:
            List of file paths relative to repo root.
        """
        supported_exts = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".go",
            ".java", ".c", ".cpp", ".h", ".hpp",
            ".rb", ".php", ".swift", ".kt", ".rs",
            ".sh", ".bash",
            ".html", ".css", ".scss", ".less",
            ".md", ".rst",
        }

        if extensions:
            supported_exts = {ext.lower() for ext in extensions}

        files = []

        for root, dirs, filenames in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                "node_modules", "__pycache__", "venv", ".git", "build", "dist", "target"
            )]

            for filename in filenames:
                ext = Path(filename).suffix.lower()
                if ext in supported_exts:
                    full_path = Path(root) / filename
                    rel_path = full_path.relative_to(self.repo_path)
                    files.append(str(rel_path))

        return files

    def get_todo_summary(self, result: TodoScanResult) -> Dict:
        """Get a summary of TODO scan results.

        Args:
            result: TodoScanResult from scan().

        Returns:
            Dictionary with summary statistics.
        """
        by_tag: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        by_file: Dict[str, int] = {}
        by_language: Dict[str, int] = {}
        by_assignee: Dict[str, int] = {}

        for tag in result.tags:
            by_tag[tag.tag] = by_tag.get(tag.tag, 0) + 1
            by_severity[tag.severity] = by_severity.get(tag.severity, 0) + 1
            by_file[tag.file_path] = by_file.get(tag.file_path, 0) + 1
            by_language[tag.language] = by_language.get(tag.language, 0) + 1

            if tag.assignee:
                by_assignee[tag.assignee] = by_assignee.get(tag.assignee, 0) + 1

        total_lines = 0
        try:
            for file_path in self._get_supported_files():
                try:
                    with open(self.repo_path / file_path, "r", encoding="utf-8", errors="replace") as f:
                        total_lines += len(f.readlines())
                except Exception:
                    pass
        except Exception:
            pass

        todo_density = 0.0
        if total_lines > 0:
            todo_density = result.total_tags / total_lines * 1000

        return {
            "total_tags": result.total_tags,
            "total_lines": total_lines,
            "todo_density_per_kilo": todo_density,
            "files_analyzed": result.files_analyzed,
            "languages": list(result.languages_found),
            "by_tag": dict(sorted(by_tag.items(), key=lambda x: x[1], reverse=True)),
            "by_severity": by_severity,
            "by_file": dict(sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:20]),
            "by_language": by_language,
            "by_assignee": dict(sorted(by_assignee.items(), key=lambda x: x[1], reverse=True)),
        }

    def get_high_priority_todos(self, result: TodoScanResult, limit: int = 10) -> List[CommentTag]:
        """Get high priority TODOs (FIXME, HACK, BUG, etc.).

        Args:
            result: TodoScanResult from scan().
            limit: Maximum number of results to return.

        Returns:
            List of high priority CommentTag objects.
        """
        high_severity = [tag for tag in result.tags if tag.severity == "high"]
        return high_severity[:limit]
