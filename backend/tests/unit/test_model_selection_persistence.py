"""Tests for ACW Service model selection and persistence.

Verifies that ACWService correctly initializes with the current model from
ModelManager and receives model updates via callbacks, fixing the race
condition where model changes before ACWService init were lost.
"""
import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from fastapi import Request

from app.services.model_manager import ModelManager
from app.services.acw_service import ACWService
from app.repositories.conversation_repository import ConversationRepository
from app.constants import MODEL_PRESETS
from app.api.dependencies import get_acw_service


@pytest.fixture
def mock_repository():
    """Create mock repository for ACWService."""
    repo = Mock(spec=ConversationRepository)
    repo.save_ai_interaction = AsyncMock()
    repo.save_disposition_suggestions = AsyncMock()
    repo.save_compliance_attempts = AsyncMock()
    repo.save_crm_fields = AsyncMock()
    return repo


@pytest.fixture
def mock_request_with_model_manager():
    """Create mock Request with ModelManager in app.state."""
    def create_request(model_id="gpt-3.5-turbo"):
        request = Mock(spec=Request)
        request.app = Mock()
        request.app.state = Mock()
        request.app.state.model_manager = ModelManager(model_id=model_id)
        return request
    return create_request


@pytest.mark.asyncio
async def test_acw_service_uses_model_manager_model(mock_request_with_model_manager):
    """Test that get_acw_service() uses current model from ModelManager.

    When get_acw_service() is called for the first time (lazy init), it should
    use the model from ModelManager.get_current_preset(), not the hardcoded
    settings.OPENAI_MODEL default.

    This tests the FIX for the bug where model changes before init were lost.
    """
    # Create request with gpt-5 selected
    request = mock_request_with_model_manager(model_id="gpt-5")
    preset = MODEL_PRESETS["gpt-5"]

    # Reset app.state.acw_service to None (simulate first call)
    request.app.state.acw_service = None

    # Mock the settings and get_session_maker
    with patch("app.api.dependencies.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_MODEL = "gpt-3.5-turbo"  # Old default (should be ignored)

        with patch("app.api.dependencies.get_session_maker") as mock_get_session:
            mock_session_maker = Mock()
            mock_get_session.return_value = mock_session_maker

            with patch("app.api.dependencies.ConversationRepository") as mock_repo_class:
                mock_repo_class.return_value = Mock(spec=ConversationRepository)

                # Call get_acw_service - this triggers lazy init
                acw_service = await get_acw_service(request)

                # Verify it initialized with gpt-5, not gpt-3.5-turbo
                assert acw_service.model == preset.model_name
                assert acw_service.model != "gpt-3.5-turbo"


@pytest.mark.asyncio
async def test_acw_service_receives_model_updates_via_callback():
    """Test that ACWService receives model updates when registered with ModelManager.

    When ModelManager.set_model() is called after ACWService init, the callback
    should update ACWService's model.
    """
    # Create request with initial model
    request = Mock(spec=Request)
    request.app = Mock()
    request.app.state = Mock()
    model_manager = ModelManager(model_id="gpt-3.5-turbo")
    request.app.state.model_manager = model_manager
    request.app.state.acw_service = None  # Reset to simulate first call

    # Initialize ACWService
    with patch("app.api.dependencies.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_MODEL = "gpt-3.5-turbo"

        with patch("app.api.dependencies.get_session_maker") as mock_get_session:
            mock_session_maker = Mock()
            mock_get_session.return_value = mock_session_maker

            with patch("app.api.dependencies.ConversationRepository") as mock_repo_class:
                mock_repo_class.return_value = Mock(spec=ConversationRepository)

                # First call - lazy init and callback registration
                acw_service = await get_acw_service(request)
                initial_model = acw_service.model

                # Change model via ModelManager
                model_manager.set_model("gpt-4o")
                preset = MODEL_PRESETS["gpt-4o"]

                # Verify ACWService was updated via callback
                assert acw_service.model == preset.model_name
                assert acw_service.model != initial_model


@pytest.mark.asyncio
async def test_model_change_before_acw_init_is_not_lost(mock_request_with_model_manager):
    """Test that model changes before ACWService init are not lost.

    This is the CORE bug we're fixing: if the user changes the model from gpt-3.5
    to gpt-5 BEFORE get_acw_service() is called (lazy init), the old code would
    ignore the change and init with settings.OPENAI_MODEL (gpt-3.5-turbo).

    The fix: get_acw_service() calls get_model_manager(request) and uses its
    current preset instead of settings.OPENAI_MODEL.
    """
    # User has changed model to gpt-5 (ModelManager exists with gpt-5)
    request = mock_request_with_model_manager(model_id="gpt-5")
    preset = MODEL_PRESETS["gpt-5"]

    # ACWService has NOT been initialized yet (app.state.acw_service is None)
    request.app.state.acw_service = None
    assert request.app.state.acw_service is None

    # Now first ACW operation happens - triggers get_acw_service() lazy init
    with patch("app.api.dependencies.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_MODEL = "gpt-3.5-turbo"  # Config default (should be ignored)

        with patch("app.api.dependencies.get_session_maker") as mock_get_session:
            mock_session_maker = Mock()
            mock_get_session.return_value = mock_session_maker

            with patch("app.api.dependencies.ConversationRepository") as mock_repo_class:
                mock_repo_class.return_value = Mock(spec=ConversationRepository)

                # Call get_acw_service - should use gpt-5, not gpt-3.5-turbo
                acw_service = await get_acw_service(request)

                # VERIFY: Model is gpt-5 (from ModelManager), not gpt-3.5-turbo (from settings)
                assert acw_service.model == preset.model_name
                assert acw_service.model != "gpt-3.5-turbo", \
                    "Bug still exists: ACWService ignored ModelManager and used settings default"


@pytest.mark.asyncio
async def test_callback_registration_happens_on_init():
    """Test that get_acw_service() registers callback with ModelManager on init."""
    # Create request with ModelManager
    request = Mock(spec=Request)
    request.app = Mock()
    request.app.state = Mock()
    model_manager = ModelManager(model_id="gpt-3.5-turbo")
    request.app.state.model_manager = model_manager
    request.app.state.acw_service = None  # Reset to simulate first call

    # Track callback registrations
    original_register = model_manager.register_callback
    registered_callbacks = []

    def track_register(callback):
        registered_callbacks.append(callback)
        return original_register(callback)

    model_manager.register_callback = track_register

    # Initialize ACWService
    with patch("app.api.dependencies.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_MODEL = "gpt-3.5-turbo"

        with patch("app.api.dependencies.get_session_maker") as mock_get_session:
            mock_session_maker = Mock()
            mock_get_session.return_value = mock_session_maker

            with patch("app.api.dependencies.ConversationRepository") as mock_repo_class:
                mock_repo_class.return_value = Mock(spec=ConversationRepository)

                # Call get_acw_service
                acw_service = await get_acw_service(request)

                # Verify callback was registered
                assert len(registered_callbacks) == 1, \
                    "get_acw_service() should register callback with ModelManager on init"

                # Verify the callback is ACWService.set_model
                callback = registered_callbacks[0]
                # Check it's bound to the acw_service instance
                assert hasattr(callback, '__self__')
                assert callback.__self__ == acw_service
