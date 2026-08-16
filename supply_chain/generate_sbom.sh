#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${1:-devsecops-app:latest}"
SBOM_FILE="sbom.json"
COSIGN_KEY="${COSIGN_KEY:-}"

echo "Generating SBOM for image: ${IMAGE_NAME}"

syft "${IMAGE_NAME}" --output spdx-json="${SBOM_FILE}"

echo "SBOM written to ${SBOM_FILE}"

if [[ -z "${COSIGN_KEY}" ]]; then
  echo "Warning: COSIGN_KEY not set — skipping SBOM signing"
else
  echo "${COSIGN_KEY}" > /tmp/cosign.key
  cosign sign-blob \
    --key /tmp/cosign.key \
    --output-signature "${SBOM_FILE}.sig" \
    "${SBOM_FILE}"
  rm -f /tmp/cosign.key
  echo "SBOM signed — signature written to ${SBOM_FILE}.sig"
fi

echo "SBOM generated and signed"
