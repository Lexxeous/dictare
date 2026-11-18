#!/usr/bin/env bash
# Run Dictare from this checkout without using the Homebrew-installed command.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${DICTARE_DEV_PYTHON:-$ROOT_DIR/.venv/bin/python}"
DEV_DIR="$ROOT_DIR/.dictare-dev"
DEV_CONFIG="$DEV_DIR/config.toml"
API_PORT="${DICTARE_DEV_API_PORT:-18770}"
UI_PORT="${DICTARE_DEV_UI_PORT:-5173}"
API_URL="http://127.0.0.1:${API_PORT}"

usage() {
    cat <<'EOF'
Run Dictare directly from this checkout, separate from an installed release.

Usage: ./scripts/dev.sh
  setup [--mlx]       Install the local Python and UI environments
  run [DICTARE_ARGS…] Run the local Dictare CLI
  serve [ARGS…]       Run the local engine on port 18770
  ui                  Run the local settings UI on port 5173
  stack               Run the local engine and UI together
  app                 Build and open the isolated macOS source preview
  listen              Start listening on the local engine
  pause               Stop listening on the local engine
  stop                Stop the verified local source engine
  hotkey              Simulate one source hotkey tap (no global shortcut)
  test [PYTEST_ARGS…] Run the repository tests
  lint                Run Ruff on source and tests
  typecheck           Run mypy on source
  build-ui            Build the local settings UI

Optional setup flag:
  --mlx                                  Include the Apple Silicon MLX extra

The source runner uses this checkout's .venv and .dictare-dev/ state. It does
not invoke the `dictare` executable from PATH or manage installed services.
EOF
}

error() {
    printf 'Error: %s\n' "$1" >&2
    exit 2
}

require_python() {
    if [[ ! -x "$VENV_PYTHON" ]]; then
        error "Local environment not found. Run ./scripts/dev.sh setup first."
    fi
}

require_ui_dependencies() {
    if [[ ! -d "$ROOT_DIR/ui/node_modules" ]]; then
        error "UI dependencies not found. Run ./scripts/dev.sh setup first."
    fi
    if [[ ! -f "$ROOT_DIR/ui/node_modules/.pnpm/lock.yaml" ]] || ! cmp -s "$ROOT_DIR/ui/pnpm-lock.yaml" "$ROOT_DIR/ui/node_modules/.pnpm/lock.yaml"; then
        error "UI dependencies are out of date. Run ./scripts/dev.sh setup after dependency changes."
    fi
}

prepare_local_environment() {
    mkdir -p "$DEV_DIR"
    if [[ ! -f "$DEV_CONFIG" && -f "$HOME/.config/dictare/config.toml" ]]; then
        cp "$HOME/.config/dictare/config.toml" "$DEV_CONFIG"
        printf 'Copied your current settings into %s for local use.\n' "$DEV_CONFIG"
    fi
    if [[ ! -f "$DEV_CONFIG" ]]; then
        printf '# Local source settings\n' > "$DEV_CONFIG"
    fi

    export DICTARE_DEV_MODE=1
    export DICTARE_DEV_CHECKOUT="$ROOT_DIR"
    require_python
    export DICTARE_DEV_VERSION
    DICTARE_DEV_VERSION="$(cd "$ROOT_DIR" && "$VENV_PYTHON" scripts/release_plan.py --local-version)"
    export DICTARE_CONFIG_PATH="$DEV_CONFIG"
    export DICTARE_RUNTIME_DIR="$DEV_DIR/runtime"
    export DICTARE_DATA_DIR="$DEV_DIR/data"
    export DICTARE_SERVER_PORT="$API_PORT"
    export DICTARE_SERVER_HOST=127.0.0.1
    export DICTARE_CLIENT_URL="$API_URL/openvip"
    export DICTARE_API_TARGET="$API_URL"
    export DICTARE_HOTKEY_TRANSPORT=none
    export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
    printf 'Dictare SOURCE %s: %s | engine %s | UI http://127.0.0.1:%s/ui/\n' "$DICTARE_DEV_VERSION" "$ROOT_DIR" "$API_URL" "$UI_PORT" >&2
}

run_cli() {
    require_python
    prepare_local_environment

    case "${1:-}" in
        setup|service|uninstall|upgrade|rollback|install|tray|repair)
            error "'$1' manages an installed service or runtime; use the installed Dictare command for lifecycle management."
            ;;
    esac

    exec "$VENV_PYTHON" -m dictare "$@"
}

run_serve() {
    require_python
    prepare_local_environment
    exec "$VENV_PYTHON" "$ROOT_DIR/scripts/dev_process.py" --restart-on 75 -- "$VENV_PYTHON" -m dictare serve --config "$DEV_CONFIG" "$@"
}

run_ui() {
    require_ui_dependencies
    prepare_local_environment
    cd "$ROOT_DIR/ui"
    exec "$VENV_PYTHON" "$ROOT_DIR/scripts/dev_process.py" -- npm run dev -- --host 127.0.0.1 --port "$UI_PORT" --strictPort "$@"
}

run_stack() {
    require_python
    require_ui_dependencies
    prepare_local_environment
    if "$VENV_PYTHON" "$ROOT_DIR/scripts/dev_control.py" "$API_URL" probe; then
        error "Port $API_PORT is already in use. If a source engine is running, use ./scripts/dev.sh stop or stop its terminal. Otherwise choose another DICTARE_DEV_API_PORT."
    fi

    local engine_pid ui_pid status
    "$VENV_PYTHON" "$ROOT_DIR/scripts/dev_process.py" --restart-on 75 -- "$VENV_PYTHON" -m dictare serve --config "$DEV_CONFIG" --verbose &
    engine_pid=$!
    (
        cd "$ROOT_DIR/ui"
        exec "$VENV_PYTHON" "$ROOT_DIR/scripts/dev_process.py" -- npm run dev -- --host 127.0.0.1 --port "$UI_PORT" --strictPort
    ) &
    ui_pid=$!

    cleanup() {
        kill "$engine_pid" "$ui_pid" 2>/dev/null || true
        wait "$engine_pid" 2>/dev/null || true
        wait "$ui_pid" 2>/dev/null || true
    }
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    while kill -0 "$engine_pid" 2>/dev/null && kill -0 "$ui_pid" 2>/dev/null; do
        sleep 1
    done

    if ! kill -0 "$engine_pid" 2>/dev/null; then
        if wait "$engine_pid"; then
            status=0
        else
            status=$?
        fi
    elif wait "$ui_pid"; then
        status=0
    else
        status=$?
    fi

    exit "$status"
}

set_local_listening() {
    require_python
    prepare_local_environment
    "$VENV_PYTHON" "$ROOT_DIR/scripts/dev_control.py" "$API_URL" "$1"
}

command_name="${1:-help}"
if [[ $# -gt 0 ]]; then
    shift
fi

case "$command_name" in
    help|-h|--help)
        usage
        ;;
    setup)
        mlx_flag=""
        if [[ "${1:-}" == "--mlx" ]]; then
            mlx_flag="--extra mlx"
            shift
        fi
        [[ $# -eq 0 ]] || error "Unexpected setup argument: $1"
        command -v uv >/dev/null 2>&1 || error "Install uv before setting up the local Python environment."
        command -v npm >/dev/null 2>&1 || error "Install Node.js and npm before setting up the local settings UI."
        if [[ "$mlx_flag" == "--extra mlx" ]]; then
            (cd "$ROOT_DIR" && uv sync --locked --python 3.11 --extra dev --extra mlx)
        else
            (cd "$ROOT_DIR" && uv sync --locked --python 3.11 --extra dev)
        fi
        (cd "$ROOT_DIR/ui" && npx --yes pnpm@10.34.9 install --frozen-lockfile)
        printf '\nLocal source environment is ready. Run ./scripts/dev.sh stack.\n'
        ;;
    run|cli)
        run_cli "$@"
        ;;
    serve)
        run_serve "$@"
        ;;
    ui)
        run_ui "$@"
        ;;
    stack)
        [[ $# -eq 0 ]] || error "The stack command does not accept extra arguments. Set DICTARE_DEV_API_PORT or DICTARE_DEV_UI_PORT to change ports."
        run_stack
        ;;
    app)
        [[ $# -eq 0 ]] || error "The app command does not accept arguments."
        [[ "$(uname -s)" == Darwin ]] || error "The source preview requires macOS."
        require_python
        "$VENV_PYTHON" - <<'PY'
import time
from AppKit import NSRunningApplication

apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_("dev.dragfly.dictare.preview")
for app in apps:
    app.terminate()
for _ in range(50):
    if not NSRunningApplication.runningApplicationsWithBundleIdentifier_("dev.dragfly.dictare.preview"):
        break
    time.sleep(0.1)
else:
    raise SystemExit("Could not stop the existing source preview; close it and try again.")
PY
        preview="$DEV_DIR/Dictare Preview.app"
        mkdir -p "$preview/Contents/MacOS" "$preview/Contents/Resources"
        swiftc -O -o "$preview/Contents/MacOS/DictarePreview" "$ROOT_DIR/src/dictare/resources/launcher.swift"
        cp "$ROOT_DIR/src/dictare/resources/Dictare.icns" "$preview/Contents/Resources/Dictare.icns"
        "$VENV_PYTHON" - "$preview/Contents/Info.plist" <<'PY'
import plistlib
import sys

with open(sys.argv[1], "wb") as output:
    plistlib.dump({"CFBundleIdentifier": "dev.dragfly.dictare.preview",
                   "CFBundleName": "Dictare Preview",
                   "CFBundleExecutable": "DictarePreview",
                   "CFBundlePackageType": "APPL",
                   "CFBundleIconFile": "Dictare.icns",
                   "LSUIElement": True}, output)
PY
        codesign --force --deep --sign - "$preview"
        open -a "$preview" --args --source-preview
        printf 'Source preview started. Use Continue in the app in the local UI.\n'
        ;;
    stop)
        [[ $# -eq 0 ]] || error "The stop command does not accept arguments."
        set_local_listening engine.shutdown
        ;;
    hotkey)
        [[ $# -eq 0 ]] || error "The hotkey command does not accept arguments."
        set_local_listening dev.hotkey
        ;;
    listen|pause)
        [[ $# -eq 0 ]] || error "The $command_name command does not accept extra arguments."
        if [[ "$command_name" == "listen" ]]; then
            set_local_listening stt.start
        else
            set_local_listening stt.stop
        fi
        ;;
    test)
        require_python
        cd "$ROOT_DIR"
        export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
        exec "$VENV_PYTHON" -m pytest tests/ -x --tb=short "$@"
        ;;
    lint)
        require_python
        cd "$ROOT_DIR"
        exec "$VENV_PYTHON" -m ruff check src/ tests/ scripts/release_plan.py scripts/dev_process.py scripts/dev_control.py "$@"
        ;;
    typecheck)
        require_python
        cd "$ROOT_DIR"
        exec "$VENV_PYTHON" -m mypy src/ "$@"
        ;;
    build-ui)
        require_ui_dependencies
        cd "$ROOT_DIR/ui"
        exec npm run build -- "$@"
        ;;
    *)
        error "Unknown command '$command_name'. Run ./scripts/dev.sh --help."
        ;;
esac
