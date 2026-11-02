#!/usr/bin/env bash
# Developer entry point. CI uses exactly the same commands, so "works on my machine" == "works in CI".
#
#   tools/dev.sh setup             clone Archipelago core and create the virtualenv
#   tools/dev.sh test [pytest...]  copy the world into Archipelago and run its test suite
#   tools/dev.sh lint              run ruff over the repository
#   tools/dev.sh build             build dist/medabots_rpg.apworld with Archipelago's own packager
#   tools/dev.sh clean             delete the local Archipelago checkout, virtualenv and build output
#
# Environment overrides:
#   AP_REF    Archipelago tag or branch to test against (default: 0.6.8, our minimum supported version)
#   AP_DIR    where the Archipelago checkout lives      (default: ./.ap-core)
#   VENV_DIR  where the virtualenv lives                (default: ./.venv)
#   PYTHON    interpreter used to create the virtualenv (default: python3)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AP_REF="${AP_REF:-0.6.8}"
AP_DIR="${AP_DIR:-$REPO_ROOT/.ap-core}"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv}"
PYTHON="${PYTHON:-python3}"
WORLD_PACKAGE="medabots_rpg"
GAME_NAME="Medabots RPG"
AP_REPO_URL="https://github.com/ArchipelagoMW/Archipelago.git"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

ensure_core() {
    if [[ -f "$AP_DIR/.dev-ref" && "$(cat "$AP_DIR/.dev-ref")" == "$AP_REF" ]]; then
        return
    fi
    log "Fetching Archipelago $AP_REF into ${AP_DIR#"$REPO_ROOT"/}"
    rm -rf "$AP_DIR"
    git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$AP_REF" "$AP_REPO_URL" "$AP_DIR"
    # Only keep the worlds we need. Every other world drags in its own third-party dependencies,
    # which would slow tests down and make them fail for reasons unrelated to this project.
    find "$AP_DIR/worlds" -mindepth 1 -maxdepth 1 -type d \
        ! -name generic ! -name _bizhawk ! -name '__pycache__' -exec rm -rf {} +
    echo "$AP_REF" > "$AP_DIR/.dev-ref"
}

ensure_venv() {
    local stamp="$VENV_DIR/.requirements.sha256"
    local want
    want="$(sha256sum "$REPO_ROOT/requirements-dev.txt" | cut -d' ' -f1)"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        log "Creating virtualenv in ${VENV_DIR#"$REPO_ROOT"/}"
        "$PYTHON" -m venv "$VENV_DIR"
    fi
    if [[ ! -f "$stamp" || "$(cat "$stamp")" != "$want" ]]; then
        log "Installing development requirements"
        "$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check -r "$REPO_ROOT/requirements-dev.txt"
        echo "$want" > "$stamp"
    fi
}

sync_world() {
    rm -rf "${AP_DIR:?}/worlds/$WORLD_PACKAGE"
    cp -R "$REPO_ROOT/worlds/$WORLD_PACKAGE" "$AP_DIR/worlds/$WORLD_PACKAGE"
    find "$AP_DIR/worlds/$WORLD_PACKAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +
}

run_in_core() {
    (cd "$AP_DIR" && SKIP_REQUIREMENTS_UPDATE=1 "$VENV_DIR/bin/python" "$@")
}

cmd_setup() { ensure_core; ensure_venv; log "Ready. Run: tools/dev.sh test"; }

cmd_test() {
    cmd_setup >/dev/null
    sync_world
    log "Running tests against Archipelago $AP_REF"
    run_in_core -m pytest "worlds/$WORLD_PACKAGE" -q -p no:cacheprovider "$@"
}

cmd_lint() {
    ensure_venv
    log "Running ruff"
    "$VENV_DIR/bin/ruff" check "$REPO_ROOT"
}

cmd_build() {
    cmd_setup >/dev/null
    sync_world
    log "Building $WORLD_PACKAGE.apworld"
    rm -rf "$AP_DIR/build/apworlds"
    run_in_core Launcher.py "Build APWorlds" -- "$GAME_NAME" --skip_open_folder
    mkdir -p "$REPO_ROOT/dist"
    cp "$AP_DIR/build/apworlds/$WORLD_PACKAGE.apworld" "$REPO_ROOT/dist/$WORLD_PACKAGE.apworld"
    log "Wrote dist/$WORLD_PACKAGE.apworld"
}

cmd_clean() { rm -rf "$AP_DIR" "$VENV_DIR" "$REPO_ROOT/dist" "$REPO_ROOT/build"; log "Cleaned."; }

case "${1:-}" in
    setup) cmd_setup ;;
    test)  shift; cmd_test "$@" ;;
    lint)  cmd_lint ;;
    build) cmd_build ;;
    clean) cmd_clean ;;
    *) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [[ -z "${1:-}" ]] || die "unknown command: $1" ;;
esac
