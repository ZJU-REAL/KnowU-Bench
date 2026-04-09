"""Log viewer module for MobileWorld trajectories.

This module provides a web-based viewer for trajectory logs using FastHTML.
"""

from mobile_world.core.log_viewer.app import app, main, rt

__all__ = ["app", "main", "rt"]
