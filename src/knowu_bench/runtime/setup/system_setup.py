import os
import re
import time
import shlex  # 引入 shlex 用于安全的 Host Shell 转义
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb, execute_root_sql


class SystemSetup:
    """System information setup - handles data injection for all Android system apps"""

    # System app configuration mapping
    SYSTEM_APPS = {
        "app_contacts": "contacts",
        "app_messages": "messages",
        "app_calendar": "calendar",
        "app_files": "files",
        "app_clock": "clock",
        "app_settings": "settings",
        "app_gallery": "gallery",
    }

    def __init__(self, controller: AndroidController):
        """
        Initialize system setup

        Args:
            controller: AndroidController instance
        """
        self.controller = controller

    def inject_system_data(self, env_state: dict) -> dict[str, bool]:
        """
        General system data injection entry point
        """
        results = {}

        # Inject each system app in order
        for app_key, app_type in self.SYSTEM_APPS.items():
            if app_key in env_state:
                logger.info(f"Starting to inject system app {app_key} ({app_type})...")
                try:
                    inject_func = getattr(self, f"_inject_{app_type}", None)
                    if inject_func:
                        result = inject_func(env_state[app_key])
                        results[app_key] = result
                        if result:
                            logger.info(f"✓ {app_key} injection successful")
                        else:
                            logger.warning(f"✗ {app_key} injection failed or partially failed")
                    else:
                        logger.warning(f"Injection function not found for {app_type}")
                        results[app_key] = False
                except Exception as e:
                    logger.error(f"✗ Error occurred while injecting {app_key}: {e}")
                    results[app_key] = False
            else:
                logger.debug(f"Skipping {app_key} (not in configuration)")
                results[app_key] = None

        return results

    def _trigger_media_scan(self, file_path: str):
        """
        Helper method to trigger MediaScanner for a specific file.
        This ensures the file appears in Android UI (Files, Gallery) immediately.
        """
        try:
            # Use 'am broadcast' to notify MediaScanner
            safe_path = shlex.quote(f"file://{file_path}")
            scan_cmd = (
                f'adb -s {self.controller.device} shell am broadcast '
                f'-a android.intent.action.MEDIA_SCANNER_SCAN_FILE '
                f'-d {safe_path}'
            )
            execute_adb(scan_cmd, output=False)
            logger.debug(f"Triggered media scan for: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to trigger media scan for {file_path}: {e}")

    def _escape_arg_for_android(self, key: str, value: str) -> str:
        """
        [核心修复] 构造 Android Shell 安全的参数字符串。
        
        原理：
        1. Android Shell 需要双引号包裹含有空格/括号的参数： "key:type:Value (Text)"
        2. 双引号内部需要转义特殊字符： " \ ` $
        3. 最后通过 shlex.quote 返回给 Host Shell 使用
        
        Args:
            key: 参数键和类型 (例如 'address:s')
            value: 参数值 (例如 'Package (SF123)')
            
        Returns:
            经过双重转义的字符串，可直接用于 execute_adb
        """
        if value is None:
            value = ""
            
        # 1. Android Shell 层面的转义
        # 在双引号内部，只有 4 个字符需要反斜杠转义：\ " $ `
        safe_val = value.replace('\\', '\\\\') \
                        .replace('"', '\\"') \
                        .replace('`', '\\`') \
                        .replace('$', '\\$')
        
        # 2. 构造 Android 看起来的参数： "key:type:SafeValue"
        # 这里的双引号是给 Android Shell 吃的，用来保护内部的空格、括号、单引号
        android_arg = f'"{key}:{safe_val}"'
        
        # 3. Host Shell 层面的转义
        # 使用 shlex.quote 保护上述字符串，使其能完整通过 docker/subprocess 传递
        host_arg = shlex.quote(android_arg)
        
        return host_arg

    def _inject_contacts(self, contacts_config: dict) -> bool:
        """Inject contacts data"""
        if not isinstance(contacts_config, dict) or "list" not in contacts_config:
            logger.error("Invalid contacts configuration")
            return False

        contact_list = contacts_config["list"]
        if not contact_list:
            return True

        success_count = 0
        db_path = "/data/data/com.android.providers.contacts/databases/contacts2.db"

        for idx, contact in enumerate(contact_list, 1):
            name = contact.get("name", "").strip()
            phone = contact.get("phone", "").strip()
            
            if not name or not phone:
                continue

            try:
                # Basic check if exists
                # SQL injection risk handled minimally here for '
                safe_name = name.replace("'", "''")
                check_sql = f"SELECT _id FROM raw_contacts WHERE display_name='{safe_name}' LIMIT 1;"
                existing = execute_root_sql(db_path, check_sql)
                if existing:
                    success_count += 1
                    continue

                # Get mimetype IDs
                name_mt_sql = "SELECT _id FROM mimetypes WHERE mimetype='vnd.android.cursor.item/name';"
                phone_mt_sql = "SELECT _id FROM mimetypes WHERE mimetype='vnd.android.cursor.item/phone_v2';"
                
                name_mt_id = execute_root_sql(db_path, name_mt_sql)
                phone_mt_id = execute_root_sql(db_path, phone_mt_sql)

                if not name_mt_id or not phone_mt_id:
                    logger.warning("Could not retrieve mimetype IDs for contacts injection")
                    continue

                # Insert Raw Contact
                insert_raw = "INSERT INTO raw_contacts (account_name, account_type, display_name) VALUES ('', '', '{}');".format(safe_name)
                execute_root_sql(db_path, insert_raw)
                
                # Get the ID we just inserted
                raw_id_res = execute_root_sql(db_path, f"SELECT _id FROM raw_contacts WHERE display_name='{safe_name}' ORDER BY _id DESC LIMIT 1;")
                if not raw_id_res: continue
                raw_id = raw_id_res.strip()

                # Insert Data (Name and Phone)
                execute_root_sql(db_path, f"INSERT INTO data (raw_contact_id, mimetype_id, data1) VALUES ({raw_id}, {name_mt_id.strip()}, '{safe_name}');")
                execute_root_sql(db_path, f"INSERT INTO data (raw_contact_id, mimetype_id, data1, data2) VALUES ({raw_id}, {phone_mt_id.strip()}, '{phone}', 2);")

                success_count += 1
            except Exception as e:
                logger.error(f"Failed to inject contact {name}: {e}")

        logger.info(f"Successfully processed {success_count} contacts")
        return success_count > 0

    def _get_thread_id(self, sender: str) -> str | None:
        """
        尝试根据发送者地址获取现有的 thread_id
        """
        try:
            # SQL查询中的转义：将单引号替换为两个单引号
            sql_safe_sender = sender.replace("'", "''")
            # ADB Shell参数的转义：address='Name' 整个作为一个参数
            # 使用 shlex.quote 包裹整个 where 子句
            where_clause = shlex.quote(f"address='{sql_safe_sender}'")
            
            cmd = (
                f'adb -s {self.controller.device} shell content query '
                f'--uri content://sms '
                f'--projection thread_id '
                f'--where {where_clause} '
                f'--limit 1'
            )
            result = execute_adb(cmd, output=False)
            
            if result.success and result.output:
                # 输出通常类似: Row: 0 thread_id=5
                match = re.search(r'thread_id=(\d+)', result.output)
                if match:
                    return match.group(1)
        except Exception as e:
            logger.warning(f"Failed to get thread_id for {sender}: {e}")
        return None

    def _inject_messages(self, messages_config: dict) -> bool:
        """Inject SMS/messages data"""
        if not isinstance(messages_config, dict) or "threads" not in messages_config:
            return False
            
        threads = messages_config["threads"]
        success_count = 0

        for thread in threads:
            sender = thread.get("sender", "").strip()
            text = thread.get("text", "").strip()
            read_status = thread.get("read", False)
            
            if not sender or not text: continue

            try:
                timestamp_ms = int(datetime.now().timestamp() * 1000)
                if thread.get("time") == "Yesterday":
                    timestamp_ms = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)

                read_val = 1 if read_status else 0
                
                # 1. 尝试获取 Thread ID (确保聚合)
                existing_thread_id = self._get_thread_id(sender)
                bind_thread_arg = ""
                if existing_thread_id:
                    bind_thread_arg = f"--bind thread_id:i:{existing_thread_id}"
                
                # 2. [核心修正] 使用专用的 Android 转义函数
                # 这会生成类似 '"address:s:Sarah Lin"' (带外部单引号保护) 的字符串
                bind_address = self._escape_arg_for_android("address:s", sender)
                bind_body = self._escape_arg_for_android("body:s", text)
                
                cmd = (
                    f'adb -s {self.controller.device} shell content insert '
                    f'--uri content://sms/inbox '
                    f'--bind {bind_address} '
                    f'--bind {bind_body} '
                    f'--bind date:j:{timestamp_ms} '
                    f'--bind read:i:{read_val} '
                    f'--bind type:i:1 '
                    f'{bind_thread_arg}'
                )
                
                result = execute_adb(cmd, output=False, root_required=True)
                if result.success:
                    success_count += 1
                else:
                    logger.warning(f"Failed to inject message from {sender}: {result.error}")
                    
            except Exception as e:
                logger.error(f"SMS injection error: {e}")

        logger.info(f"Successfully processed {success_count} messages")
        return success_count > 0

    def _inject_calendar(self, calendar_config: dict) -> bool:
        """Inject calendar events"""
        if not isinstance(calendar_config, dict) or "events" not in calendar_config:
            return False
            
        events = calendar_config["events"]
        success_count = 0
        base_date = datetime.now()

        for event in events:
            title = event.get("title", "")
            time_str = event.get("time", "")
            if not title or not time_str: continue

            try:
                start_dt = base_date
                end_dt = base_date + timedelta(hours=1)
                
                if "-" in time_str:
                    parts = time_str.split("-")
                    try:
                        s_h, s_m = map(int, parts[0].strip().split(":"))
                        e_h, e_m = map(int, parts[1].strip().split(":"))
                        start_dt = base_date.replace(hour=s_h, minute=s_m)
                        end_dt = base_date.replace(hour=e_h, minute=e_m)
                    except ValueError:
                        pass

                # [核心修正] 同样应用新的转义函数
                bind_title = self._escape_arg_for_android("title:s", title)
                bind_timezone = self._escape_arg_for_android("eventTimezone:s", "Asia/Shanghai")
                
                cmd = (
                    f'adb -s {self.controller.device} shell content insert '
                    f'--uri content://com.android.calendar/events '
                    f'--bind calendar_id:i:1 '
                    f'--bind {bind_title} '
                    f'--bind dtstart:j:{int(start_dt.timestamp() * 1000)} '
                    f'--bind dtend:j:{int(end_dt.timestamp() * 1000)} '
                    f'--bind {bind_timezone} '
                    f'--bind allDay:i:0'
                )
                if execute_adb(cmd, output=False, root_required=True).success:
                    success_count += 1
            except Exception as e:
                logger.error(f"Calendar injection error: {e}")

        logger.info(f"Successfully processed {success_count} events")
        return success_count > 0

    def _inject_files(self, files_config: dict) -> bool:
        """
        Inject file system structure (supports real file upload and placeholders)
        """
        file_list = files_config.get("files", [])
        
        if not file_list and "directories" in files_config:
            logger.info("Converting legacy directory config to file list...")
            for directory in files_config["directories"]:
                base_path = directory.get("path", "")
                for fname in directory.get("content", []):
                    file_list.append({"path": f"{base_path}/{fname}"})

        if not file_list:
            logger.warning("No files configured for injection")
            return True

        success_count = 0

        for item in file_list:
            target_path_relative = item.get("path", "").strip()
            if not target_path_relative:
                continue
                
            target_path_relative = target_path_relative.lstrip("/")
            full_remote_path = f"/sdcard/{target_path_relative}"
            remote_dir = os.path.dirname(full_remote_path)
            
            # 安全转义路径
            safe_remote_dir = shlex.quote(remote_dir)
            safe_full_remote_path = shlex.quote(full_remote_path)
            
            mkdir_cmd = f'adb -s {self.controller.device} shell mkdir -p {safe_remote_dir}'
            execute_adb(mkdir_cmd, output=False)
            
            local_source = item.get("source")
            
            try:
                if local_source:
                    if not os.path.exists(local_source):
                        logger.error(f"Local source file not found: {local_source}")
                        continue
                        
                    # push 命令本地路径需要本地 Shell 规则
                    safe_local_source = shlex.quote(local_source)
                    
                    push_cmd = f'adb -s {self.controller.device} push {safe_local_source} {safe_full_remote_path}'
                    result = execute_adb(push_cmd, output=False)
                    
                    if result.success:
                        logger.debug(f"Uploaded: {local_source} -> {full_remote_path}")
                        self._trigger_media_scan(full_remote_path)
                        success_count += 1
                    else:
                        logger.error(f"Failed to push file {local_source}: {result.error}")
                        
                else:
                    touch_cmd = f'adb -s {self.controller.device} shell touch {safe_full_remote_path}'
                    result = execute_adb(touch_cmd, output=False)
                    
                    if result.success:
                        logger.debug(f"Created placeholder: {full_remote_path}")
                        self._trigger_media_scan(full_remote_path)
                        success_count += 1
                    else:
                        logger.error(f"Failed to touch file {full_remote_path}")

            except Exception as e:
                logger.error(f"Error processing file {target_path_relative}: {e}")

        logger.info(f"Successfully processed {success_count} files")
        return success_count > 0

    def _inject_clock(self, clock_config: dict) -> bool:
        """Inject alarms (Simplified)"""
        return True

    def _inject_settings(self, settings_config: dict) -> bool:
        """Inject settings (Simplified)"""
        return True

    def _inject_gallery(self, gallery_config: dict) -> bool:
        """Inject gallery data"""
        if "albums" not in gallery_config:
            return False

        albums = gallery_config["albums"]
        success_count = 0

        for album in albums:
            album_name = album.get("name", "Unknown")
            if album_name == "Camera":
                base_path = "/sdcard/DCIM/Camera"
            elif album_name == "Screenshots":
                base_path = "/sdcard/Pictures/Screenshots"
            else:
                base_path = f"/sdcard/Pictures/{album_name}"
            
            safe_base_path = shlex.quote(base_path)
            execute_adb(f'adb -s {self.controller.device} shell mkdir -p {safe_base_path}', output=False)

            for content_item in album.get("content", []):
                filename = content_item
                if isinstance(content_item, str):
                    full_path = f"{base_path}/{filename}"
                    safe_full_path = shlex.quote(full_path)
                    
                    execute_adb(f'adb -s {self.controller.device} shell touch {safe_full_path}', output=False)
                    self._trigger_media_scan(full_path)
                    success_count += 1
        
        logger.info(f"Successfully processed gallery items")
        return success_count > 0