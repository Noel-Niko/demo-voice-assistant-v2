"""Central model state holder with Observer-pattern notification.

Stores the current LLM model preset and notifies registered services
when the model changes. Services register callbacks via register_callback().
"""
from typing import Callable

import structlog

from app.constants import MODEL_PRESETS, DEFAULT_MODEL_ID, ModelPreset

logger = structlog.get_logger(__name__)

# Callback signature: (model_name: str, reasoning_effort: str | None) -> None
ModelChangeCallback = Callable[[str, str | None], None]


class ModelManager:
    """Central model state holder.

    Manages the current LLM model and notifies services when it changes.
    Follows Observer pattern — services register callbacks instead of being
    tightly coupled to the manager.
    """

    def __init__(self, model_id: str = DEFAULT_MODEL_ID) -> None:
        """Initialize with a model preset.

        Args:
            model_id: Model preset ID (must be in MODEL_PRESETS)

        Raises:
            ValueError: If model_id not in MODEL_PRESETS
        """
        if model_id not in MODEL_PRESETS:
            raise ValueError(f"Unknown model: {model_id}. Available: {list(MODEL_PRESETS.keys())}")

        self._current_model_id = model_id
        self._callbacks: list[ModelChangeCallback] = []

        logger.info(
            "model_manager_initialized",
            model_id=model_id,
            display_name=MODEL_PRESETS[model_id].display_name,
        )

    @property
    def current_model_id(self) -> str:
        """Current model preset ID."""
        return self._current_model_id

    def get_current_preset(self) -> ModelPreset:
        """Get the current ModelPreset."""
        return MODEL_PRESETS[self._current_model_id]

    def set_model(self, model_id: str) -> None:
        """Switch to a new model and notify all registered services.

        Args:
            model_id: Model preset ID to switch to

        Raises:
            ValueError: If model_id not in MODEL_PRESETS
        """
        if model_id not in MODEL_PRESETS:
            raise ValueError(f"Unknown model: {model_id}. Available: {list(MODEL_PRESETS.keys())}")

        old_model = self._current_model_id
        self._current_model_id = model_id
        preset = MODEL_PRESETS[model_id]

        logger.info(
            "model_changed",
            old_model=old_model,
            new_model=model_id,
            display_name=preset.display_name,
            reasoning_effort=preset.reasoning_effort,
        )

        # Notify all registered callbacks
        for callback in self._callbacks:
            callback(preset.model_name, preset.reasoning_effort)

    def get_api_kwargs(self) -> dict:
        """Get OpenAI API kwargs for the current model.

        Returns:
            Dict with 'model' and optionally 'reasoning_effort'
        """
        preset = MODEL_PRESETS[self._current_model_id]
        kwargs = {"model": preset.model_name}
        if preset.reasoning_effort:
            kwargs["reasoning_effort"] = preset.reasoning_effort
        return kwargs

    def register_callback(self, callback: ModelChangeCallback) -> None:
        """Register a callback to be notified on model changes.

        Args:
            callback: Function(model_name, reasoning_effort) called on model change
        """
        self._callbacks.append(callback)

    def list_presets(self) -> list[ModelPreset]:
        """Return all available model presets.

        Returns:
            List of all ModelPreset objects
        """
        return list(MODEL_PRESETS.values())
