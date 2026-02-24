"""Unit tests for FCR (First Call Resolution) calculation.

Following TDD: Tests written FIRST, then implementation.

FCR is calculated based on disposition code selection:
- Resolution dispositions (RESOLVED, etc.) → FCR = True
- Non-resolution dispositions (ESCALATED, FOLLOWUP) → FCR = False
- No disposition selected → FCR = None

Note: This is a simplified FCR calculation that does NOT account for
inbound transfers. Full FCR accuracy requires telephony integration
to track if the call was transferred from another agent.
"""
import pytest

from app.api.routes import calculate_fcr, RESOLUTION_DISPOSITIONS


class TestFCRCalculation:
    """Test suite for First Call Resolution calculation logic."""

    def test_resolved_disposition_returns_true(self):
        """Test that 'RESOLVED' disposition code returns FCR = True."""
        result = calculate_fcr("RESOLVED")
        assert result is True

    def test_escalated_disposition_returns_false(self):
        """Test that 'ESCALATED' disposition code returns FCR = False."""
        result = calculate_fcr("ESCALATED")
        assert result is False

    def test_followup_disposition_returns_false(self):
        """Test that 'FOLLOWUP' disposition code returns FCR = False."""
        result = calculate_fcr("FOLLOWUP")
        assert result is False

    def test_none_disposition_returns_none(self):
        """Test that None disposition returns None (not yet selected)."""
        result = calculate_fcr(None)
        assert result is None

    def test_empty_string_disposition_returns_none(self):
        """Test that empty string disposition returns None."""
        result = calculate_fcr("")
        assert result is None

    def test_resolution_dispositions_constant_exists(self):
        """Test that RESOLUTION_DISPOSITIONS constant is defined."""
        assert isinstance(RESOLUTION_DISPOSITIONS, set)
        assert len(RESOLUTION_DISPOSITIONS) > 0
        assert "RESOLVED" in RESOLUTION_DISPOSITIONS

    def test_all_resolution_dispositions_return_true(self):
        """Test that all dispositions in RESOLUTION_DISPOSITIONS return True."""
        # These are common resolution disposition codes
        resolution_codes = ["RESOLVED", "ORDER_PLACED", "INFO_PROVIDED"]

        for code in resolution_codes:
            if code in RESOLUTION_DISPOSITIONS:
                result = calculate_fcr(code)
                assert result is True, f"Expected {code} to return True"

    def test_unknown_disposition_returns_false(self):
        """Test that an unknown disposition code returns False (conservative approach)."""
        result = calculate_fcr("UNKNOWN_CODE_12345")
        assert result is False

    def test_case_sensitivity(self):
        """Test that disposition codes are case-sensitive (as per current implementation)."""
        # Uppercase codes are in the set
        assert calculate_fcr("RESOLVED") is True

        # Lowercase should not match (if implementation is case-sensitive)
        # This test documents current behavior
        result_lower = calculate_fcr("resolved")
        # If case-insensitive in future, this test should be updated
        assert result_lower is False

    def test_whitespace_in_disposition_code(self):
        """Test that disposition codes with whitespace are not matched."""
        # Whitespace should not accidentally match
        result = calculate_fcr(" RESOLVED ")
        assert result is False

    def test_disposition_with_spaces_if_in_set(self):
        """Test disposition codes with spaces (if any exist in the set)."""
        # Some disposition codes might have spaces
        if any(" " in code for code in RESOLUTION_DISPOSITIONS):
            # Test that codes with spaces work correctly
            space_code = next(code for code in RESOLUTION_DISPOSITIONS if " " in code)
            result = calculate_fcr(space_code)
            assert result is True


class TestFCRIntegration:
    """Integration tests for FCR calculation with conversation completion."""

    def test_fcr_calculation_deterministic(self):
        """Test that FCR calculation is deterministic for same input."""
        # Same input should always produce same output
        assert calculate_fcr("RESOLVED") == calculate_fcr("RESOLVED")
        assert calculate_fcr("ESCALATED") == calculate_fcr("ESCALATED")
        assert calculate_fcr(None) == calculate_fcr(None)

    def test_resolution_dispositions_comprehensive_list(self):
        """Test that RESOLUTION_DISPOSITIONS covers common resolution scenarios."""
        # Document expected resolution disposition codes
        expected_codes = [
            "RESOLVED",  # Generic resolution
            # Add more as they are discovered from disposition suggestion endpoint
        ]

        for code in expected_codes:
            assert code in RESOLUTION_DISPOSITIONS, f"Expected {code} to be in RESOLUTION_DISPOSITIONS"
