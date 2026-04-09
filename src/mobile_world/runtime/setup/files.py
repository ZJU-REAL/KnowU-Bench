import os
import shlex
from loguru import logger
from mobile_world.runtime.utils.helpers import execute_adb
from .base import BaseSetup

class FilesSetup(BaseSetup):
    def setup(self, files_config: dict) -> bool:
        file_list = files_config.get("files", [])
        if not file_list and "directories" in files_config:
            for d in files_config["directories"]:
                for f in d.get("content", []):
                    file_list.append({"path": f"{d.get('path', '')}/{f}"})

        if not file_list: return True

        device = self.controller.device
        success_count = 0

        for item in file_list:
            path = item.get("path", "").strip().lstrip("/")
            if not path: continue

            remote_path = f"/sdcard/{path}"
            safe_path = shlex.quote(remote_path)
            
            execute_adb(f'adb -s {device} shell mkdir -p {shlex.quote(os.path.dirname(remote_path))}', output=False)

            local_src = item.get("source")
            success = False
            
            try:
                if local_src and os.path.exists(local_src):
                    success = execute_adb(f'adb -s {device} push {shlex.quote(local_src)} {safe_path}', output=False).success
                else:
                    success = execute_adb(f'adb -s {device} shell touch {safe_path}', output=False).success

                if success:
                    execute_adb(f'adb -s {device} shell chmod 644 {safe_path}', output=False)
                    
                    scan_cmd = (f'adb -s {device} shell content call '
                                f'--uri content://media/scanner --method scan_file '
                                f'--extra _data:s:"{remote_path}"')
                    execute_adb(scan_cmd, output=False)

                    bc_cmd = f'adb -s {device} shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote_path}'
                    execute_adb(bc_cmd, output=False)
                    
                    success_count += 1
            except Exception as e:
                logger.error(f"Error {path}: {e}")

        if success_count > 0:
            for pkg in ["com.android.documentsui", "com.google.android.documentsui", "com.android.providers.downloads"]:
                execute_adb(f'adb -s {device} shell am force-stop {pkg}', output=False)

        logger.info(f"Processed {success_count} files")
        return success_count > 0