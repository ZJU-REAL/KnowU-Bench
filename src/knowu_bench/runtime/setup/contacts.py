import re
from loguru import logger
from knowu_bench.runtime.utils.helpers import execute_adb
from .base import BaseSetup

class ContactsSetup(BaseSetup):
    """Handles data injection for Contacts app via ADB Content Provider"""

    def setup(self, contacts_config: dict) -> bool:
        if not isinstance(contacts_config, dict) or "list" not in contacts_config:
            logger.error("Invalid contacts configuration")
            return False

        contact_list = contacts_config["list"]
        if not contact_list:
            return True

        success_count = 0
        
        for contact in contact_list:
            name = contact.get("name", "").strip()
            phone = contact.get("phone", "").strip()
            email = contact.get("email", "").strip()
            
            if not name or not phone:
                continue

            try:
                # 1. Check if contact exists
                safe_name = name.replace("'", r"\'")
                check_cmd = (
                    f'adb shell "content query --uri content://com.android.contacts/data '
                    f'--projection contact_id '
                    f'--where \\"mimetype=\'vnd.android.cursor.item/name\' AND data1=\'{safe_name}\'\\""'
                )
                check_res = execute_adb(check_cmd, output=True)
                
                if check_res.success and f"data1={name}" in check_res.output:
                    logger.info(f"Contact {name} already exists.")
                    success_count += 1
                    continue

                # 2. Insert Raw Contact
                insert_raw_cmd = (
                    'adb shell "content insert --uri content://com.android.contacts/raw_contacts '
                    '--bind account_name:s:null --bind account_type:s:null"'
                )
                raw_res = execute_adb(insert_raw_cmd, output=True)
                
                raw_contact_id = None
                
                # Attempt 1: Parse ID from insert output
                id_match = re.search(r'raw_contacts/(\d+)', raw_res.output)
                if id_match:
                    raw_contact_id = id_match.group(1)
                else:
                    # Attempt 2: Query all IDs and find max (Fallback)
                    get_id_cmd = 'adb shell "content query --uri content://com.android.contacts/raw_contacts --projection _id"'
                    id_res = execute_adb(get_id_cmd, output=True)
                    
                    if id_res.success:
                        all_ids = re.findall(r'_id=(\d+)', id_res.output)
                        if all_ids:
                            raw_contact_id = str(max(int(x) for x in all_ids))

                if not raw_contact_id:
                    logger.error(f"Failed to retrieve raw_contact_id for {name}")
                    continue

                # 3. Insert Name
                insert_name_cmd = (
                    f'adb shell "content insert --uri content://com.android.contacts/data '
                    f'--bind raw_contact_id:i:{raw_contact_id} '
                    f'--bind mimetype:s:vnd.android.cursor.item/name '
                    f'--bind data1:s:\'{safe_name}\'"'
                )
                if not execute_adb(insert_name_cmd, output=True).success:
                    logger.error(f"Failed to insert name for {name}")
                    continue

                # 4. Insert Phone
                safe_phone = phone.replace("'", r"\'")
                insert_phone_cmd = (
                    f'adb shell "content insert --uri content://com.android.contacts/data '
                    f'--bind raw_contact_id:i:{raw_contact_id} '
                    f'--bind mimetype:s:vnd.android.cursor.item/phone_v2 '
                    f'--bind data1:s:\'{safe_phone}\'"'
                )
                if not execute_adb(insert_phone_cmd, output=True).success:
                    logger.error(f"Failed to insert phone for {name}")
                    continue

                # 5. Insert Email (Optional)
                if email:
                    safe_email = email.replace("'", r"\'")
                    insert_email_cmd = (
                        f'adb shell "content insert --uri content://com.android.contacts/data '
                        f'--bind raw_contact_id:i:{raw_contact_id} '
                        f'--bind mimetype:s:vnd.android.cursor.item/email_v2 '
                        f'--bind data1:s:\'{safe_email}\'"'
                    )
                    if not execute_adb(insert_email_cmd, output=True).success:
                        logger.error(f"Failed to insert email for {name}")
                        # Continue even if email fails, as contact is created

                success_count += 1
                logger.debug(f"Successfully injected contact: {name}")
                
            except Exception as e:
                logger.error(f"Failed to inject contact {name}: {e}")

        logger.info(f"Successfully processed {success_count} contacts")
        return success_count > 0