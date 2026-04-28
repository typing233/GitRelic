"""GitRelic - Git Repository Analysis Tool

A command-line tool for analyzing Git repositories, generating code ownership
heatmaps, zombie function detection, TODO tracking, and technical debt radar
charts using ANSI terminal output.
"""

__version__ = "0.1.0"
__author__ = "GitRelic Team"

from . import git_data
from . import ownership
from . import renderer
from . import zombie
from . import todo_tracker
from . import metrics
from . import cli

__all__ = [
    "git_data",
    "ownership",
    "renderer",
    "zombie",
    "todo_tracker",
    "metrics",
    "cli",
]
