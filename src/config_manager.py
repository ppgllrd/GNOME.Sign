# config_manager.py
import os
import json
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
            self.config_data = {"certificates": [], "recent_files": []}
        
        # Ensure default keys exist
        if 'certificates' not in self.config_data:
            self.config_data['certificates'] = []
        if 'recent_files' not in self.config_data:
            self.config_data['recent_files'] = []

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
