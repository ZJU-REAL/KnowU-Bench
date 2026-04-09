import os
import shlex
from loguru import logger
from mobile_world.runtime.utils.helpers import execute_adb
from .base import BaseSetup

class GallerySetup(BaseSetup):
    """Handles data injection for Gallery app via ADB Push"""

    def setup(self, gallery_config: dict) -> bool:
        if not isinstance(gallery_config, dict) or "albums" not in gallery_config:
            logger.error("Invalid gallery configuration")
            return False

        albums = gallery_config["albums"]
        success_count = 0

        for album in albums:
            album_name = album.get("name", "Unknown")
            
            # 1. Determine remote directory based on album name
            if album_name == "Camera":
                remote_dir = "/sdcard/DCIM/Camera"
            elif album_name == "Screenshots":
                remote_dir = "/sdcard/Pictures/Screenshots"
            else:
                remote_dir = f"/sdcard/Pictures/{album_name}"
            
            # Create remote directory
            execute_adb(f'adb -s {self.controller.device} shell mkdir -p {shlex.quote(remote_dir)}', output=False)

            # 2. Process content items
            content_list = album.get("content", [])
            for item in content_list:
                # Handle dictionary format from config
                if isinstance(item, dict):
                    filename = item.get("filename")
                    local_source = item.get("source")
                else:
                    logger.warning(f"Skipping invalid item format: {item}")
                    continue

                if not filename or not local_source:
                    continue

                # Check if local file exists
                if not os.path.exists(local_source):
                    logger.error(f"Local source file not found: {local_source}")
                    continue

                remote_path = f"{remote_dir}/{filename}"
                
                # 3. Push file to device (Use quotes to handle spaces)
                push_cmd = f'adb -s {self.controller.device} push "{local_source}" "{remote_path}"'
                res = execute_adb(push_cmd, output=True)
                
                if res.success:
                    self._trigger_media_scan(remote_path)
                    success_count += 1
                    logger.debug(f"Pushed {filename} to {remote_dir}")
                else:
                    logger.error(f"Failed to push {filename}: {res.error}")
        
        logger.info(f"Successfully processed {success_count} gallery items")
        return success_count > 0

    def _trigger_media_scan(self, remote_path: str):
        """Forces Android MediaScanner to index the new file so it appears in Gallery app"""
        cmd = (
            f'adb -s {self.controller.device} shell am broadcast '
            f'-a android.intent.action.MEDIA_SCANNER_SCAN_FILE '
            f'-d "file://{remote_path}"'
        )
        execute_adb(cmd, output=False)