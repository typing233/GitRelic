"""Git Data Extraction Module

This module handles extraction of data from git log and git blame commands,
providing structured data for further analysis.
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class GitCommit:
    """Data class representing a single git commit."""
    hash: str
    author: str
    author_email: str
    date: datetime
    message: str
    files_changed: List[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0


@dataclass
class GitBlameLine:
    """Data class representing a single line from git blame."""
    file_path: str
    line_number: int
    commit_hash: str
    author: str
    date: datetime
    line_content: str


@dataclass
class FileModificationHistory:
    """Data class representing modification history of a file."""
    file_path: str
    author_stats: Dict[str, int] = field(default_factory=dict)  # author -> line count
    last_modified: Optional[datetime] = None
    total_commits: int = 0
    authors: List[str] = field(default_factory=list)


class GitDataExtractor:
    """Extractor for git repository data.

    This class provides methods to extract and parse data from git log
    and git blame commands.
    """

    def __init__(self, repo_path: Optional[str] = None):
        """Initialize the GitDataExtractor.

        Args:
            repo_path: Path to the git repository. If None, uses current working directory.
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.git_dir = self.repo_path / ".git"

        if not self.git_dir.exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def _run_git_command(self, args: List[str]) -> str:
        """Run a git command and return the output.

        Args:
            args: List of git command arguments.

        Returns:
            Standard output of the git command.
        """
        cmd = ["git"] + args
        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            errors="replace",
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Git command failed: {' '.join(cmd)}\n"
                f"Error: {result.stderr}"
            )

        return result.stdout

    def get_commits(self, since: Optional[str] = None, 
                    until: Optional[str] = None) -> List[GitCommit]:
        """Get all commits from the repository.

        Args:
            since: Only commits more recent than a specific date.
            until: Only commits older than a specific date.

        Returns:
            List of GitCommit objects.
        """
        args = ["log", "--pretty=format:%H|%an|%ae|%ai|%s", "--date=iso"]
        
        if since:
            args.append(f"--since={since}")
        if until:
            args.append(f"--until={until}")

        log_output = self._run_git_command(args)
        commits = []

        for line in log_output.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|", 4)
            if len(parts) < 5:
                continue

            commit_hash, author, author_email, date_str, message = parts
            
            try:
                dt = datetime.fromisoformat(date_str)
                date = dt.replace(tzinfo=None)
            except (ValueError, IndexError):
                date = datetime.now()

            commit = GitCommit(
                hash=commit_hash,
                author=author,
                author_email=author_email,
                date=date,
                message=message,
            )

            stats = self._get_commit_stats(commit_hash)
            commit.files_changed = stats["files"]
            commit.insertions = stats["insertions"]
            commit.deletions = stats["deletions"]

            commits.append(commit)

        return commits

    def _get_commit_stats(self, commit_hash: str) -> Dict:
        """Get file change statistics for a specific commit.

        Args:
            commit_hash: The commit hash to analyze.

        Returns:
            Dictionary with files, insertions, and deletions.
        """
        try:
            output = self._run_git_command(["show", "--stat", "--format=", commit_hash])
            lines = output.strip().split("\n")

            files = []
            insertions = 0
            deletions = 0

            for line in lines:
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        file_path = parts[0].strip()
                        if file_path and file_path not in files:
                            files.append(file_path)
                        
                        stats_part = parts[1].strip()
                        insertion_matches = re.findall(r"(\d+)\s*\+", stats_part)
                        deletion_matches = re.findall(r"(\d+)\s*\-", stats_part)
                        
                        if insertion_matches:
                            insertions += int(insertion_matches[0])
                        if deletion_matches:
                            deletions += int(deletion_matches[0])

            return {
                "files": files,
                "insertions": insertions,
                "deletions": deletions,
            }
        except Exception:
            return {"files": [], "insertions": 0, "deletions": 0}

    def get_blame(self, file_path: str) -> List[GitBlameLine]:
        """Get blame information for a specific file.

        Args:
            file_path: Path to the file relative to repository root.

        Returns:
            List of GitBlameLine objects.
        """
        try:
            output = self._run_git_command([
                "blame", 
                "--line-porcelain", 
                file_path
            ])
            
            lines = []
            current_line: Optional[GitBlameLine] = None
            line_number = 0

            for output_line in output.split("\n"):
                if not output_line.strip():
                    continue

                if output_line.startswith("\t"):
                    if current_line:
                        current_line.line_content = output_line[1:]
                        lines.append(current_line)
                        current_line = None
                    continue

                parts = output_line.split(" ", 1)
                if len(parts) < 2:
                    continue

                key, value = parts[0], parts[1] if len(parts) > 1 else ""

                if len(key) == 40 and re.match(r"^[0-9a-f]{40}$", key, re.IGNORECASE):
                    hash_parts = output_line.split()
                    if len(hash_parts) >= 3:
                        line_number = int(hash_parts[2]) if len(hash_parts) > 2 else 0
                        current_line = GitBlameLine(
                            file_path=file_path,
                            line_number=line_number,
                            commit_hash=hash_parts[0],
                            author="",
                            date=datetime.now(),
                            line_content="",
                        )
                    continue

                if current_line:
                    if key == "author":
                        current_line.author = value
                    elif key == "author-time":
                        try:
                            current_line.date = datetime.fromtimestamp(int(value))
                        except ValueError:
                            pass
                    elif key == "author-tz":
                        pass

            return lines

        except Exception as e:
            return []

    def get_all_files(self) -> List[str]:
        """Get all tracked files in the repository.

        Returns:
            List of file paths relative to repository root.
        """
        try:
            output = self._run_git_command(["ls-files"])
            return [line.strip() for line in output.strip().split("\n") if line.strip()]
        except Exception:
            return []

    def get_file_modification_history(
        self, 
        file_path: str
    ) -> FileModificationHistory:
        """Get modification history for a specific file.

        Args:
            file_path: Path to the file.

        Returns:
            FileModificationHistory object.
        """
        history = FileModificationHistory(file_path=file_path)

        blame_lines = self.get_blame(file_path)
        
        if not blame_lines:
            return history

        author_stats: Dict[str, int] = {}
        authors_set = set()
        last_modified: Optional[datetime] = None

        for line in blame_lines:
            author = line.author
            author_stats[author] = author_stats.get(author, 0) + 1
            authors_set.add(author)

            if last_modified is None or line.date > last_modified:
                last_modified = line.date

        history.author_stats = author_stats
        history.authors = list(authors_set)
        history.last_modified = last_modified

        try:
            log_output = self._run_git_command([
                "log", "--oneline", "--follow", "--", file_path
            ])
            history.total_commits = len([
                line for line in log_output.strip().split("\n") 
                if line.strip()
            ])
        except Exception:
            pass

        return history

    def get_commit_activity_by_author(self, commits: Optional[List[GitCommit]] = None) -> Dict[str, List[GitCommit]]:
        """Group commits by author.

        Args:
            commits: Optional list of commits. If None, fetches all commits.

        Returns:
            Dictionary mapping author names to list of their commits.
        """
        if commits is None:
            commits = self.get_commits()

        by_author: Dict[str, List[GitCommit]] = {}
        for commit in commits:
            if commit.author not in by_author:
                by_author[commit.author] = []
            by_author[commit.author].append(commit)

        return by_author

    def get_commit_activity_by_month(
        self, 
        commits: Optional[List[GitCommit]] = None
    ) -> Dict[str, Dict[str, int]]:
        """Get commit activity grouped by month and author.

        Args:
            commits: Optional list of commits.

        Returns:
            Dictionary mapping "YYYY-MM" to author commit counts.
        """
        if commits is None:
            commits = self.get_commits()

        by_month: Dict[str, Dict[str, int]] = {}

        for commit in commits:
            month_key = commit.date.strftime("%Y-%m")
            
            if month_key not in by_month:
                by_month[month_key] = {}
            
            if commit.author not in by_month[month_key]:
                by_month[month_key][commit.author] = 0
            
            by_month[month_key][commit.author] += 1

        return by_month
