"""Pytest configuration and shared fixtures."""
import pytest


@pytest.fixture
def sample_transcript_lines():
    """Sample transcript lines for testing."""
    return [
        "02/01/2026 11:39:00|Agent:Thank you for calling customer support.",
        "02/01/2026 11:39:01|Customer:Hi, I need help with my order.",
        "04/10/2026 11:40:08\tCustomer:Okay, it's 784562.",  # Tab delimiter (edge case)
        "Invalid line without proper format",
        "Timestamp|Transcript_Log",  # Header line
    ]
