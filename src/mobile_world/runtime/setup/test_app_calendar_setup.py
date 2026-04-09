import sys
import yaml
import time
import argparse
import subprocess
import json
from datetime import datetime
from pathlib import Path
from loguru import logger

import mobile_world.runtime.utils.helpers as helpers_module
import mobile_world.runtime.controller as controller_module
# Assumes your CalendarSetup is in mobile_world.runtime.setup.calendar
import mobile_world.runtime.setup.calendar as calendar_module

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.setup.calendar import CalendarSetup
from mobile_world.runtime.utils.helpers import AdbResponse

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

def get_calendar_config(yaml_data: dict) -> dict:
    if "environment_init_state" in yaml_data:
        return yaml_data["environment_init_state"].get("app_calendar", {})
    if "user_profile" in yaml_data:
        return yaml_data.get("user_profile", {}).get("environment_init_state", {}).get("app_calendar", {})
    return {}

def verify_calendar_events(device: str, expected_events: list) -> bool:
    db_path = "/data/user/0/org.fossify.calendar/databases/events.db"
    cmd = f'adb -s {device} shell "sqlite3 -json {db_path} \\"SELECT title, location, description FROM events\\""'
    
    res = helpers_module.execute_adb(cmd, output=False, root_required=True)
    
    if not res.success:
        logger.error(f"Failed to query Calendar DB: {res.error}")
        return False

    try:
        db_events = json.loads(res.output)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse DB output: {res.output}")
        return False

    all_found = True
    for expected in expected_events:
        title = expected.get("title", "")
        if not title: continue
        
        found = False
        for db_event in db_events:
            if title in db_event.get("title", ""):
                found = True
                logger.info(f"✓ Found Event: {title}")
                break
        
        if not found:
            logger.error(f"✗ Missing Event: {title}")
            all_found = False

    return all_found

def run_test(device: str, container: str, cleanup: bool) -> bool:
    if not YAML_PATH.exists():
        logger.error(f"Config not found: {YAML_PATH}")
        return False

    data = yaml.safe_load(YAML_PATH.read_text(encoding='utf-8'))
    config = get_calendar_config(data)
    
    if not config or "events" not in config:
        logger.error("No valid calendar config found")
        return False

    original_exec = helpers_module.execute_adb
    patch_func = (lambda cmd, output=True, root_required=False: execute_docker_adb(cmd, container)) if container else original_exec
    
    for mod in [helpers_module, controller_module, calendar_module]:
        if hasattr(mod, 'execute_adb'): mod.execute_adb = patch_func

    try:
        logger.info(f"Testing on {device} (Container: {container or 'Local'})...")
        controller = AndroidController(device=device)
        injector = CalendarSetup(controller)
        
        logger.info(">>> Step 1: Injecting calendar events...")
        if not injector.setup(config):
            logger.error("Setup failed")
            return False

        logger.info(">>> Step 2: Waiting 60s for DB sync...")
        time.sleep(60)

        logger.info(">>> Step 3: Verifying events via SQLite...")
        success = verify_calendar_events(device, config["events"])
        logger.info(f"VERIFICATION RESULT: {'PASSED' if success else 'FAILED'}")
        
        if cleanup and success:
            logger.info(">>> Step 4: Cleaning up...")
            db_path = "/data/user/0/org.fossify.calendar/databases/events.db"
            for event in config["events"]:
                title = event.get("title", "").replace("'", "''")
                if not title: continue
                
                del_sql = f"DELETE FROM events WHERE title='{title}';"
                cmd = f'adb -s {device} shell "sqlite3 {db_path} \\"{del_sql}\\""'
                helpers_module.execute_adb(cmd, output=False, root_required=True)
            logger.info("Cleanup completed")
        
        return success

    except Exception as e:
        logger.exception(f"Crashed: {e}")
        return False
    finally:
        for mod in [helpers_module, controller_module, calendar_module]:
            if hasattr(mod, 'execute_adb'): mod.execute_adb = original_exec

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", default="emulator-5554")
    parser.add_argument("-c", "--container")
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()
    
    sys.exit(0 if run_test(args.device, args.container, not args.no_cleanup) else 1)