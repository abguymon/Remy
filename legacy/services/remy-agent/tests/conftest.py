"""
Shared fixtures for remy-agent tests.
"""

import pytest


@pytest.fixture
def sample_mealie_recipe():
    """A sample recipe as returned by Mealie's get_recipe_detailed."""
    return {
        "id": "abc123",
        "name": "Shrimp Scampi",
        "slug": "shrimp-scampi",
        "description": "Classic Italian-American shrimp dish",
        "recipeIngredient": [
            {"note": "1 lb large shrimp, peeled and deveined", "food": {"name": "shrimp"}},
            {"note": "4 tbsp butter", "food": {"name": "butter"}},
            {"note": "4 cloves garlic, minced", "food": {"name": "garlic"}},
            {"note": "1/2 cup white wine", "food": {"name": "white wine"}},
            {"note": "1/4 tsp salt", "food": {"name": "salt"}},
            {"note": "1/4 tsp black pepper", "food": {"name": "black pepper"}},
        ],
        "recipeInstructions": [
            {"text": "Melt butter in a large skillet over medium heat."},
            {"text": "Add garlic and cook for 1 minute."},
            {"text": "Add shrimp and cook until pink."},
        ],
    }


@pytest.fixture
def sample_pantry_config():
    """Sample pantry configuration."""
    return {
        "bypass_staples": [
            "salt",
            "black pepper",
            "water",
            "olive oil",
            "flour",
        ]
    }
