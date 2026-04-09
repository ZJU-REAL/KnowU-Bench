#!/usr/bin/env python3
"""
Task testing script for mobile_world.

Usage:
    python test_task.py                              # Run default task
    python test_task.py --task CheckGithubInfoTask   # Run a specific task
    python test_task.py --list                       # List all available tasks
    python test_task.py --task CheckGithubInfoTask --question "What is today?"  # Ask a specific question
"""

import argparse

from mobile_world.runtime.controller import AndroidController
from mobile_world.tasks.registry import TaskRegistry


def main():
    parser = argparse.ArgumentParser(description="Test mobile_world tasks")
    parser.add_argument("--task", "-t", help="Task name")
    parser.add_argument("--device", "-d", default="emulator-5554", help="Device identifier")
    parser.add_argument("--question", "-q", default=None, help="Question to ask user agent")
    parser.add_argument("--list", "-l", action="store_true", help="List all tasks")
    args = parser.parse_args()

    registry = TaskRegistry()

    if args.list:
        tasks = registry.list_tasks()
        print(f"\nAvailable tasks ({len(tasks)}):")
        for name in sorted(tasks):
            print(f"  - {name}")
        return

    if not args.task:
        parser.error("--task is required when not using --list")

    task = registry.get_task(args.task)
    controller = AndroidController(device=args.device)
    task.run_task(controller=controller, agent_question=args.question)


if __name__ == "__main__":
    main()
