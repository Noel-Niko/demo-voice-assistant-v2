"""Tests for cost estimation utility.

Simple tests to verify token cost calculation logic.
"""
import pytest
from app.utils.cost import estimate_cost


def test_estimate_cost_default():
    """Test cost estimation with default rate ($0.00175 per 1K tokens)."""
    # 1000 tokens should cost $0.00175
    assert estimate_cost(1000) == 0.00175

    # 2000 tokens should cost $0.0035
    assert estimate_cost(2000) == 0.0035

    # 500 tokens should cost $0.000875
    assert estimate_cost(500) == 0.000875

    # 0 tokens should cost $0
    assert estimate_cost(0) == 0.0


def test_estimate_cost_custom_rate():
    """Test cost estimation with custom rate."""
    # Custom rate: $0.002 per 1K tokens
    assert estimate_cost(1000, cost_per_1k=0.002) == 0.002
    assert estimate_cost(5000, cost_per_1k=0.002) == 0.01

    # Custom rate: $0.001 per 1K tokens
    assert estimate_cost(10000, cost_per_1k=0.001) == 0.01


def test_estimate_cost_fractional_tokens():
    """Test cost estimation with fractional token counts."""
    # 1500 tokens at default rate
    expected = (1500 / 1000) * 0.00175
    assert estimate_cost(1500) == expected

    # 250 tokens at default rate
    expected = (250 / 1000) * 0.00175
    assert estimate_cost(250) == expected


def test_estimate_cost_large_numbers():
    """Test cost estimation with large token counts."""
    # 1 million tokens at default rate
    assert estimate_cost(1_000_000) == 1.75

    # 100K tokens at $0.01 per 1K
    assert estimate_cost(100_000, cost_per_1k=0.01) == 1.0
