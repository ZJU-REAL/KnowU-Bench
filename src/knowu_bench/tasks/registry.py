import importlib.util
import inspect
import os
from pathlib import Path

from loguru import logger

import knowu_bench


class TaskRegistry:
    _scan_logged: set[str] = set()

    def __init__(self, task_set_path: str | None = None):
        """
        Initialize TaskRegistry and automatically scan for tasks.

        Args:
            task_set_path: Path to the directory containing task files.
                          If None, uses the installed knowu_bench package path.
        """
        self.tasks: dict[str, object] = {}
        self._profile_cache: list[tuple[str, str]] | None = None
        if task_set_path is None:
            package_path = Path(knowu_bench.__file__).parent
            self.task_set_path = str(package_path / "tasks" / "definitions")
            self.user_profile_path = str(package_path / "user_profile")
        else:
            self.task_set_path = task_set_path
            task_root = Path(task_set_path).resolve()
            self.user_profile_path = str(task_root.parent.parent / "user_profile")
        self._scan_and_register_tasks()

    def _scan_and_register_tasks(self):
        """Recursively scan the task_set directory and register all tasks."""
        should_log = self.task_set_path not in TaskRegistry._scan_logged
        if should_log:
            TaskRegistry._scan_logged.add(self.task_set_path)
            logger.info(f"Starting task scanning in directory: {self.task_set_path}")

        if not os.path.exists(self.task_set_path):
            logger.warning(f"Task directory not found: {self.task_set_path}")
            return

        task_files = list(Path(self.task_set_path).rglob("*.py"))

        for file_path in task_files:
            if file_path.name == "__init__.py":
                continue

            self._load_tasks_from_file(file_path)

        if should_log:
            logger.info(f"Task registration complete. Total tasks registered: {len(self.tasks)}")
            logger.info(f"Registered tasks: {list(self.tasks.keys())}")

    def _load_tasks_from_file(self, file_path: Path):
        """
        Load and register tasks from a single Python file.

        Args:
            file_path: Path to the Python file
        """
        try:
            module_name = str(file_path.with_suffix("")).replace(os.sep, ".")

            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.warning(f"Could not load spec for file: {file_path}")
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            self._register_tasks_from_module(module, file_path)

        except Exception as e:
            logger.error(f"Error loading tasks from {file_path}: {e}", exc_info=True)

    def _register_tasks_from_module(self, module, file_path: Path):
        """
        Register all BaseTask subclasses from a module.

        Args:
            module: The loaded Python module
            file_path: Path to the source file (for logging)
        """
        try:
            from knowu_bench.tasks.base import BaseTask
        except ImportError:
            logger.error("Could not import BaseTask. Please ensure it exists.")
            return

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseTask)
                and obj is not BaseTask
                and obj.__module__ == module.__name__
            ):
                if self._should_use_profile_variants(file_path):
                    profiles = self._get_user_profiles()
                    supported = getattr(obj, "supported_profiles", None)
                    for profile_id, profile_path in profiles:
                        if supported is not None and profile_id not in supported:
                            continue
                        params = {
                            "profile_id": profile_id,
                            "profile_path": profile_path,
                        }
                        self._register_task_instance(obj, file_path, params=params)
                else:
                    self._register_task_instance(obj, file_path, params=None)

    def _register_task_instance(self, task_cls, file_path: Path, params: dict | None):
        try:
            task_instance = task_cls(params) if params is not None else task_cls()
            task_name = task_instance.name
            if task_name in self.tasks:
                logger.warning(
                    f"Task '{task_name}' already registered. Overwriting with instance from {file_path}"
                )
            self.tasks[task_name] = task_instance
        except Exception as e:
            name_hint = task_cls.__name__
            if params and params.get("profile_id"):
                name_hint = f"{name_hint}@{params['profile_id']}"
            logger.error(
                f"Error instantiating task '{name_hint}' from {file_path}: {e}",
                exc_info=True,
            )

    def _get_user_profiles(self) -> list[tuple[str, str]]:
        if self._profile_cache is not None:
            return self._profile_cache

        profiles: list[tuple[str, str]] = []
        profile_dir = Path(self.user_profile_path)
        if not profile_dir.exists():
            self._profile_cache = []
            return self._profile_cache

        for profile_path in sorted(profile_dir.glob("*.yaml")):
            profile_id = profile_path.stem
            if profile_id == "template":
                continue
            profiles.append((profile_id, str(profile_path)))

        self._profile_cache = profiles
        return self._profile_cache

    def _should_use_profile_variants(self, file_path: Path) -> bool:
        parts = {part.lower() for part in file_path.parts}
        return "routine" in parts or "preference" in parts

    def get_task(self, task_name: str):
        """
        Retrieve a task by name.

        Args:
            task_name: Name of the task class

        Returns:
            Task instance

        Raises:
            KeyError: If task is not found
        """
        if task_name not in self.tasks:
            logger.error(
                f"Task '{task_name}' not found. Available tasks: {list(self.tasks.keys())}"
            )
            raise KeyError(f"Task '{task_name}' not found in registry")

        return self.tasks[task_name]

    def list_tasks(self) -> list:
        """Return a list of all registered task names."""
        return list(self.tasks.keys())

    def has_task(self, task_name: str) -> bool:
        """Check if a task is registered."""
        return task_name in self.tasks
