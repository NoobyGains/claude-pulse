#!/usr/bin/env sh
set -eu

REPO_SLUG="NoobyGains/claude-pulse"
REPO_URL="https://github.com/${REPO_SLUG}.git"
RAW_BASE_URL="https://raw.githubusercontent.com/${REPO_SLUG}/main"

INSTALL_DIR="${CLAUDE_PULSE_DIR:-$HOME/.claude-pulse}"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
COMMANDS_DIR="${CLAUDE_DIR}/commands"

INSTALL_METHOD=""

log() {
  printf '%s\n' "$*"
}

die() {
  log "claude-pulse installer: $*"
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
  download_file "$RAW_BASE_URL/pulse.md" "$INSTALL_DIR/pulse.md"
  INSTALL_METHOD="raw"
}

install_repo() {
  if has_cmd git; then
    if [ -d "$INSTALL_DIR/.git" ]; then
      origin_url="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || true)"
      origin_lc="$(printf '%s' "$origin_url" | tr '[:upper:]' '[:lower:]')"
      case "$origin_lc" in
        *noobygains/claude-pulse|*noobygains/claude-pulse.git)
          log "Updating existing claude-pulse clone..."
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
      die "directory already exists and is not a claude-pulse install: $INSTALL_DIR"
    fi

    install_parent="${INSTALL_DIR%/*}"
    if [ "$install_parent" != "$INSTALL_DIR" ]; then
      mkdir -p "$install_parent"
    fi

    log "Cloning claude-pulse..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" >/dev/null 2>&1 || die "failed to clone repository"
    INSTALL_METHOD="git"
    return
  fi

  log "git not found, downloading scripts directly..."
  install_from_raw
}

run_python_install() {
  if has_cmd python3; then
    python3 "$INSTALL_DIR/claude_status.py" --install
    return
  fi

  if has_cmd python; then
    python "$INSTALL_DIR/claude_status.py" --install
    return
  fi

  die "Python 3 is required. Install Python, then run this installer again."
}

install_pulse_command() {
  if [ -f "$INSTALL_DIR/pulse.md" ]; then
    mkdir -p "$COMMANDS_DIR"
    cp "$INSTALL_DIR/pulse.md" "$COMMANDS_DIR/pulse.md"
  fi
}

install_repo
install_pulse_command
run_python_install

log ""
log "claude-pulse installed in: $INSTALL_DIR"
log "Restart Claude Code, then run /pulse to configure your status bar."

if [ "$INSTALL_METHOD" = "raw" ]; then
  log "Note: installed without git. /pulse update expects a git clone."
fi
