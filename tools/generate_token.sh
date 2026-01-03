#!/bin/bash
#
# Generate a secure API token for QuantumDB authentication
#
# This script generates a cryptographically secure random token
# suitable for use with the QuantumDB API authentication system.
#
# The token is 32+ characters and contains only alphanumeric
# characters plus hyphens and underscores, as required by the
# authentication middleware.
#
# Usage:
#   ./generate_token.sh
#
# The generated token will be printed to stdout.

# Check if openssl is available
if ! command -v openssl &> /dev/null; then
    echo "Error: openssl is required but not installed." >&2
    echo "Please install openssl and try again." >&2
    exit 1
fi

# Generate a 32-byte random token and encode it in base64
# The output will be 44 characters (base64 encoding of 32 bytes)
# We remove the trailing '=' padding and any slashes/pluses for URL safety
TOKEN=$(openssl rand -base64 32 | tr -d '=/' | tr '+' '-')

echo "Generated API token (save this securely):"
echo "$TOKEN"
echo ""
echo "Add this to your docker-compose.yml or .env file:"
echo "API_TOKENS=$TOKEN"
echo ""
echo "For multiple users, separate tokens with commas:"
echo "API_TOKENS=$TOKEN,another-token-here"
