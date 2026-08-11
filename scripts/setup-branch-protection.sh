#!/usr/bin/env bash
# =============================================================================
# Mizan ERP — GitHub Branch Protection Setup
# =============================================================================
# Usage:
#   export GITHUB_TOKEN=ghp_your_personal_access_token
#   bash scripts/setup-branch-protection.sh
#
# The token needs: repo → Administration (write) scope.
# Create one at: https://github.com/settings/tokens/new
# =============================================================================

set -euo pipefail

OWNER="procount157-commits"
REPO="mizan-erp"
BRANCH="main"
API="https://api.github.com/repos/${OWNER}/${REPO}/branches/${BRANCH}/protection"

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GITHUB_TOKEN environment variable is not set."
  echo "  export GITHUB_TOKEN=ghp_..."
  exit 1
fi

echo "Applying branch protection to ${OWNER}/${REPO}:${BRANCH} ..."

curl -s -X PUT "${API}" \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -d '{
    "required_status_checks": {
      "strict": true,
      "contexts": ["Validate mizan_core"]
    },
    "enforce_admins": true,
    "required_pull_request_reviews": {
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": true,
      "required_approving_review_count": 1
    },
    "restrictions": null,
    "allow_force_pushes": false,
    "allow_deletions": false,
    "block_creations": false,
    "required_conversation_resolution": true
  }' | python3 -m json.tool

echo ""
echo "Done. Visit:"
echo "  https://github.com/${OWNER}/${REPO}/settings/branches"
echo "to confirm the rules are active."
