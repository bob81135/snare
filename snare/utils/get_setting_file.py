import os
import json
def get_setting(full_page_path):
    if not os.path.exists(os.path.join(full_page_path, 'setting.json')):
        setting_info = {"sensitives":[],"auth_list":[],"user_dict":{"user":"password"}}
        return setting_info
    with open(os.path.join(full_page_path, 'setting.json')) as setting:
        setting_info = json.load(setting)
    return setting_info