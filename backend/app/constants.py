"""Application constants for CRM field extraction and taxonomies.

Following 12-factor config: These are business logic constants (not config).
Environment-specific values belong in environment variables.
"""
from dataclasses import dataclass


# ===== LLM Model Presets =====
# Evaluated against ctlg_domain_dev_bronze.schm_product.llm_eval_latency_stats
# and ctlg_domain_dev_bronze.schm_product.llm_eval_structured_stats
# See ARCHITECTURAL_DECISIONS.md ADR-026 for benchmark data and rationale.

@dataclass(frozen=True)
class ModelPreset:
    """Immutable LLM model preset with metadata."""
    model_id: str           # Unique key (e.g. "gpt-4.1-mini")
    model_name: str         # OpenAI API model name
    display_name: str       # UI label
    reasoning_effort: str | None  # For reasoning models (e.g. "low")
    description: str        # Short description for UI tooltip


MODEL_PRESETS: dict[str, ModelPreset] = {
    "gpt-3.5-turbo": ModelPreset(
        model_id="gpt-3.5-turbo",
        model_name="gpt-3.5-turbo",
        display_name="GPT-3.5 Turbo",
        reasoning_effort=None,
        description="Fastest model. Best real-time latency for agent-assist UX.",
    ),
    "gpt-4.1-mini": ModelPreset(
        model_id="gpt-4.1-mini",
        model_name="gpt-4.1-mini",
        display_name="GPT-4.1 Mini",
        reasoning_effort=None,
        description="Higher quality but slower. Latency may impact real-time UX.",
    ),
    "gpt-4o": ModelPreset(
        model_id="gpt-4o",
        model_name="gpt-4o",
        display_name="GPT-4o",
        reasoning_effort=None,
        description="Quality tier. Higher accuracy, higher latency.",
    ),
    "gpt-5": ModelPreset(
        model_id="gpt-5",
        model_name="gpt-5",
        display_name="GPT-5 (Not Recommended)",
        reasoning_effort="low",
        description="Reasoning model. Latency too high for real-time use.",
    ),
}

DEFAULT_MODEL_ID = "gpt-3.5-turbo"


# CRM Field Extraction Taxonomies
# These can be changed here without code modification if business requirements change

PRIORITY_VALUES = [
    "Critical",
    "High",
    "Medium",
    "Low",
]

CASE_TYPE_VALUES = [
    "Order Tracking",
    "Product Question",
    "Billing Issue",
    "Technical Support",
    "Return/Refund",
    "Other",
]

# CRM Field Names (Salesforce)
CRM_FIELD_NAMES = {
    "CASE_SUBJECT": "Case Subject",
    "CASE_TYPE": "Case Type",
    "PRIORITY": "Priority",
    "ROOT_CAUSE": "Root Cause",
    "RESOLUTION_ACTION": "Resolution Action",
}

# ===== Disposition Code Taxonomy =====
# Fixed disposition codes for agent selection (no AI involvement)
# Follows industry standards from Genesys, Salesforce Service Cloud, Five9
# Used for FCR calculation and dashboard metrics

class DispositionCategory:
    """Primary disposition categories for organization."""
    RESOLVED = "RESOLVED"
    PENDING = "PENDING"
    ESCALATED = "ESCALATED"
    NO_RESOLUTION = "NO_RESOLUTION"


# Full disposition code taxonomy with metadata
# Each disposition has: code (DB key), label (UI display), category, fcr_eligible (for FCR calc)
DISPOSITION_CODES = [
    # === RESOLVED (FCR = Yes) ===
    {
        "code": "RESOLVED",
        "label": "Issue Resolved",
        "category": DispositionCategory.RESOLVED,
        "fcr_eligible": True,
        "description": "Customer issue fully resolved on first contact",
    },
    {
        "code": "ORDER_PLACED",
        "label": "Order Placed",
        "category": DispositionCategory.RESOLVED,
        "fcr_eligible": True,
        "description": "Order successfully placed by agent",
    },
    {
        "code": "INFO_PROVIDED",
        "label": "Information Provided",
        "category": DispositionCategory.RESOLVED,
        "fcr_eligible": True,
        "description": "Customer received requested information",
    },
    {
        "code": "REQUEST_PROCESSED",
        "label": "Request Processed",
        "category": DispositionCategory.RESOLVED,
        "fcr_eligible": True,
        "description": "Customer request completed successfully",
    },
    {
        "code": "NO_ACTION_NEEDED",
        "label": "No Action Needed",
        "category": DispositionCategory.RESOLVED,
        "fcr_eligible": True,
        "description": "Call was informational; no action required",
    },

    # === PENDING (FCR = No - requires follow-up) ===
    {
        "code": "FOLLOWUP_REQUIRED",
        "label": "Follow-Up Required",
        "category": DispositionCategory.PENDING,
        "fcr_eligible": False,
        "description": "Agent or customer needs to follow up",
    },
    {
        "code": "CALLBACK_SCHEDULED",
        "label": "Callback Scheduled",
        "category": DispositionCategory.PENDING,
        "fcr_eligible": False,
        "description": "Agent scheduled callback with customer",
    },
    {
        "code": "AWAITING_PARTS",
        "label": "Awaiting Parts/Inventory",
        "category": DispositionCategory.PENDING,
        "fcr_eligible": False,
        "description": "Resolution pending inventory or parts availability",
    },

    # === ESCALATED (FCR = No - transferred to another team) ===
    {
        "code": "ESCALATED_SUPERVISOR",
        "label": "Escalated to Supervisor",
        "category": DispositionCategory.ESCALATED,
        "fcr_eligible": False,
        "description": "Call escalated to supervisor or manager",
    },
    {
        "code": "ESCALATED_TECHNICAL",
        "label": "Escalated to Technical Support",
        "category": DispositionCategory.ESCALATED,
        "fcr_eligible": False,
        "description": "Call transferred to technical support team",
    },
    {
        "code": "TRANSFERRED_DEPARTMENT",
        "label": "Transferred to Another Department",
        "category": DispositionCategory.ESCALATED,
        "fcr_eligible": False,
        "description": "Call transferred to different department",
    },

    # === NO RESOLUTION (FCR = No - could not resolve) ===
    {
        "code": "CUSTOMER_DISCONNECTED",
        "label": "Customer Disconnected",
        "category": DispositionCategory.NO_RESOLUTION,
        "fcr_eligible": False,
        "description": "Customer hung up before resolution",
    },
    {
        "code": "UNABLE_TO_RESOLVE",
        "label": "Unable to Resolve",
        "category": DispositionCategory.NO_RESOLUTION,
        "fcr_eligible": False,
        "description": "Agent unable to resolve issue on this call",
    },
    {
        "code": "WRONG_NUMBER",
        "label": "Wrong Number",
        "category": DispositionCategory.NO_RESOLUTION,
        "fcr_eligible": False,
        "description": "Caller reached wrong department or company",
    },
]

# Helper lookups for fast access
DISPOSITION_CODE_MAP = {d["code"]: d for d in DISPOSITION_CODES}
RESOLUTION_DISPOSITION_CODES = {d["code"] for d in DISPOSITION_CODES if d["fcr_eligible"]}
