#!/usr/bin/env bash
# Run Dictare from this checkout without using the Homebrew-installed command.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
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
  listen              Start listening on the local engine
  pause               Stop listening on the local engine
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
    exec "$VENV_PYTHON" -m dictare serve --config "$DEV_CONFIG" "$@"
}

run_ui() {
    require_ui_dependencies
    prepare_local_environment
    cd "$ROOT_DIR/ui"
    exec npm run dev -- --host 127.0.0.1 --port "$UI_PORT" --strictPort "$@"
}

run_stack() {
    require_python
    require_ui_dependencies
    prepare_local_environment

    local engine_pid ui_pid status
    "$VENV_PYTHON" -m dictare serve --config "$DEV_CONFIG" --verbose &
    engine_pid=$!
    (
        cd "$ROOT_DIR/ui"
        exec npm run dev -- --host 127.0.0.1 --port "$UI_PORT" --strictPort
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
    "$VENV_PYTHON" - "$API_URL" "$1" <<'PY'
import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

request = Request(
    sys.argv[1] + "/openvip/control",
    data=json.dumps({"command": sys.argv[2]}).encode(),
    headers={"Content-Type": "application/json"},
)
try:
    with urlopen(request, timeout=5) as response:
        print(response.read().decode())
except URLError as error:
    raise SystemExit(f"Cannot reach the local source engine. Start ./scripts/dev.sh stack: {error}")
PY
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
        exec "$VENV_PYTHON" -m ruff check src/ tests/ "$@"
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
