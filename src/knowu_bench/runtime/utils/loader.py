import yaml
import os
from typing import Dict, Any

class UserProfileLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = self._load_yaml()

    def _load_yaml(self) -> Dict[str, Any]:
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Config file not found: {self.file_path}")
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing YAML: {e}")
        
        self._validate_schema(data)
        return data

    def _validate_schema(self, data: Dict):
        required_roots = ['user_profile', 'environment_init_state']
        for root in required_roots:
            if root not in data:
                raise ValueError(f"Missing required root key in YAML: '{root}'")
        
        print(f"✅ Configuration loaded and validated from {self.file_path}")

    @property
    def user_profile(self) -> Dict[str, Any]:
        return self.data.get('user_profile', {})

    @property
    def environment_state(self) -> Dict[str, Any]:
        return self.data.get('environment_init_state', {})

    def flatten_user_profile(self, separator: str = '.') -> Dict[str, Any]:
        return self._flatten_dict(self.user_profile, parent_key='', sep=separator)

    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        
        return dict(items)

    def get_formatted_prompt_context(self) -> str:
        flat_profile = self.flatten_user_profile(separator=' -> ')
        lines = ["# User Profile Context"]
        for key, value in flat_profile.items():
            val_str = str(value) if not isinstance(value, list) else ", ".join(map(str, value))
            lines.append(f"- {key}: {val_str}")
        return "\n".join(lines)