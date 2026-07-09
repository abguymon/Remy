import os
from typing import Any

import yaml


def load_pantry_config(config_path: str = "pantry.yaml") -> dict[str, Any]:
    """
    Loads the pantry configuration from a YAML file.
    Search order:
    1. Absolute path provided
    2. Relative to current working directory
    3. Relative to project root (up 3 levels if running from src)
    """
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)

    # Try project root
    # assuming we are in services/remy-agent/src/remy_agent
    # root is ../../../..
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
    root_config_path = os.path.join(project_root, config_path)

    if os.path.exists(root_config_path):
        with open(root_config_path) as f:
            return yaml.safe_load(f)

    return {"bypass_staples": []}


def load_recipe_sources(config_path: str = "recipe_sources.yaml") -> dict[str, Any]:
    """
    Loads favorite recipe sources configuration from a YAML file.
    """
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f) or {}

    # Try project root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
    root_config_path = os.path.join(project_root, config_path)

    if os.path.exists(root_config_path):
        with open(root_config_path) as f:
            return yaml.safe_load(f) or {}

    return {"favorite_sources": []}


def load_user_settings(config_path: str = "user_settings.yaml") -> dict[str, Any]:
    """Load user settings from a YAML file."""
    default = {"store": {"location_id": None, "name": None, "zip_code": ""}, "fulfillment": "PICKUP"}

    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f) or default

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
    root_config_path = os.path.join(project_root, config_path)

    if os.path.exists(root_config_path):
        with open(root_config_path) as f:
            return yaml.safe_load(f) or default

    return default


def save_user_settings(settings: dict[str, Any], config_path: str = "user_settings.yaml"):
    """Save user settings to a YAML file."""
    with open(config_path, "w") as f:
        yaml.dump(settings, f, default_flow_style=False)
