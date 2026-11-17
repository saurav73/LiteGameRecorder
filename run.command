#!/bin/sh
# macOS double-click launcher: opens Terminal and runs run.sh.
cd "$(dirname "$0")" || exit 1
exec ./run.sh
