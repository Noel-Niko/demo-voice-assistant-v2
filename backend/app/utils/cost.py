"""Token cost estimation utilities."""

# Simplified average cost per 1K tokens across GPT-3.5/4 models.
# In production, use per-model pricing from a config map.
_DEFAULT_COST_PER_1K_TOKENS = 0.00175


def estimate_cost(tokens: int, cost_per_1k: float = _DEFAULT_COST_PER_1K_TOKENS) -> float:
    """Estimate OpenAI API cost from token count.

    Args:
        tokens: Total tokens used.
        cost_per_1k: Cost per 1,000 tokens (default: $0.00175).

    Returns:
        Estimated cost in USD.
    """
    return (tokens / 1000) * cost_per_1k
