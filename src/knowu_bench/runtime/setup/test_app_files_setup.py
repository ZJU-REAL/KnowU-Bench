"""
Test script for independent FilesSetup injection
"""
import sys
import yaml
import argparse
import subprocess
from pathlib import Path
from loguru import logger

import knowu_bench.runtime.utils.helpers as helpers_module
import knowu_bench.runtime.controller as controller_module
import knowu_bench.runtime.setup.files as files_module
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.setup.files import FilesSetup
from knowu_bench.runtime.utils.helpers import AdbResponse

PROJECT_ROOT = Path(__file__).parents[4]
YAML_PATH = Path(__file__).parents[2] / "user_profile/user.yaml"

def execute_docker_adb(cmd: str, container: str) -> AdbResponse:
    cmd = cmd[4:] if cmd.startswith("adb ") else cmd
    full_cmd = f"docker exec {container} adb {cmd}"
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return AdbResponse(
        success=(res.returncode == 0),
        output=res.stdout.strip(),
        return_code=res.returncode,
        command=full_cmd,
        error=res.stderr
    )

def get_config_and_temps():
    if not YAML_PATH.exists(): return {}, []
    data = yaml.safe_load(YAML_PATH.read_text(encoding='utf-8'))
    config = data.get("environment_init_state", {}).get("app_files") or \
             data.get("user_profile", {}).get("environment_init_state", {}).get("app_files", {})
    
    if not config.get("files") and "directories" in config:
        config["files"] = [{"source": None, "path": f"{d['path']}/{f}"} 
                          for d in config["directories"] for f in d.get("content", [])]

    temp_files = []
    for item in config.get("files", []):
        if src := item.get("source"):
            p = PROJECT_ROOT / src
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
                temp_files.append(p)
    return config, temp_files

def run_test(device, container, cleanup):
    config, temps = get_config_and_temps()
    if not config: return logger.error("No config found") or False

    original_exec = helpers_module.execute_adb
    patch_func = (lambda cmd, output=True, root_required=False: execute_docker_adb(cmd, container)) if container else original_exec
    
    for mod in [helpers_module, controller_module, files_module]:
        if hasattr(mod, 'execute_adb'): mod.execute_adb = patch_func

    try:
        logger.info(f"Testing on {device} (Docker: {container})...")
        injector = FilesSetup(AndroidController(device=device))
        if not injector.setup(config): 
            logger.error("Setup failed"); return False

        logger.info("Verifying files...")
        success = True
        for item in config["files"]:
            path = item.get("path", "").lstrip("/")
            check = helpers_module.execute_adb(f'adb -s {device} shell ls -l "/sdcard/{path}"', output=False)
            
            if check.success and "No such file" not in check.output:
                logger.info(f"✓ Found: {path}")
            else:
                logger.error(f"✗ Missing: {path}")
                success = False
        
        if success:
            logger.info("\n" + "="*50)
            logger.info(">>> Injection Successful! Check Android Emulator now.")
            logger.info(">>> Press [ENTER] to clean up and exit...")
            logger.info("="*50 + "\n")
            input()
        
        if cleanup and success:
            for item in config["files"]:
                path = item.get("path", "").lstrip("/")
                helpers_module.execute_adb(f'adb -s {device} shell rm -f "/sdcard/{path}"', output=False)
        return success

    except Exception as e:
        logger.exception(f"Crashed: {e}")
        return False
    finally:
        for mod in [helpers_module, controller_module, files_module]:
            if hasattr(mod, 'execute_adb'): mod.execute_adb = original_exec
        for p in temps: p.unlink(missing_ok=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", default="emulator-5554")
    parser.add_argument("-c", "--container")
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()
    sys.exit(0 if run_test(args.device, args.container, not args.no_cleanup) else 1)