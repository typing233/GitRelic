"""Zombie Function Detection Module

This module detects zombie functions - functions that have not been
modified in a long time and have no callers in the codebase.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Iterator


@dataclass
class FunctionInfo:
    """Data class representing information about a function."""
    name: str
    file_path: str
    line_number: int
    language: str
    last_modified: Optional[datetime] = None
    is_modified_recently: bool = False
    callers: List[str] = field(default_factory=list)  # List of caller function names
    is_called: bool = False
    is_public: bool = False


@dataclass
class ZombieScanResult:
    """Data class representing zombie function scan results."""
    total_functions: int = 0
    zombie_functions: List[FunctionInfo] = field(default_factory=list)
    files_analyzed: int = 0
    languages_found: Set[str] = field(default_factory=set)
    scan_date: datetime = field(default_factory=datetime.now)


class LanguagePatterns:
    """Regular expression patterns for different programming languages."""

    PYTHON = {
        "function_def": re.compile(
            r"^[ \t]*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            re.MULTILINE
        ),
        "class_def": re.compile(
            r"^[ \t]*class\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            re.MULTILINE
        ),
        "function_call": re.compile(
            r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            re.MULTILINE
        ),
        "method_call": re.compile(
            r"\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            re.MULTILINE
        ),
        "comment": re.compile(r"#.*$", re.MULTILINE),
        "string": re.compile(r"""(['"])(?:\\.|[^\\])*?\1""", re.DOTALL),
        "is_public": lambda name: not name.startswith("_"),
    }

    JAVASCRIPT = {
        "function_def": re.compile(
            r"(?:^|\s)(?:function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(|"
            r"(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s+)?function\s*\(|"
            r"(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>|"
            r"([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*\{)",
            re.MULTILINE
        ),
        "class_method": re.compile(
            r"^[ \t]+(?:async\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(",
            re.MULTILINE
        ),
        "function_call": re.compile(
            r"([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(",
            re.MULTILINE
        ),
        "method_call": re.compile(
            r"\.([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(",
            re.MULTILINE
        ),
        "comment": re.compile(r"//.*$|/\*.*?\*/", re.MULTILINE | re.DOTALL),
        "string": re.compile(r"""(['"`])(?:\\.|[^\\])*?\1""", re.DOTALL),
        "is_public": lambda name: not name.startswith("_"),
    }

    TYPESCRIPT = JAVASCRIPT

    GO = {
        "function_def": re.compile(
            r"^[ \t]*(?:func\s+(?:\([^)]+\)\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\()",
            re.MULTILINE
        ),
        "method_def": re.compile(
            r"^[ \t]*func\s+\(\s*\*?([a-zA-Z_][a-zA-Z0-9_]*)\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            re.MULTILINE
        ),
        "function_call": re.compile(
            r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            re.MULTILINE
        ),
        "method_call": re.compile(
            r"\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            re.MULTILINE
        ),
        "comment": re.compile(r"//.*$|/\*.*?\*/", re.MULTILINE | re.DOTALL),
        "string": re.compile(r"""(['"`])(?:\\.|[^\\])*?\1|`[^`]*`""", re.DOTALL),
        "is_public": lambda name: name[0].isupper() if name else False,
    }

    @classmethod
    def get_patterns(cls, file_path: str) -> Tuple[Optional[Dict], str]:
        """Get the appropriate patterns for a file based on its extension.

        Args:
            file_path: Path to the file.

        Returns:
            Tuple of (patterns dict, language name), or (None, "") if unsupported.
        """
        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            return cls.PYTHON, "Python"
        elif ext in (".js", ".jsx"):
            return cls.JAVASCRIPT, "JavaScript"
        elif ext in (".ts", ".tsx"):
            return cls.TYPESCRIPT, "TypeScript"
        elif ext == ".go":
            return cls.GO, "Go"

        return None, ""


class ZombieScanner:
    """Scanner for detecting zombie functions in code.

    A zombie function is defined as:
    1. Not modified for a specified period (default: 90 days)
    2. Not called by any other function in the codebase
    3. Not a public/exported API (unless specified otherwise)
    """

    def __init__(
        self,
        repo_path: Optional[str] = None,
        days_threshold: int = 90,
        include_private: bool = True,
    ):
        """Initialize the ZombieScanner.

        Args:
            repo_path: Path to the repository.
            days_threshold: Number of days without modification to be considered zombie.
            include_private: Whether to include private functions in the scan.
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.days_threshold = days_threshold
        self.include_private = include_private
        self.cutoff_date = datetime.now() - timedelta(days=days_threshold)

    def _remove_comments_and_strings(self, content: str, patterns: Dict) -> str:
        """Remove comments and strings from content to avoid false positives.

        Newlines inside comments and strings are preserved so that line numbers
        calculated from the cleaned content remain accurate.

        Args:
            content: File content.
            patterns: Language patterns dict.

        Returns:
            Content with comments and strings replaced by spaces (newlines kept).
        """
        def _blank_keep_newlines(match: re.Match) -> str:
            return re.sub(r"[^\n]", " ", match.group(0))

        result = patterns["comment"].sub(_blank_keep_newlines, content)
        result = patterns["string"].sub(_blank_keep_newlines, result)

        return result

    def _extract_functions(
        self,
        file_path: str,
        patterns: Dict,
        language: str
    ) -> List[FunctionInfo]:
        """Extract function definitions from a file.

        Args:
            file_path: Path to the file.
            patterns: Language patterns dict.
            language: Language name.

        Returns:
            List of FunctionInfo objects.
        """
        functions = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            clean_content = self._remove_comments_and_strings(content, patterns)

            func_pattern = patterns["function_def"]
            matches = func_pattern.finditer(clean_content)

            for match in matches:
                func_name = match.group(1)
                if not func_name:
                    for i in range(2, 5):
                        if match.lastindex and i <= match.lastindex and match.group(i):
                            func_name = match.group(i)
                            break

                if func_name and func_name.strip():
                    line_number = clean_content[:match.start()].count("\n") + 1
                    
                    is_public = patterns["is_public"](func_name)

                    func_info = FunctionInfo(
                        name=func_name,
                        file_path=str(Path(file_path).relative_to(self.repo_path)),
                        line_number=line_number,
                        language=language,
                        is_public=is_public,
                    )
                    functions.append(func_info)

            if language in ("JavaScript", "TypeScript"):
                class_matches = patterns.get("class_method", re.compile(r"")).finditer(clean_content)
                for match in class_matches:
                    func_name = match.group(1)
                    if func_name and func_name.strip() and func_name != "constructor":
                        line_number = clean_content[:match.start()].count("\n") + 1
                        func_info = FunctionInfo(
                            name=func_name,
                            file_path=str(Path(file_path).relative_to(self.repo_path)),
                            line_number=line_number,
                            language=language,
                            is_public=patterns["is_public"](func_name),
                        )
                        functions.append(func_info)

        except Exception as e:
            pass

        return functions

    def _extract_all_calls(
        self,
        file_path: str,
        patterns: Dict
    ) -> Set[str]:
        """Extract all function calls from a file.

        Args:
            file_path: Path to the file.
            patterns: Language patterns dict.

        Returns:
            Set of function/method names that are called.
        """
        calls = set()

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            clean_content = self._remove_comments_and_strings(content, patterns)

            func_calls = patterns["function_call"].findall(clean_content)
            for call in func_calls:
                if call:
                    calls.add(call)

            method_calls = patterns["method_call"].findall(clean_content)
            for call in method_calls:
                if call:
                    calls.add(call)

        except Exception as e:
            pass

        return calls

    def _get_file_last_modified(self, file_path: str) -> Optional[datetime]:
        """Get the last modification date of a file from git or filesystem.

        Args:
            file_path: Path to the file.

        Returns:
            Datetime of last modification, or None.
        """
        try:
            from .git_data import GitDataExtractor
            extractor = GitDataExtractor(str(self.repo_path))
            history = extractor.get_file_modification_history(file_path)
            if history.last_modified:
                return history.last_modified
        except Exception:
            pass

        try:
            mtime = os.path.getmtime(self.repo_path / file_path)
            return datetime.fromtimestamp(mtime)
        except Exception:
            pass

        return None

    def scan(
        self,
        files: Optional[List[str]] = None,
        extensions: Optional[List[str]] = None
    ) -> ZombieScanResult:
        """Scan for zombie functions.

        Args:
            files: Optional list of specific files to scan. If None, scans all supported files.
            extensions: Optional list of file extensions to include (e.g., ['.py', '.js']).

        Returns:
            ZombieScanResult with scan results.
        """
        result = ZombieScanResult()

        if files is None:
            files = self._get_supported_files(extensions)

        all_functions: Dict[str, FunctionInfo] = {}
        all_calls: Set[str] = set()

        # Cache last-modified per file to avoid redundant git-blame calls.
        file_last_modified: Dict[str, Optional[datetime]] = {}

        for file_path in files:
            full_path = self.repo_path / file_path
            
            patterns, language = LanguagePatterns.get_patterns(str(full_path))
            
            if not patterns:
                continue

            result.languages_found.add(language)
            result.files_analyzed += 1

            # Compute the file's last-modified date once.
            last_modified = self._get_file_last_modified(file_path)
            file_last_modified[file_path] = last_modified

            functions = self._extract_functions(str(full_path), patterns, language)
            for func in functions:
                func_key = f"{func.file_path}:{func.name}"
                all_functions[func_key] = func
                result.total_functions += 1

                func.last_modified = last_modified

                if last_modified and last_modified >= self.cutoff_date:
                    func.is_modified_recently = True

            calls = self._extract_all_calls(str(full_path), patterns)
            all_calls.update(calls)

        for func in all_functions.values():
            if func.name in all_calls:
                func.is_called = True

        for func in all_functions.values():
            is_zombie = False

            if not func.is_called:
                if not func.is_modified_recently:
                    if self.include_private or func.is_public:
                        is_zombie = True

            if is_zombie:
                result.zombie_functions.append(func)

        result.zombie_functions.sort(key=lambda x: x.file_path)

        return result

    def _get_supported_files(self, extensions: Optional[List[str]] = None) -> List[str]:
        """Get all supported files in the repository.

        Args:
            extensions: Optional list of extensions to filter by.

        Returns:
            List of file paths relative to repo root.
        """
        supported_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".go"}
        
        if extensions:
            supported_exts = {ext.lower() for ext in extensions}

        files = []

        for root, dirs, filenames in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".git")]

            for filename in filenames:
                ext = Path(filename).suffix.lower()
                if ext in supported_exts:
                    full_path = Path(root) / filename
                    rel_path = full_path.relative_to(self.repo_path)
                    files.append(str(rel_path))

        return files

    def get_zombie_summary(self, result: ZombieScanResult) -> Dict:
        """Get a summary of zombie scan results.

        Args:
            result: ZombieScanResult from scan().

        Returns:
            Dictionary with summary statistics.
        """
        by_language: Dict[str, int] = {}
        by_file: Dict[str, int] = {}

        for func in result.zombie_functions:
            by_language[func.language] = by_language.get(func.language, 0) + 1
            by_file[func.file_path] = by_file.get(func.file_path, 0) + 1

        zombie_rate = 0.0
        if result.total_functions > 0:
            zombie_rate = len(result.zombie_functions) / result.total_functions * 100

        return {
            "total_functions": result.total_functions,
            "zombie_count": len(result.zombie_functions),
            "zombie_rate": zombie_rate,
            "files_analyzed": result.files_analyzed,
            "languages": list(result.languages_found),
            "by_language": by_language,
            "by_file": dict(sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:10]),
            "days_threshold": self.days_threshold,
        }
