"""User task runner module for executing single disposable tasks.

Unlike the predefined task runner, this runner:
- Takes a user-provided goal string directly
- Does not require task initialization or validation
- Does not score or evaluate the task
- Handles ASK_USER action interactively via terminal
"""

from .runner import run_user_task

__all__ = ["run_user_task"]
