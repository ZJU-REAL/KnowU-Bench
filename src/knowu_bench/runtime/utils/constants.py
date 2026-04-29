import os
from pathlib import Path

ARTIFACTS_ROOT = Path(os.getenv("ARTIFACTS_ROOT", "./artifacts")).resolve()
ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)


def device_dir(artifacts_root: Path, device: str) -> Path:
    p = artifacts_root / device
    p.mkdir(parents=True, exist_ok=True)
    return p
