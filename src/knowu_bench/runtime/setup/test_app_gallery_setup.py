import sys
import yaml
import time
import argparse
import subprocess
from pathlib import Path
from loguru import logger

import knowu_bench.runtime.utils.helpers as helpers_module
import knowu_bench.runtime.controller as controller_module
# Assumes GallerySetup is in knowu_bench.runtime.setup.gallery
import knowu_bench.runtime.setup.gallery as gallery_module

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.setup.gallery import GallerySetup
from knowu_bench.runtime.utils.helpers import AdbResponse

PROJECT_ROOT = Path(__file__).parents[4]
YAML_PATH = Path(__file__).parents[2] / "user_profile/user.yaml"

def execute_docker_adb(cmd: str, container: str) -> AdbResponse:
    if cmd.strip().startswith("adb "):
        cmd = cmd.strip()[4:]
    
    full_cmd = f"docker exec {container} adb {cmd}"
    logger.debug(f"[CMD] {full_cmd}")
    
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    
    return AdbResponse(
        success=(res.returncode == 0),
        output=res.stdout.strip(),
        return_code=res.returncode,
        command=full_cmd,
        error=res.stderr
    )

def get_gallery_config(yaml_data: dict) -> dict:
    if "environment_init_state" in yaml_data:
        return yaml_data["environment_init_state"].get("app_gallery", {})
    if "user_profile" in yaml_data:
        return yaml_data.get("user_profile", {}).get("environment_init_state", {}).get("app_gallery", {})
    return {}

def verify_gallery_files(device: str, albums: list) -> bool:
    all_found = True
    
    for album in albums:
        album_name = album.get("name", "")
        # Determine expected remote path based on Setup logic
        if album_name == "Camera":
            base_path = "/sdcard/DCIM/Camera"
        elif album_name == "Screenshots":
            base_path = "/sdcard/Pictures/Screenshots"
        else:
            base_path = f"/sdcard/Pictures/{album_name}"

        for content in album.get("content", []):
            if isinstance(content, dict):
                filename = content.get("filename")
                if not filename: continue
                
                full_path = f"{base_path}/{filename}"
                # Check if file exists using 'ls'
                cmd = f'adb -s {device} shell "ls \'{full_path}\'"'
                res = helpers_module.execute_adb(cmd, output=True)
                
                if res.success and filename in res.output:
                    logger.info(f"✓ Found: {full_path}")
                else:
                    logger.error(f"✗ Missing: {full_path}")
                    all_found = False
                    
    return all_found

def run_test(device: str, container: str, cleanup: bool) -> bool:
    if not YAML_PATH.exists():
        logger.error("Config not found")
        return False
        
    data = yaml.safe_load(YAML_PATH.read_text(encoding='utf-8'))
    config = get_gallery_config(data)
    
    if not config or "albums" not in config:
        logger.error("No valid gallery config found")
        return False

    original_exec = helpers_module.execute_adb
    patch_func = (lambda cmd, output=True, root_required=False: execute_docker_adb(cmd, container)) if container else original_exec
    
    for mod in [helpers_module, controller_module, gallery_module]:
        if hasattr(mod, 'execute_adb'): mod.execute_adb = patch_func

    try:
        logger.info(f"Testing on {device}...")
        controller = AndroidController(device=device)
        injector = GallerySetup(controller)
        
        logger.info(">>> Step 1: Injecting gallery files...")
        if not injector.setup(config):
            logger.error("Setup failed")
            return False
        
        logger.info(">>> Step 2: Waiting 60s for Media Scanner...")
        time.sleep(60)
        
        logger.info(">>> Step 3: Verifying files via ADB...")
        success = verify_gallery_files(device, config["albums"])
        logger.info(f"RESULT: {'PASSED' if success else 'FAILED'}")
        
        if cleanup and success:
            logger.info("Cleaning up...")
            for album in config["albums"]:
                album_name = album.get("name", "")
                if album_name == "Camera":
                    base_path = "/sdcard/DCIM/Camera"
                elif album_name == "Screenshots":
                    base_path = "/sdcard/Pictures/Screenshots"
                else:
                    base_path = f"/sdcard/Pictures/{album_name}"
                
                # Delete files
                for content in album.get("content", []):
                    fname = content.get("filename") if isinstance(content, dict) else None
                    if fname:
                        cmd = f'adb -s {device} shell "rm \'{base_path}/{fname}\'"'
                        helpers_module.execute_adb(cmd, output=False)
            logger.info("Cleanup done")
        return success

    except Exception as e:
        logger.exception(e)
        return False
    finally:
        for mod in [helpers_module, controller_module, gallery_module]:
            if hasattr(mod, 'execute_adb'): mod.execute_adb = original_exec

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", default="emulator-5554")
    parser.add_argument("-c", "--container")
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()
    
    sys.exit(0 if run_test(args.device, args.container, not args.no_cleanup) else 1)