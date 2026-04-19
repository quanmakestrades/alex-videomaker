#!/usr/bin/env bash
# videomaker CLI entry shim.
# This is the version used inside the skill directory during dev.
# `setup.sh` installs a copy to /usr/local/bin (or ~/.local/bin).
exec python3 -m videomaker.cli "$@"
