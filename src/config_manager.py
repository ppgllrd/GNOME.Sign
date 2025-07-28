# config_manager.py
import os
import json
import uuid
from collections import deque

class ConfigManager:
    """Manages loading, saving, and accessing application configuration settings."""
    MAX_RECENT_FILES = 10

    def __init__(self, config_path="~/.config/gnomesign/config.json"):
        """Initializes the ConfigManager with the path to the configuration file."""
        self.config_file = os.path.expanduser(config_path)
        self.config_data = {}

    def load(self):
        """Loads configuration from the JSON file, or creates it with defaults if it doesn't exist."""
        config_dir = os.path.dirname(self.config_file)
        os.makedirs(config_dir, exist_ok=True)
        try:
            with open(self.config_file, 'r') as f:
                self.config_data = json.load(f)
        except (IOError, json.JSONDecodeError):
            self.config_data = {}
        
        defaults = {
            'certificates': [], 'recent_files': [], 'signature_templates': [],
            'active_template_id': None, 'last_folder': os.path.expanduser("~"),
            'language': "en", 'active_cert_path': None,
            'signature_reason': '', 
            'signature_location': '' 
        }
        for key, value in defaults.items():
            self.config_data.setdefault(key, value)
        self._create_default_templates_if_needed()

    def _create_default_templates_if_needed(self):
        """Creates and saves a set of default signature templates if none are present in the config."""
        if not self.config_data['signature_templates']:
            simple_id = uuid.uuid4().hex
            simple_template = { 
                "id": simple_id, 
                "name": "Simple", 
                "template": "Digitally signed by:\n<b>$$SUBJECTCN$$</b>\nDate: $$SIGNDATE=dd-MM-yyyy$$" 
            }
            detailed_id = uuid.uuid4().hex
            detailed_template = { 
                "id": detailed_id, 
                "name": "Detailed", 
                "template": "Digitally signed by: <b>$$SUBJECTCN$$</b>\nDate: $$SIGNDATE=dd-MM-yyyy$$\nIssuer: <b>$$ISSUERCN$$</b>"
            }
            self.config_data['signature_templates'].extend([simple_template, detailed_template])
            self.config_data['active_template_id'] = simple_id
            self.save() # Initial save is OK here, as it's part of first-time setup.

    def save(self):
        """Saves the current configuration data to the JSON file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config_data, f, indent=2)
        except IOError as e:
            print(f"Error saving configuration: {e}")
            
    def get_cert_paths(self):
        """Returns a list of all configured certificate paths."""
        return [c["path"] for c in self.config_data.get("certificates", [])]
        
    def add_cert_path(self, path):
        """Adds a new certificate path to the configuration if it doesn't already exist."""
        if path not in self.get_cert_paths():
            self.config_data["certificates"].append({"path": path})

    def remove_cert_path(self, path_to_remove):
        """Removes a certificate path from the configuration."""
        self.config_data["certificates"] = [c for c in self.config_data["certificates"] if c.get("path") != path_to_remove]

    def get_recent_files(self):
        """Returns the list of recently opened files."""
        return self.config_data.get("recent_files", [])

    def add_recent_file(self, file_path):
        """Adds a file path to the top of the recent files list."""
        recent_files = deque(self.get_recent_files(), maxlen=self.MAX_RECENT_FILES)
        if file_path in recent_files:
            recent_files.remove(file_path)
        recent_files.appendleft(file_path)
        self.config_data["recent_files"] = list(recent_files)

    def remove_recent_file(self, file_path):
        """Removes a specific file path from the recent files list."""
        if file_path in self.config_data["recent_files"]:
            self.config_data["recent_files"].remove(file_path)
            
    def get_signature_templates(self):
        """Returns the list of all signature templates."""
        return self.config_data.get("signature_templates", [])

    def get_template_by_id(self, template_id):
        """Finds and returns a signature template by its unique ID."""
        return next((t for t in self.get_signature_templates() if t.get('id') == template_id), None)

    def save_template(self, template_data):
        """Saves a signature template, either by updating an existing one or adding a new one."""
        templates = self.get_signature_templates()
        for i, t in enumerate(templates):
            if t.get('id') == template_data.get('id'):
                templates[i] = template_data
                return
        templates.append(template_data)

    def delete_template(self, template_id):
        """Deletes a signature template by its ID."""
        self.config_data['signature_templates'] = [t for t in self.get_signature_templates() if t.get('id') != template_id]

    def get_active_template_id(self):
        """Returns the ID of the currently active signature template."""
        return self.config_data.get('active_template_id')

    def set_active_template_id(self, template_id):
        """Sets the active signature template by its ID."""
        self.config_data['active_template_id'] = template_id

    def get_active_template(self):
        """Returns the full data of the currently active signature template."""
        return self.get_template_by_id(self.get_active_template_id())
    
    def get_active_cert_path(self):
        """Returns the path of the currently active certificate."""
        return self.config_data.get("active_cert_path")

    def set_active_cert_path(self, path):
        """Sets the active certificate path."""
        self.config_data['active_cert_path'] = path
    
    def get_last_folder(self):
        """Returns the path of the last folder used for opening files."""
        return self.config_data.get("last_folder", os.path.expanduser("~"))

    def set_last_folder(self, path):
        """Sets the last folder path used."""
        self.config_data["last_folder"] = path

    def get_language(self):
        """Returns the current language code (e.g., 'es' or 'en')."""
        return self.config_data.get("language", "es")

    def set_language(self, lang_code):
        """Sets the application language."""
        self.config_data["language"] = lang_code
    
    def get_signature_reason(self):
        """Returns the default signature reason."""
        return self.config_data.get("signature_reason", "")

    def set_signature_reason(self, reason):
        """Sets the default signature reason."""
        self.config_data["signature_reason"] = reason

    def get_signature_location(self):
        """Returns the default signature location."""
        return self.config_data.get("signature_location", "")

    def set_signature_location(self, location):
        """Sets the default signature location."""
        self.config_data["signature_location"] = location