#!/bin/sh
# Appimo installer.
#
#   curl -fsSL https://appimo.vercel.app/install.sh | sh
#
# Installs the `appimo` command into an isolated environment using whichever
# Python tool installer you already have. It never uses sudo, never writes
# outside your home directory, and prints everything before it does it.
#
# By default it installs straight from the GitHub repository, so it works
# before a PyPI release exists:
#
#   sh install.sh --dry-run        print the plan, change nothing
#   sh install.sh --uninstall      remove appimo again
#   sh install.sh --version 0.1.0  pin a tag from the repository
#   sh install.sh --no-gui         skip the graphical interface (Flet)
#   sh install.sh --pypi           install from PyPI instead of GitHub
#
# Environment:
#   APPIMO_PIP_ARGS   extra arguments for the install command
#   NO_COLOR          disable colour

set -eu

PKG="appimo"
REPO_URL="https://github.com/Shadow-457/appimo.git"
SOURCE="git"
VERSION=""
DRY_RUN=0
UNINSTALL=0
WITH_GUI=1
PYPI="${APPIMO_INDEX_URL:-https://pypi.org/simple}"

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m')
    GREEN=$(printf '\033[32m'); YELLOW=$(printf '\033[33m')
    RED=$(printf '\033[31m'); RESET=$(printf '\033[0m')
else
    BOLD=""; DIM=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

say()  { printf '%s\n' "$*"; }
step() { printf '  %s%s%s%s\n' "$DIM" "$1" "$RESET" ""; }
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$1" >&2; }
die()  { printf 'appimo: %s%s%s\n' "$RED" "$1" "$RESET" >&2; [ $# -gt 1 ] && printf '        %s%s%s\n' "$DIM" "$2" "$RESET" >&2; exit 1; }

# A literal usage block, not a `sed` of this file: when the script arrives on
# stdin (curl | sh) there is no $0 to read back.
usage() {
    cat <<'USAGE'
Appimo installer.

  curl -fsSL https://appimo.vercel.app/install.sh | sh

Installs the `appimo` command — including the graphical interface — using
whichever Python tool installer you already have (uv, pipx or pip). It never
uses sudo and never writes outside your home directory. Default source is the
GitHub repository.

  --dry-run        print the plan, change nothing
  --uninstall      remove appimo again
  --no-gui         skip the graphical interface (Flet)
  --with-gui       kept for compatibility; the GUI is included by default
  --version X      pin a repository tag (vX)
  --pypi           install from PyPI instead of GitHub
  -h, --help       this text
USAGE
    exit 0
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)     usage ;;
        --dry-run)     DRY_RUN=1 ;;
        --uninstall|--remove) UNINSTALL=1 ;;
        --no-gui)      WITH_GUI=0 ;;
        --with-gui)    WITH_GUI=1 ;;
        --pypi)        SOURCE="pypi" ;;
        --version)     shift; [ $# -gt 0 ] || die "--version needs a value"; VERSION="$1" ;;
        --version=*)   VERSION="${1#--version=}" ;;
        *)             die "unknown option: $1" "run with --help" ;;
    esac
    shift
done

# What gets handed to the installer: a PyPI requirement, or a git URL that
# works with no release published at all. A --version pin means a repo tag.
case "$SOURCE" in
    git)  TARGET="git+$REPO_URL"
          [ -n "$VERSION" ] && TARGET="git+$REPO_URL@v$VERSION" ;;
    pypi) TARGET="$PKG"
          [ -n "$VERSION" ] && TARGET="$PKG==$VERSION" ;;
esac

# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------

[ "$(uname -s)" = "Linux" ] || die "Appimo is for Linux" "found: $(uname -s)"

if [ "$(id -u)" = "0" ]; then
    die "refusing to run as root" \
        "Appimo installs into your home directory; root would put files there owned by root"
fi

if ! command -v unsquashfs >/dev/null 2>&1; then
    warn "unsquashfs not found — Appimo will have to run bundles to read them"
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release 2>/dev/null || true
        case "${ID:-}${ID_LIKE:-}" in
            *debian*|*ubuntu*) warn "install it with: sudo apt install squashfs-tools" ;;
            *fedora*|*rhel*)   warn "install it with: sudo dnf install squashfs-tools" ;;
            *arch*)            warn "install it with: sudo pacman -S squashfs-tools" ;;
            *suse*)            warn "install it with: sudo zypper install squashfs" ;;
        esac
    fi
fi

# ---------------------------------------------------------------------------
# Pick a method
# ---------------------------------------------------------------------------

METHOD=""
if command -v uv >/dev/null 2>&1; then
    METHOD="uv"
elif command -v pipx >/dev/null 2>&1; then
    METHOD="pipx"
elif command -v python3 >/dev/null 2>&1; then
    METHOD="pip"
fi

[ -n "$METHOD" ] || die "no Python installer found" \
    "install uv (https://docs.astral.sh/uv/) or pipx, then run this again"

EXTRAS=""
[ "$WITH_GUI" = "1" ] && EXTRAS="[gui]"
say "  ${DIM}gui${RESET}      $( [ "$WITH_GUI" = "1" ] && printf 'yes' || printf 'no (--no-gui to skip it)' )"

case "$METHOD" in
    uv)   INSTALL_CMD="uv tool install --force"; UNINSTALL_CMD="uv tool uninstall";   ;;
    pipx) INSTALL_CMD="pipx install --force";      UNINSTALL_CMD="pipx uninstall" ;;
    pip)  INSTALL_CMD="python3 -m pip install --user"; UNINSTALL_CMD="python3 -m pip uninstall -y" ;;
esac
# --force means re-running this script upgrades an existing install (or adds
# the GUI to one) instead of failing with "already installed".

run() {
    if [ "$DRY_RUN" = "1" ]; then
        step "would run: $*"
    else
        step "$*"
        "$@"
    fi
}

say ""
say "${BOLD}Appimo${RESET} — turn any AppImage into a real application"
say ""

if [ "$UNINSTALL" = "1" ]; then
    say "  ${DIM}method${RESET}   $METHOD"
    # shellcheck disable=SC2086
    run $UNINSTALL_CMD "$PKG"
    say ""
    ok "Removed Appimo"
    say "  ${DIM}Your integrated applications were left alone;${RESET}"
    say "  ${DIM}remove them with 'appimo remove' first if you want them gone.${RESET}"
    exit 0
fi

say "  ${DIM}method${RESET}   $METHOD"
say "  ${DIM}package${RESET}  ${TARGET}${EXTRAS}"
if [ "$SOURCE" = "pypi" ]; then
    say "  ${DIM}index${RESET}    $PYPI"
else
    say "  ${DIM}source${RESET}   GitHub (main)"
fi
say ""

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

if [ "$METHOD" = "pip" ]; then
    warn "pipx or uv install the command in isolation; pip --user does not"
fi

# shellcheck disable=SC2086
if [ -n "${APPIMO_PIP_ARGS:-}" ]; then
    # shellcheck disable=SC2086
    run $INSTALL_CMD "$TARGET$EXTRAS" $APPIMO_PIP_ARGS
else
    # shellcheck disable=SC2086
    run $INSTALL_CMD "$TARGET$EXTRAS"
fi

if [ "$DRY_RUN" = "1" ]; then
    say ""
    ok "Dry run — nothing was installed"
    exit 0
fi

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

if ! command -v appimo >/dev/null 2>&1; then
    warn "appimo was installed but is not on your PATH yet"
    say "  ${DIM}uv/pipx usually add ~/.local/bin — open a new shell, then run:${RESET}"
    say "  ${DIM}  appimo doctor${RESET}"
    exit 0
fi

say ""
ok "Installed $(appimo --version 2>/dev/null || echo "$PKG")"

# Put Appimo itself in the start menu (the GUI launcher). Best-effort: a
# headless shell has no applications dir and should not fail the install.
if [ "$WITH_GUI" = "1" ]; then
    if step "appimo menu" && appimo menu >/dev/null 2>&1; then
        ok "Added Appimo to your start menu"
    else
        warn "could not add the start-menu entry; run 'appimo menu' later"
    fi
fi

say ""
say "  ${BOLD}Next${RESET}"
say "    ${DIM}1.${RESET} appimo doctor                      ${DIM}# check the environment${RESET}"
say "    ${DIM}2.${RESET} appimo install ~/Downloads/Some.AppImage"
if [ "$WITH_GUI" = "1" ]; then
    say "    ${DIM}3.${RESET} Open ${BOLD}Appimo${RESET} from your start menu  ${DIM}# or: appimo gui${RESET}"
else
    say "    ${DIM}3.${RESET} Launch it from your start menu"
fi
say ""
if [ "$WITH_GUI" = "1" ]; then
    say "  ${DIM}Terminal only? re-run with --no-gui${RESET}"
    say ""
else
    say "  ${DIM}Want a window instead of a terminal? re-run with --with-gui${RESET}"
    say ""
fi
