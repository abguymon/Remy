"""
Unit tests for remy_agent.utils module.
"""

import os
import tempfile

import yaml
from remy_agent.utils import load_pantry_config


class TestLoadPantryConfig:
    """Tests for the load_pantry_config function."""

    def test_load_from_absolute_path(self, sample_pantry_config):
        """Test loading pantry config from an absolute path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_pantry_config, f)
            temp_path = f.name

        try:
            result = load_pantry_config(temp_path)
            assert result == sample_pantry_config
            assert "bypass_staples" in result
            assert "salt" in result["bypass_staples"]
        finally:
            os.unlink(temp_path)

    def test_load_from_relative_path(self, sample_pantry_config):
        """Test loading pantry config from a relative path."""
        # Create temp file in current directory
        temp_filename = "test_pantry_temp.yaml"
        with open(temp_filename, "w") as f:
            yaml.dump(sample_pantry_config, f)

        try:
            result = load_pantry_config(temp_filename)
            assert result == sample_pantry_config
        finally:
            os.unlink(temp_filename)

    def test_returns_empty_bypass_staples_when_file_not_found(self):
        """Test that missing config file returns empty bypass_staples."""
        result = load_pantry_config("nonexistent_file.yaml")
        assert result == {"bypass_staples": []}

    def test_handles_empty_yaml_file(self):
        """Test handling of empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            result = load_pantry_config(temp_path)
            # Empty YAML returns None, so we expect the default
            assert result is None or result == {"bypass_staples": []}
        finally:
            os.unlink(temp_path)

    def test_handles_yaml_with_extra_fields(self):
        """Test that extra fields in YAML are preserved."""
        config = {
            "bypass_staples": ["salt", "pepper"],
            "extra_field": "some_value",
            "nested": {"key": "value"},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            result = load_pantry_config(temp_path)
            assert result["bypass_staples"] == ["salt", "pepper"]
            assert result["extra_field"] == "some_value"
            assert result["nested"]["key"] == "value"
        finally:
            os.unlink(temp_path)

    def test_handles_empty_bypass_staples_list(self):
        """Test handling of config with empty bypass_staples list."""
        config = {"bypass_staples": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            result = load_pantry_config(temp_path)
            assert result["bypass_staples"] == []
        finally:
            os.unlink(temp_path)
