import json
import time

from pydantic import BaseModel

from mobile_world.runtime.utils.constants import ARTIFACTS_ROOT, device_dir

CONFIG_FILE = ARTIFACTS_ROOT / "mall_config.json"


class MallConfig(BaseModel):
    """Mall config."""

    showSplashAd: bool = False
    requireLogin: bool = False
    defaultUserId: str = "mashu001"
    mockOrders: list[dict] = []


def get_recent_callback_content(num: int = 1) -> list[dict]:
    """Get the recent callback files from the artifacts root."""
    callback_files = list(ARTIFACTS_ROOT.glob("**/*_callback_*.json"))
    callback_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    contents = []
    for file in callback_files[:num]:
        with open(file) as f:
            contents.append(json.load(f))
    return contents


def get_config() -> MallConfig:
    """Get the config from the artifacts root."""
    if not CONFIG_FILE.exists():
        return MallConfig()
    with open(CONFIG_FILE) as f:
        return MallConfig.model_validate(json.load(f))


def set_config(config: MallConfig) -> None:
    """Set the config to the artifacts root."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config.model_dump(), f)


def clear_config() -> None:
    """Clear the config from the artifacts root."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


def write_callback_file(callback_data: dict, task_name: str, device_name: str) -> str:
    callback_dir = device_dir(ARTIFACTS_ROOT, device_name) / "taodian_callbacks"
    callback_dir.mkdir(parents=True, exist_ok=True)
    callback_file = callback_dir / f"{task_name}_callback_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(callback_file, "w", encoding="utf-8") as f:
        json.dump(callback_data, f, indent=2, ensure_ascii=False)
    return str(callback_file)


def clear_callback_files(device_name) -> None:
    """Clear the callback files from the artifacts root."""
    callback_dir = device_dir(ARTIFACTS_ROOT, device_name) / "taodian_callbacks"
    if callback_dir.exists():
        for file in callback_dir.glob("*.json"):
            file.unlink()
