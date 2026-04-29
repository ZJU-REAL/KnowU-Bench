import sys
import yaml
import time
import argparse
import subprocess
from pathlib import Path
from loguru import logger

import knowu_bench.runtime.utils.helpers as helpers_module
import knowu_bench.runtime.controller as controller_module
import knowu_bench.runtime.setup.clock as clock_module
from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.setup.clock import ClockSetup
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

def get_clock_config(yaml_data: dict) -> dict:
    if "environment_init_state" in yaml_data:
        return yaml_data["environment_init_state"].get("app_clock", {})
    if "user_profile" in yaml_data:
        return yaml_data.get("user_profile", {}).get("environment_init_state", {}).get("app_clock", {})
    return {}

def calculate_day_mask(days: list) -> int:
    # FIX: Correct mapping to match DeskClock/Setup code (Mon=1)
    map_ = {
        "mon": 1, "tue": 2, "wed": 4, "thu": 8, "fri": 16, "sat": 32, "sun": 64
    }
    mask = 0
    for day in days:
        k = str(day).lower()[:3]
        if k in map_:
            mask |= map_[k]
    return mask

def verify_alarms(device: str, expected_alarms: list) -> bool:
    db_path = "/data/user_de/0/com.google.android.deskclock/databases/alarms.db"
    cmd = f'adb -s {device} shell "sqlite3 {db_path} \\"SELECT hour, minutes, label, daysofweek, vibrate FROM alarm_templates\\""'
    
    res = helpers_module.execute_adb(cmd, output=False, root_required=True)
    if not res.success:
        logger.error(f"Failed to query Clock DB: {res.error}")
        return False

    db_output = res.output.strip()
    if not db_output:
        return len(expected_alarms) == 0

    all_found = True
    for expected in expected_alarms:
        time_str = expected.get("time", "")
        label = expected.get("label", "")
        exp_mask = calculate_day_mask(expected.get("repeat", []))
        exp_vibrate = 1 if expected.get("vibrate", True) else 0
        
        try:
            exp_h, exp_m = map(int, time_str.split(":"))
        except ValueError:
            continue
        
        found = False
        for line in db_output.splitlines():
            parts = line.split("|")
            if len(parts) < 5: continue
            
            try:
                d_h, d_m = int(parts[0]), int(parts[1])
                d_lbl = parts[2]
                d_days = int(parts[3])
                d_vib = int(parts[4])
                
                if d_h == exp_h and d_m == exp_m:
                    # Loose label match, strict settings match
                    if label in d_lbl and d_days == exp_mask and d_vib == exp_vibrate:
                        found = True
                        logger.info(f"✓ Found: {time_str} days={d_days} vib={d_vib}")
                        break
            except ValueError:
                continue
        
        if not found:
            logger.error(f"✗ Missing/Mismatch: {time_str} mask={exp_mask} vib={exp_vibrate}")
            all_found = False

    return all_found

def run_test(device: str, container: str, cleanup: bool) -> bool:
    if not YAML_PATH.exists():
        logger.error("Config not found")
        return False
        
    data = yaml.safe_load(YAML_PATH.read_text(encoding='utf-8'))
    config = get_clock_config(data)
    
    if not config or "alarms" not in config:
        logger.error("No valid config found")
        return False

    original_exec = helpers_module.execute_adb
    patch_func = (lambda cmd, output=True, root_required=False: execute_docker_adb(cmd, container)) if container else original_exec
    
    for mod in [helpers_module, controller_module, clock_module]:
        if hasattr(mod, 'execute_adb'): mod.execute_adb = patch_func

    try:
        logger.info(f"Testing on {device}...")
        controller = AndroidController(device=device)
        injector = ClockSetup(controller)
        
        logger.info(">>> Step 1: Injecting alarms...")
        if not injector.setup(config):
            logger.error("Setup failed")
            return False
        
        logger.info(">>> Step 2: Waiting 10s for DB sync...")
        time.sleep(10)
        
        logger.info(">>> Step 3: Verifying alarms via ADB...")
        success = verify_alarms(device, config["alarms"])
        logger.info(f"RESULT: {'PASSED' if success else 'FAILED'}")
        
        if cleanup and success:
            logger.info("Cleaning up...")
            db_path = "/data/user_de/0/com.google.android.deskclock/databases/alarms.db"
            for alarm in config["alarms"]:
                try:
                    h, m = map(int, alarm.get("time").split(":"))
                    cmd = f'adb -s {device} shell "sqlite3 {db_path} \\"DELETE FROM alarm_templates WHERE hour={h} AND minutes={m};\\""'
                    helpers_module.execute_adb(cmd, output=False, root_required=True)
                except: pass
            logger.info("Cleanup done")
        return success

    except Exception as e:
        logger.exception(e)
        return False
    finally:
        for mod in [helpers_module, controller_module, clock_module]:
            if hasattr(mod, 'execute_adb'): mod.execute_adb = original_exec

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", default="emulator-5554")
    parser.add_argument("-c", "--container")
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()
    
    sys.exit(0 if run_test(args.device, args.container, not args.no_cleanup) else 1)