#!/usr/bin/env sh
set -eu

REPO_SLUG="NoobyGains/usage-pulse"
REPO_URL="${USAGE_PULSE_REPO_URL:-${CLAUDE_PULSE_REPO_URL:-https://github.com/${REPO_SLUG}.git}}"
RAW_BASE_URL="https://raw.githubusercontent.com/${REPO_SLUG}/main"

# New installs go to ~/.usage-pulse. An install from before the rename (3.5.0)
# stays in ~/.claude-pulse, so re-running this updates it in place.
DEFAULT_DIR="$HOME/.usage-pulse"
if [ ! -e "$HOME/.usage-pulse" ] && [ -d "$HOME/.claude-pulse" ]; then
  DEFAULT_DIR="$HOME/.claude-pulse"
fi
INSTALL_DIR="${USAGE_PULSE_DIR:-${CLAUDE_PULSE_DIR:-$DEFAULT_DIR}}"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
COMMANDS_DIR="${CLAUDE_DIR}/commands"

INSTALL_METHOD=""

log() {
  printf '%s\n' "$*"
}

die() {
  log "usage-pulse installer: $*"
  exit 1
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

download_file() {
  src_url="$1"
  dst_path="$2"

  if has_cmd curl; then
    curl -fsSL "$src_url" -o "$dst_path"
    return
  fi

  if has_cmd wget; then
    wget -qO "$dst_path" "$src_url"
    return
  fi

  die "curl or wget is required when git is unavailable"
}

install_from_raw() {
  mkdir -p "$INSTALL_DIR"
  download_file "$RAW_BASE_URL/claude_status.py" "$INSTALL_DIR/claude_status.py"
  mkdir -p "$INSTALL_DIR/commands"
  download_file "$RAW_BASE_URL/commands/pulse.md" "$INSTALL_DIR/commands/pulse.md"
  INSTALL_METHOD="raw"
}

install_repo() {
  if has_cmd git; then
    if [ -d "$INSTALL_DIR/.git" ]; then
      origin_url="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || true)"
      origin_lc="$(printf '%s' "$origin_url" | tr '[:upper:]' '[:lower:]')"
      case "$origin_lc" in
        *noobygains/usage-pulse|*noobygains/usage-pulse.git|*noobygains/claude-pulse|*noobygains/claude-pulse.git)
          log "Updating existing usage-pulse clone..."
          git -C "$INSTALL_DIR" pull --ff-only origin main >/dev/null 2>&1 || die "failed to update git clone"
          INSTALL_METHOD="git"
          return
          ;;
        *)
          die "existing git repo at $INSTALL_DIR has unexpected origin: $origin_url"
          ;;
      esac
    fi

    if [ -f "$INSTALL_DIR/claude_status.py" ]; then
      log "Existing non-git install detected, refreshing files..."
      install_from_raw
      return
    fi

    if [ -d "$INSTALL_DIR" ]; then
      die "directory already exists and is not a usage-pulse install: $INSTALL_DIR"
    fi

    install_parent="${INSTALL_DIR%/*}"
    if [ "$install_parent" != "$INSTALL_DIR" ]; then
      mkdir -p "$install_parent"
    fi

    log "Cloning usage-pulse..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" >/dev/null 2>&1 || die "failed to clone repository"
    INSTALL_METHOD="git"
    return
  fi

  log "git not found, downloading scripts directly..."
  install_from_raw
}

run_python_setup() {
  if has_cmd python3; then
    PY=python3
  elif has_cmd python; then
    PY=python
  else
    die "Python 3 is required. Install Python, then run this installer again."
  fi

  # `curl | bash` leaves stdin on the pipe, so test stdout and /dev/tty
  # instead: when both work, the wizard reads real keys from /dev/tty.
  # USAGE_PULSE_NONINTERACTIVE=1 (dotfiles, CI) always takes the defaults.
  if [ -z "${USAGE_PULSE_NONINTERACTIVE:-}${CLAUDE_PULSE_NONINTERACTIVE:-}" ] && [ -t 1 ] && ( : </dev/tty ) 2>/dev/null; then
    "$PY" "$INSTALL_DIR/claude_status.py" --setup </dev/tty
  else
    "$PY" "$INSTALL_DIR/claude_status.py" --setup --non-interactive
  fi
}

install_pulse_command() {
  if [ -f "$INSTALL_DIR/commands/pulse.md" ]; then
    mkdir -p "$COMMANDS_DIR"
    cp "$INSTALL_DIR/commands/pulse.md" "$COMMANDS_DIR/pulse.md"
  fi
}

install_repo
install_pulse_command
run_python_setup

log ""
log "usage-pulse installed in: $INSTALL_DIR"
log "Restart Claude Code. Change anything later with /pulse (or /pulse setup)."

if [ "$INSTALL_METHOD" = "raw" ]; then
  log "Note: installed without git. /pulse update expects a git clone."
fi
