import sys
import yaml
import argparse
import subprocess
from pathlib import Path
from loguru import logger

import mobile_world.runtime.utils.helpers as helpers_module
import mobile_world.runtime.controller as controller_module
import mobile_world.runtime.setup.messages as messages_module

from mobile_world.runtime.controller import AndroidController
from mobile_world.runtime.setup.messages import MessagesSetup
from mobile_world.runtime.utils.helpers import AdbResponse

PROJECT_ROOT = Path(__file__).parents[4]
YAML_PATH = Path(__file__).parents[2] / "user_profile/user.yaml"

def execute_docker_adb(cmd: str, container: str) -> AdbResponse:
    if cmd.strip().startswith("adb "):
        cmd = cmd.strip()[4:]
    
    full_cmd = f"docker exec {container} adb {cmd}"
    logger.debug(f"Docker Exec: {full_cmd}")
    
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return AdbResponse(
        success=(res.returncode == 0),
        output=res.stdout.strip(),
        return_code=res.returncode,
        command=full_cmd,
        error=res.stderr
    )

def verify_all_messages(device, expected_threads):
    # 查询 Address 和 Body
    cmd = f"adb -s {device} shell 'content query --uri content://sms/inbox --projection address:body'"
    
    res = helpers_module.execute_adb(cmd, output=False)
    
    if not res.success:
        logger.error(f"Failed to query SMS DB: {res.error}")
        return False

    db_content = res.output
    # 简单的清理换行，方便匹配
    clean_db_content = db_content.replace("\r\n", " ").replace("\n", " ")
    
    all_found = True
    for thread in expected_threads:
        sender = str(thread.get("sender", ""))
        text = str(thread.get("text", ""))
        body_frag = text[:10]
        
        if sender in db_content and body_frag in db_content:
            logger.info(f"✓ Found: {sender}")
        else:
            logger.error(f"✗ Missing: {sender}")
            logger.warning(f"  - DB Dump (Partial): {clean_db_content[:500]}...")
            all_found = False
            
    return all_found

def get_messages_config(yaml_data):
    if "app_messages" in yaml_data: return yaml_data["app_messages"]
    if "environment_init_state" in yaml_data:
        return yaml_data.get("environment_init_state", {}).get("app_messages", {})
    if "user_profile" in yaml_data:
        return yaml_data.get("user_profile", {}).get("environment_init_state", {}).get("app_messages", {})
    return {}

def run_test(device, container, cleanup):
    if not YAML_PATH.exists(): return logger.error(f"Config not found: {YAML_PATH}") or False
    data = yaml.safe_load(YAML_PATH.read_text(encoding='utf-8'))
    config = get_messages_config(data)
    
    if not config or "threads" not in config:
        return logger.error("No valid config found") or False

    original_exec = helpers_module.execute_adb
    # 注入 Docker 执行逻辑
    patch_func = (lambda cmd, output=True, root_required=False: execute_docker_adb(cmd, container)) if container else original_exec
    
    for mod in [helpers_module, controller_module, messages_module]:
        if hasattr(mod, 'execute_adb'): mod.execute_adb = patch_func

    try:
        logger.info(f"Testing on {device} (Container: {container})...")
        
        controller = AndroidController(device=device)
        injector = MessagesSetup(controller)
        
        logger.info(">>> Step 1: Injecting messages...")
        if not injector.setup(config):
            logger.error("Setup reported failure")
            return False

        logger.info(">>> Step 2: Verifying messages...")
        success = verify_all_messages(device, config["threads"])
        
        logger.info(f"VERIFICATION RESULT: {'PASSED' if success else 'FAILED'}")
        
        if cleanup and success:
            logger.info(">>> Step 3: Cleaning up injected messages...")
            for thread in config["threads"]:
                sender = str(thread.get("sender"))
                
                safe_sender = sender.replace("'", r"\'")

                cmd = f"adb -s {device} shell \"content delete --uri content://sms/inbox --where \\\"address='{safe_sender}'\\\"\""
                
                logger.debug(f"Deleting [{sender}]: {cmd}")
                helpers_module.execute_adb(cmd, output=False)
            logger.info("Cleanup completed.")
        
        return success

    except Exception as e:
        logger.exception(f"Crashed: {e}")
        return False
    finally:
        for mod in [helpers_module, controller_module, messages_module]:
            if hasattr(mod, 'execute_adb'): mod.execute_adb = original_exec

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", default="emulator-5554")
    parser.add_argument("-c", "--container")
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()
    
    sys.exit(0 if run_test(args.device, args.container, not args.no_cleanup) else 1)