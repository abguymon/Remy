import yaml
import os
from typing import List, Dict, Any

def load_pantry_config(config_path: str = "pantry.yaml") -> Dict[str, Any]:
    """
    Loads the pantry configuration from a YAML file.
    Search order:
    1. Absolute path provided
    2. Relative to current working directory
    3. Relative to project root (up 3 levels if running from src)
    """
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
            
    # Try project root
    # assuming we are in services/remy-agent/src/remy_agent
    # root is ../../../..
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
    root_config_path = os.path.join(project_root, config_path)
    
    if os.path.exists(root_config_path):
        with open(root_config_path, "r") as f:
            return yaml.safe_load(f)
            
    return {"bypass_staples": []}
