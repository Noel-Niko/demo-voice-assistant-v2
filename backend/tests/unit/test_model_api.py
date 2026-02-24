"""Unit tests for Model API endpoints (GET /api/model, PUT /api/model).

Following TDD: Tests written FIRST, then implementation.
"""
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.dependencies import get_model_manager


@pytest.mark.asyncio
class TestModelAPI:
    """Test suite for model selection API endpoints."""

    async def test_get_model_returns_current_and_presets(self):
        """GET /api/model returns current model + all available presets."""
        mock_manager = MagicMock()
        mock_manager.current_model_id = "gpt-3.5-turbo"

        mock_preset = MagicMock()
        mock_preset.model_id = "gpt-3.5-turbo"
        mock_preset.model_name = "gpt-3.5-turbo"
        mock_preset.display_name = "GPT-3.5 Turbo (Recommended)"
        mock_preset.reasoning_effort = None
        mock_preset.description = "Fastest model"
        mock_manager.get_current_preset.return_value = mock_preset

        mock_presets = [
            mock_preset,
            MagicMock(model_id="gpt-4.1-mini", model_name="gpt-4.1-mini",
                      display_name="GPT-4.1 Mini", reasoning_effort=None,
                      description="Higher quality but slower"),
            MagicMock(model_id="gpt-4o", model_name="gpt-4o",
                      display_name="GPT-4o", reasoning_effort=None,
                      description="Quality tier"),
            MagicMock(model_id="gpt-5", model_name="gpt-5",
                      display_name="GPT-5 (Low Reasoning)", reasoning_effort="low",
                      description="Reasoning model"),
        ]
        mock_manager.list_presets.return_value = mock_presets

        app.dependency_overrides[get_model_manager] = lambda: mock_manager
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/model")

            assert response.status_code == 200
            data = response.json()
            assert data["current_model_id"] == "gpt-3.5-turbo"
            assert "current" in data
            assert "available" in data
            assert len(data["available"]) == 4
        finally:
            app.dependency_overrides.pop(get_model_manager, None)

    async def test_put_model_changes_model(self):
        """PUT /api/model switches to a new model globally."""
        mock_manager = MagicMock()
        mock_manager.set_model.return_value = None
        mock_manager.current_model_id = "gpt-4o"

        mock_preset = MagicMock()
        mock_preset.model_id = "gpt-4o"
        mock_preset.model_name = "gpt-4o"
        mock_preset.display_name = "GPT-4o"
        mock_preset.reasoning_effort = None
        mock_manager.get_current_preset.return_value = mock_preset

        app.dependency_overrides[get_model_manager] = lambda: mock_manager
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/model",
                    json={"model_id": "gpt-4o"}
                )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "updated"
            assert data["model_id"] == "gpt-4o"
            mock_manager.set_model.assert_called_once_with("gpt-4o")
        finally:
            app.dependency_overrides.pop(get_model_manager, None)

    async def test_put_model_invalid_returns_400(self):
        """PUT /api/model with invalid model_id returns 400."""
        mock_manager = MagicMock()
        mock_manager.set_model.side_effect = ValueError("Unknown model: bad-model")

        app.dependency_overrides[get_model_manager] = lambda: mock_manager
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/model",
                    json={"model_id": "bad-model"}
                )

            assert response.status_code == 400
        finally:
            app.dependency_overrides.pop(get_model_manager, None)

    async def test_presets_contain_four_models(self):
        """Verify the MODEL_PRESETS constant has exactly 4 entries."""
        from app.constants import MODEL_PRESETS
        assert len(MODEL_PRESETS) == 4
        assert "gpt-3.5-turbo" in MODEL_PRESETS
        assert "gpt-4.1-mini" in MODEL_PRESETS
        assert "gpt-4o" in MODEL_PRESETS
        assert "gpt-5" in MODEL_PRESETS
