#!/usr/bin/env bash
# Cross-compile the Pi binary on slmbeast, deploy to thinktank.
#
# Usage: ./deploy/cross.sh [--run]
#   --run  also launch the binary on the Pi after deploy

set -euo pipefail

CRATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CRATE_DIR"

TARGET="aarch64-unknown-linux-gnu"
BIN_NAME="robotcar-pi"
BIN_PATH="target/${TARGET}/release/${BIN_NAME}"
PI_HOST="${PI_HOST:-thinktank}"
PI_BIN_DIR="${PI_BIN_DIR:-bin}"

echo ">>> cross build --target ${TARGET} --release"
cross build --target "$TARGET" --release

ls -la "$BIN_PATH"
file "$BIN_PATH"

echo ">>> scp ${BIN_PATH} → ${PI_HOST}:~/${PI_BIN_DIR}/"
ssh "$PI_HOST" "mkdir -p ~/${PI_BIN_DIR}"
scp "$BIN_PATH" "${PI_HOST}:~/${PI_BIN_DIR}/${BIN_NAME}"
ssh "$PI_HOST" "chmod +x ~/${PI_BIN_DIR}/${BIN_NAME}"

echo ">>> deployed"

if [[ "${1:-}" == "--run" ]]; then
    echo ">>> running on ${PI_HOST}"
    ssh "$PI_HOST" "~/${PI_BIN_DIR}/${BIN_NAME}"
fi
