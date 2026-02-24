#!/usr/bin/env bash
#
# Setup Environment Variables
# Fetches secrets from AWS Secrets Manager and exports them to environment
#
# Usage:
#   source setup_env.sh prod
#   source setup_env.sh qa
#
# Pattern from: /Users/xnxn040/PycharmProjects/grainger-chat-v2/env_utils/load_qa_env_vars.sh

set -e

ENVIRONMENT="${1:-prod}"  # Default to prod (better data for MCP RAG resources)

if [[ "$ENVIRONMENT" != "prod" && "$ENVIRONMENT" != "qa" ]]; then
    echo "❌ Error: Environment must be 'prod' or 'qa'"
    echo "Usage: source setup_env.sh [prod|qa]"
    return 1 2>/dev/null || exit 1
fi

echo "🔐 Loading environment variables for: $ENVIRONMENT"

# Check AWS credentials
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                  AWS CREDENTIALS REQUIRED                        ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "❌ No valid AWS credentials found!"
    echo ""
    echo "🔧 You MUST run the following commands first:"
    echo ""
    echo "   1. assume"
    echo ""
    echo "   2. Run: assume aad-mlops-prod-digitalassistantdo"
    if [[ "$ENVIRONMENT" == "qa" ]]; then
        echo "      (For QA: assume aad-mlops-nonprod-digitalassistantdo)"
    fi
    echo ""
    echo "   3. Then source this script again:"
    echo "      source setup_env.sh $ENVIRONMENT"
    echo ""
    return 1 2>/dev/null || exit 1
fi

# List of AWS Secrets Manager secret IDs to fetch
if [[ "$ENVIRONMENT" == "prod" ]]; then
    aws_secrets=(
        "digitalassistantdomain/prod/openai_key_list"
        "digitalassistantdomain/prod/mcp-secret"
    )
else
    aws_secrets=(
        "digitalassistantdomain/qa/openai_key_list"
        "digitalassistantdomain/qa/mcp-secret"
    )
fi

openai_key_list_json=""
for secret_id in "${aws_secrets[@]}"; do
    echo "🔸 Fetching $secret_id..."
    secret_json=$(aws secretsmanager get-secret-value \
        --secret-id "$secret_id" \
        --region us-east-2 \
        --query SecretString \
        --output text 2>/dev/null || true)

    if [[ -n "$secret_json" ]]; then
        # Capture the OpenAI key list JSON for specialized handling
        if [[ "$secret_id" == *"/openai_key_list" ]]; then
            openai_key_list_json="$secret_json"
        else
            # Generic export for other secrets (like mcp-secret)
            while IFS="=" read -r key val; do
                val="${val%\"}"
                val="${val#\"}"
                export "$key"="$val"
                echo "✅ Exported: $key"
            done < <(echo "$secret_json" | jq -r 'to_entries|map("\(.key)=\(.value|tostring)")|.[]')
        fi
    else
        echo "⚠️  Warning: Could not fetch AWS secret: $secret_id"
    fi
done

# DRY function to prompt for manual secret entry
prompt_manual_secret() {
    local secret_name="$1"
    local secret_description="$2"
    local features_affected="$3"

    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║     $secret_name NOT AVAILABLE FROM AWS                          "
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "⚠️  Could not retrieve $secret_name from AWS Secrets Manager"
    echo ""
    echo "This could mean:"
    echo "  • Your AWS credentials don't have access to the secret"
    echo "  • The secret doesn't exist in this environment"
    echo "  • Network/permissions issue"
    echo ""
    read -p "🔑 Would you like to enter $secret_description manually? (y/n): " manual_input

    if [[ "$manual_input" =~ ^[Yy]$ ]]; then
        read -p "Enter your $secret_description: " manual_value
        if [[ -n "$manual_value" ]]; then
            export "$secret_name"="$manual_value"
            echo "✅ Exported: $secret_name (manually entered)"
            return 0
        else
            echo "❌ No key provided. $features_affected will not work."
            return 1
        fi
    else
        echo "⚠️  Skipping $secret_name. $features_affected will not work."
        return 1
    fi
}

# Map OpenAI key list: Use OPENAI_CSCDA_NONPROD_API for this project (works for both qa and prod)
openai_key_retrieved=false
if [[ -n "$openai_key_list_json" ]] && echo "$openai_key_list_json" | jq -e . >/dev/null 2>&1; then
    echo "🔧 Mapping OpenAI keys for $ENVIRONMENT..."

    # Use OPENAI_CSCDA_NONPROD_API for both qa and prod environments
    # (This is the standard key for DA projects as specified by user)
    api_key=$(echo "$openai_key_list_json" | jq -r '.OPENAI_CSCDA_NONPROD_API // empty')

    if [[ -n "$api_key" ]]; then
        export OPENAI_API_KEY="$api_key"
        echo "✅ Exported: OPENAI_API_KEY (from OPENAI_CSCDA_NONPROD_API)"
        openai_key_retrieved=true
    else
        echo "⚠️  Warning: OPENAI_CSCDA_NONPROD_API not found in openai_key_list JSON"
        echo "Available keys: $(echo "$openai_key_list_json" | jq -r 'keys | join(", ")')"
    fi
fi

# Fallback: Prompt for manual key entry if AWS retrieval failed
if [[ "$openai_key_retrieved" == "false" ]]; then
    prompt_manual_secret "OPENAI_API_KEY" "OpenAI API key (starts with sk-)" "ACW features (disposition, compliance, CRM extraction)"
fi

# Check MCP_SECRET_KEY and prompt if missing
if [[ -z "$MCP_SECRET_KEY" ]]; then
    prompt_manual_secret "MCP_SECRET_KEY" "MCP secret key" "MCP RAG features"
fi

# Set environment marker
export ENVIRONMENT="$ENVIRONMENT"
echo "✅ Exported: ENVIRONMENT=$ENVIRONMENT"

echo ""
echo "✅ Environment variables loaded successfully!"
echo ""
echo "You can now start the application:"
echo "  uv run uvicorn app.main:app --reload"
echo ""
