import os
import json
import uuid
from collections import deque

class ConfigManager:
    """Handles reading and writing the application's configuration file."""
    
    MAX_RECENT_FILES = 10

    def __init__(self, config_path="~/.config/gnomesign/config.json"):
        """
        Initializes the ConfigManager.
        
        Args:
            config_path (str): The path to the configuration file.
        """
        self.config_file = os.path.expanduser(config_path)
        self.config_data = {}

    def load(self):
        """Loads the configuration from the JSON file."""
        config_dir = os.path.dirname(self.config_file)
        os.makedirs(config_dir, exist_ok=True)
        try:
            with open(self.config_file, 'r') as f:
                self.config_data = json.load(f)
        except (IOError, json.JSONDecodeError):
            self.config_data = {}
        
        # Ensure default keys exist
        if 'certificates' not in self.config_data:
            self.config_data['certificates'] = []
        if 'recent_files' not in self.config_data:
            self.config_data['recent_files'] = []
        if 'signature_templates' not in self.config_data:
            self.config_data['signature_templates'] = []
        if 'active_template_id' not in self.config_data:
            self.config_data['active_template_id'] = None
        if 'last_folder' not in self.config_data:
            self.config_data['last_folder'] = os.path.expanduser("~")
        if 'language' not in self.config_data:
            self.config_data['language'] = "es" # Default language

        self._create_default_templates_if_needed()

    def _create_default_templates_if_needed(self):
        if not self.config_data['signature_templates']:
            default_id = uuid.uuid4().hex
            default_template = {
                "id": default_id,
                "name": "Default",
                "template_es": "Firmado digitalmente por:\n<b>$$SUBJECTCN$$</b>\nFecha: $$SIGNDATE=dd-MM-yyyy$$",
                "template_en": "Digitally signed by:\n<b>$$SUBJECTCN$$</b>\nDate: $$SIGNDATE=yyyy-MM-dd$$"
            }
            self.config_data['signature_templates'].append(default_template)
            self.config_data['active_template_id'] = default_id
            self.save()

    def save(self):
        """Saves the current configuration to the JSON file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config_data, f, indent=2)
        except IOError as e:
            print(f"Error saving configuration: {e}")
            
    def get_cert_paths(self):
        """Returns a list of certificate paths."""
        return [c["path"] for c in self.config_data.get("certificates", [])]
        
    def add_cert_path(self, path):
        """Adds a new certificate path if it doesn't already exist."""
        cert_paths = [c["path"] for c in self.config_data["certificates"]]
        if path not in cert_paths:
            self.config_data["certificates"].append({"path": path})

    def remove_cert_path(self, path_to_remove):
        """Removes a certificate path from the configuration."""
        self.config_data["certificates"] = [
            cert for cert in self.config_data["certificates"] if cert.get("path") != path_to_remove
        ]
        self.save()

    def get_recent_files(self):
        """Returns the list of recent file paths."""
        return self.config_data.get("recent_files", [])

    def add_recent_file(self, file_path):
        """Adds a file to the top of the recent files list."""
        recent_files = deque(self.get_recent_files(), maxlen=self.MAX_RECENT_FILES)
        if file_path in recent_files:
            recent_files.remove(file_path)
        recent_files.appendleft(file_path)
        self.config_data["recent_files"] = list(recent_files)

    def remove_recent_file(self, file_path):
        """Removes a file path from the recent files list."""
        if file_path in self.config_data["recent_files"]:
            self.config_data["recent_files"].remove(file_path)
            
    def get_signature_templates(self):
        return self.config_data.get("signature_templates", [])

    def get_template_by_id(self, template_id):
        for template in self.get_signature_templates():
            if template['id'] == template_id:
                return template
        return None

    def save_template(self, template_data):
        templates = self.get_signature_templates()
        # Check if it's an existing template to update it
        for i, t in enumerate(templates):
            if t['id'] == template_data['id']:
                templates[i] = template_data
                self.save()
                return
        # If not found, it's a new template
        templates.append(template_data)
        self.save()

    def delete_template(self, template_id):
        templates = self.get_signature_templates()
        self.config_data['signature_templates'] = [t for t in templates if t['id'] != template_id]
        if self.get_active_template_id() == template_id:
            if self.config_data['signature_templates']:
                self.set_active_template_id(self.config_data['signature_templates'][0]['id'])
            else:
                self.set_active_template_id(None)
        self.save()

    def get_active_template_id(self):
        return self.config_data.get('active_template_id')

    def set_active_template_id(self, template_id):
        self.config_data['active_template_id'] = template_id
        self.save()

    def get_active_template(self):
        active_id = self.get_active_template_id()
        if not active_id:
            return None
        return self.get_template_by_id(active_id)
        
    def get_last_folder(self):
        """Returns the last used folder path."""
        return self.config_data.get("last_folder", os.path.expanduser("~"))

    def set_last_folder(self, path):
        """Sets the last used folder path."""
        self.config_data["last_folder"] = path
        
    def get_language(self):
        """Returns the saved language code."""
        return self.config_data.get("language", "es")

    def set_language(self, lang_code):
        """Sets and saves the language code."""
        self.config_data["language"] = lang_code
        self.save()