"""Unit tests for ModelManager service.

Following TDD: Tests written FIRST, then implementation.
ModelManager is the central model state holder that notifies services via Observer pattern.
"""
import pytest
from unittest.mock import Mock

from app.services.model_manager import ModelManager
from app.constants import MODEL_PRESETS, DEFAULT_MODEL_ID


class TestModelManagerInit:
    """Test ModelManager initialization."""

    def test_init_with_default_model(self):
        """Test that ModelManager initializes with default model preset."""
        manager = ModelManager()
        assert manager.current_model_id == DEFAULT_MODEL_ID
        assert manager.current_model_id in MODEL_PRESETS

    def test_init_with_specific_model(self):
        """Test initializing with a specific model."""
        manager = ModelManager(model_id="gpt-4o")
        assert manager.current_model_id == "gpt-4o"

    def test_init_with_invalid_model_raises(self):
        """Test that initializing with an unknown model raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model"):
            ModelManager(model_id="nonexistent-model")


class TestModelManagerSetModel:
    """Test set_model() method."""

    def test_set_model_valid(self):
        """Test switching to a valid model."""
        manager = ModelManager()
        manager.set_model("gpt-4o")
        assert manager.current_model_id == "gpt-4o"

    def test_set_model_invalid_raises(self):
        """Test that switching to an invalid model raises ValueError."""
        manager = ModelManager()
        with pytest.raises(ValueError, match="Unknown model"):
            manager.set_model("nonexistent-model")

    def test_set_model_triggers_callbacks(self):
        """Test that set_model notifies all registered callbacks."""
        manager = ModelManager()
        callback1 = Mock()
        callback2 = Mock()
        manager.register_callback(callback1)
        manager.register_callback(callback2)

        manager.set_model("gpt-4o")

        preset = MODEL_PRESETS["gpt-4o"]
        callback1.assert_called_once_with(preset.model_name, preset.reasoning_effort)
        callback2.assert_called_once_with(preset.model_name, preset.reasoning_effort)


class TestModelManagerGetApiKwargs:
    """Test get_api_kwargs() method."""

    def test_get_api_kwargs_without_reasoning(self):
        """Test kwargs for a model without reasoning_effort."""
        manager = ModelManager(model_id="gpt-4.1-mini")
        kwargs = manager.get_api_kwargs()
        assert kwargs["model"] == "gpt-4.1-mini"
        assert "reasoning_effort" not in kwargs

    def test_get_api_kwargs_with_reasoning(self):
        """Test kwargs for a model with reasoning_effort."""
        manager = ModelManager(model_id="gpt-5")
        kwargs = manager.get_api_kwargs()
        assert kwargs["model"] == "gpt-5"
        assert kwargs["reasoning_effort"] == "low"


class TestModelManagerListPresets:
    """Test list_presets() method."""

    def test_list_presets_returns_all_four(self):
        """Test that list_presets returns all 4 model presets."""
        manager = ModelManager()
        presets = manager.list_presets()
        assert len(presets) == 4
        ids = [p.model_id for p in presets]
        assert "gpt-3.5-turbo" in ids
        assert "gpt-4.1-mini" in ids
        assert "gpt-4o" in ids
        assert "gpt-5" in ids
