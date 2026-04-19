#!/usr/bin/env bash
# videomaker — one-shot installer.
#
# Run from the skill root:
#   bash setup.sh
#
# What it does:
#   1. Verifies Python 3.10+ and ffmpeg are installed
#   2. Creates ~/.videomaker, copies defaults
#   3. Installs Python deps (pip install -r requirements.txt --break-system-packages)
#   4. Symlinks `videomaker` into /usr/local/bin (or ~/.local/bin if /usr/local/bin not writable)
#   5. Runs `videomaker auth setup` interactively

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${VIDEOMAKER_HOME:-$HOME/.videomaker}"

echo "videomaker installer"
echo "===================="
echo "skill dir: $SKILL_DIR"
echo "home dir:  $HOME_DIR"
echo

# --- 1. Prereqs ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "[fail] python3 not found. Install Python 3.10+."
  exit 1
fi
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "[ok] python3 $PY_VER"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[fail] ffmpeg not found."
  echo "       macOS:  brew install ffmpeg"
  echo "       Linux:  sudo apt install ffmpeg"
  exit 1
fi
echo "[ok] ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "[fail] ffprobe not found. It ships with ffmpeg — reinstall ffmpeg."
  exit 1
fi
echo "[ok] ffprobe"

# --- 2. Home dir + config ---
mkdir -p "$HOME_DIR" "$HOME_DIR/runs"
if [ ! -f "$HOME_DIR/config.yaml" ]; then
  cp "$SKILL_DIR/config/defaults.yaml" "$HOME_DIR/config.yaml"
  echo "[ok] wrote $HOME_DIR/config.yaml"
else
  echo "[skip] $HOME_DIR/config.yaml already exists"
fi
if [ ! -f "$HOME_DIR/.env" ]; then
  cp "$SKILL_DIR/.env.example" "$HOME_DIR/.env"
  chmod 600 "$HOME_DIR/.env"
  echo "[ok] wrote $HOME_DIR/.env (chmod 600)"
else
  echo "[skip] $HOME_DIR/.env already exists"
fi

# --- 3. Python deps ---
echo "[install] python3 -m pip install -r requirements.txt"
if python3 -m pip install -r "$SKILL_DIR/requirements.txt" --break-system-packages 2>/dev/null; then
  echo "[ok] deps installed (system)"
elif python3 -m pip install -r "$SKILL_DIR/requirements.txt" --user; then
  echo "[ok] deps installed (user)"
else
  echo "[fail] pip install failed. Install manually: python3 -m pip install -r $SKILL_DIR/requirements.txt"
  exit 1
fi

# --- 4. Entry script on PATH ---
BIN_TARGET=""
if [ -w "/usr/local/bin" ]; then
  BIN_TARGET="/usr/local/bin/videomaker"
else
  mkdir -p "$HOME/.local/bin"
  BIN_TARGET="$HOME/.local/bin/videomaker"
fi
cat > "$BIN_TARGET" <<EOF
#!/usr/bin/env bash
exec python3 -m videomaker.cli "\$@"
EOF
chmod +x "$BIN_TARGET"
echo "[ok] installed $BIN_TARGET"

# Add skill dir to PYTHONPATH for this user (so `python3 -m videomaker.cli` finds the package)
PROFILE_LINE="export PYTHONPATH=\"$SKILL_DIR:\$PYTHONPATH\""
for rc in ~/.zshrc ~/.bashrc ~/.profile; do
  if [ -f "$rc" ]; then
    if ! grep -qF "$PROFILE_LINE" "$rc"; then
      echo "$PROFILE_LINE" >> "$rc"
      echo "[ok] added PYTHONPATH to $rc"
    fi
  fi
done

echo
echo "Installed. Next steps:"
echo "  1. Restart your shell or: export PYTHONPATH=\"$SKILL_DIR:\$PYTHONPATH\""
echo "  2. Run: videomaker auth setup"
echo "  3. Run: videomaker run --topic 'your first topic'"
