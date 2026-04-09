import sys
import yaml
import time
import argparse
import subprocess
from pathlib import Path
from loguru import logger

import mobile_world.runtime.utils.helpers as helpers_module
import mobile_world.runtime.controller as controller_module
import mobile_world.runtime.setup.contacts as contacts_module

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.setup.contacts import ContactsSetup
from mobile_world.runtime.utils.helpers import AdbResponse

PROJECT_ROOT = Path(__file__).parents[4]
YAML_PATH = Path(__file__).parents[2] / "user_profile/user.yaml"

def execute_docker_adb(cmd: str, container: str) -> AdbResponse:
    if cmd.strip().startswith("adb "):
        cmd = cmd.strip()[4:]
    
    full_cmd = f"docker exec {container} adb {cmd}"
    # Debug log already here, will show exact command
    logger.debug(f"[CMD] {full_cmd}")
    
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return AdbResponse(
        success=(res.returncode == 0),
        output=res.stdout.strip(),
        return_code=res.returncode,
        command=full_cmd,
        error=res.stderr
    )

def get_contacts_config(yaml_data: dict) -> dict:
    if "environment_init_state" in yaml_data:
        return yaml_data["environment_init_state"].get("app_contacts", {})
    if "user_profile" in yaml_data:
        return yaml_data.get("user_profile", {}).get("environment_init_state", {}).get("app_contacts", {})
    return {}

def verify_all_contacts(device: str, expected_list: list) -> bool:
    cmd = f"adb -s {device} shell content query --uri content://com.android.contacts/data --projection data1:mimetype"
    res = helpers_module.execute_adb(cmd, output=False)
    
    if not res.success:
        logger.error(f"Failed to query Contacts DB: {res.error}")
        return False

    db_content = res.output
    all_found = True
    
    for contact in expected_list:
        name = str(contact.get("name", "")).strip()
        phone = str(contact.get("phone", "")).strip()
        
        if name and f"data1={name}" in db_content:
            logger.info(f"✓ Found Name: {name}")
        else:
            logger.error(f"✗ Missing Name: {name}")
            all_found = False

        if phone:
            # Simple check, real phone normalization is complex but string match is enough for test
            if phone in db_content:
                logger.info(f"✓ Found Phone: {phone}")
            else:
                logger.error(f"✗ Missing Phone: {phone}")
                all_found = False
            
    if not all_found:
        logger.warning(f"DB Dump (Partial): {db_content.replace('\n', ' ')[:500]}...")

    return all_found

def run_test(device: str, container: str, cleanup: bool) -> bool:
    if not YAML_PATH.exists():
        logger.error(f"Config not found: {YAML_PATH}")
        return False

    data = yaml.safe_load(YAML_PATH.read_text(encoding='utf-8'))
    config = get_contacts_config(data)
    
    if not config or "list" not in config:
        logger.error("No valid contacts config found")
        return False

    original_exec = helpers_module.execute_adb
    patch_func = (lambda cmd, output=True, root_required=False: execute_docker_adb(cmd, container)) if container else original_exec
    
    for mod in [helpers_module, controller_module, contacts_module]:
        if hasattr(mod, 'execute_adb'): mod.execute_adb = patch_func

    try:
        logger.info(f"Testing on {device} (Container: {container or 'Local'})...")
        controller = AndroidController(device=device)
        injector = ContactsSetup(controller)
        
        logger.info(">>> Step 1: Injecting contacts...")
        if not injector.setup(config):
            logger.error("Setup failed")
            return False

        logger.info(">>> Step 2: Waiting 60s for Manual VNC Inspection...")
        logger.info("    (Go check the Contacts app now!)")
        time.sleep(60) 

        logger.info(">>> Step 3: Verifying contacts via ADB...")
        success = verify_all_contacts(device, config["list"])
        logger.info(f"VERIFICATION RESULT: {'PASSED' if success else 'FAILED'}")
        
        if cleanup and success:
            logger.info(">>> Step 4: Cleaning up...")
            for contact in config["list"]:
                name = str(contact.get("name", "")).strip()
                if not name: continue
                
                safe_name = name.replace("'", r"\'")
                cmd = f"adb -s {device} shell content delete --uri content://com.android.contacts/raw_contacts --where \"display_name='{safe_name}'\""
                helpers_module.execute_adb(cmd, output=False)
            logger.info("Cleanup completed")
        
        return success

    except Exception as e:
        logger.exception(f"Crashed: {e}")
        return False
    finally:
        for mod in [helpers_module, controller_module, contacts_module]:
            if hasattr(mod, 'execute_adb'): mod.execute_adb = original_exec

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", default="emulator-5554")
    parser.add_argument("-c", "--container")
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()
    
    sys.exit(0 if run_test(args.device, args.container, not args.no_cleanup) else 1)