"""
Generic callback helper for new apps (jingdian, chilemei, tuantuan).

Provides unified config management, callback file storage, and verification
functions. Each app's callback files are stored in a separate directory:
    artifacts/<device>/<app_name>_callbacks/

- jingdian: same callback structure as mall (task_name, product_info, address_info)
- chilemei / tuantuan: food-order structure (event, order.foods, order.address, ...)
"""

import json
import time
from typing import Any

from loguru import logger
from pydantic import BaseModel

from mobile_world.runtime.utils.constants import ARTIFACTS_ROOT, device_dir

SUPPORTED_APPS = {"jingdian", "chilemei", "tuantuan"}


# Now just for jingdian
class AppConfig(BaseModel):
    """Generic app config, mirrors MallConfig."""

    showSplashAd: bool = False
    requireLogin: bool = False
    defaultUserId: str = "mashu001"
    mockOrders: list[dict] = []


def _config_file(app_name: str):
    return ARTIFACTS_ROOT / f"{app_name}_config.json"


def _callback_dir(device_name: str, app_name: str):
    return device_dir(ARTIFACTS_ROOT, device_name) / f"{app_name}_callbacks"


def get_app_config(app_name: str) -> AppConfig:
    """Read config for app_name; returns defaults when the file is missing."""
    cfg = _config_file(app_name)
    if not cfg.exists():
        return AppConfig()
    with open(cfg) as f:
        return AppConfig.model_validate(json.load(f))


def set_app_config(app_name: str, config: AppConfig) -> None:
    """Persist config for app_name."""
    cfg = _config_file(app_name)
    with open(cfg, "w") as f:
        json.dump(config.model_dump(), f)


def clear_app_config(app_name: str) -> None:
    """Delete config file for app_name."""
    cfg = _config_file(app_name)
    if cfg.exists():
        cfg.unlink()


def write_app_callback_file(
    app_name: str,
    callback_data: dict,
    task_name: str,
    device_name: str,
) -> str:
    """Write callback JSON to artifacts/<device>/<app_name>_callbacks/."""
    cb_dir = _callback_dir(device_name, app_name)
    cb_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    callback_file = cb_dir / f"{task_name}_callback_{ts}.json"
    with open(callback_file, "w", encoding="utf-8") as f:
        json.dump(callback_data, f, indent=2, ensure_ascii=False)
    return str(callback_file)


def get_app_callback_content(
    app_name: str,
    num: int = 1,
    device_name: str | None = None,
) -> list[dict]:
    """Return the num most-recent callback records for app_name.

    If device_name is given, only searches that device's directory;
    otherwise searches across all devices.
    """
    if device_name:
        cb_dir = _callback_dir(device_name, app_name)
        callback_files = list(cb_dir.glob("*_callback_*.json")) if cb_dir.exists() else []
    else:
        pattern = f"**/{app_name}_callbacks/*_callback_*.json"
        callback_files = list(ARTIFACTS_ROOT.glob(pattern))

    callback_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    contents: list[dict] = []
    for file in callback_files[:num]:
        with open(file) as f:
            contents.append(json.load(f))
    return contents


def clear_app_callback_files(app_name: str, device_name: str) -> None:
    """Remove all callback JSON files for app_name on device_name."""
    cb_dir = _callback_dir(device_name, app_name)
    if cb_dir.exists():
        for file in cb_dir.glob("*.json"):
            file.unlink()
