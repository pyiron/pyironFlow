#!/usr/bin/env bash
# Rebuild the pyironFlow JS bundle from local sources.
#
#   ./dev-build.sh              rebuild pyironflow/static/{widget.js,widget.css}
#   ./dev-build.sh --clean      wipe node_modules + static first, then rebuild
#   ./dev-build.sh --watch      rebuild continuously on every .jsx/.css save
#   ./dev-build.sh --install    also (re)do the editable Python install
#   ./dev-build.sh --update     bump JS deps within package.json ranges (rewrites package-lock.json)
#
# After a build, restart the Jupyter kernel. anywidget ships the bundle as a
# synced traitlet over the kernel comm (not over HTTP), and caches the file
# contents for the life of the import -- so the kernel is what holds it stale,
# not the browser. No page reload needed. Set ANYWIDGET_HMR=1 with --watch to
# skip the restart too; this needs `watchfiles` in the kernel's environment
# (e.g. `pip install -e ".[dev]"`).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

CLEAN=0
WATCH=0
INSTALL=0
UPDATE=0

for arg in "$@"; do
    case "$arg" in
        --clean)   CLEAN=1 ;;
        --watch)   WATCH=1 ;;
        --install) INSTALL=1 ;;
        --update)  UPDATE=1 ;;
        -h|--help) sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^#//; s/^ //'; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --- 1. is the Python side even pointing at this checkout? ------------------
check_python_import() {
    local found
    found="$(python - <<'PY' 2>/dev/null || true
import importlib.util, os
spec = importlib.util.find_spec("pyironflow")
print(os.path.realpath(os.path.dirname(spec.origin)) if spec and spec.origin else "")
PY
)"
    local expected
    expected="$(python -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$REPO/pyironflow")"

    if [[ -z "$found" ]]; then
        echo "!! 'pyironflow' is not importable in this environment."
        echo "   Run: ./dev-build.sh --install"
    elif [[ "$found" != "$expected" ]]; then
        echo "!! 'import pyironflow' resolves to the INSTALLED copy, not this checkout:"
        echo "     $found"
        echo "   Your local JS build will not be picked up. Fix with:"
        echo "     ./dev-build.sh --install"
    else
        echo "ok: 'import pyironflow' -> $found"
    fi
}

# --- 2. optional editable install -------------------------------------------
if [[ $INSTALL -eq 1 ]]; then
    say "Editable install (shadows the conda-forge build)"
    # --no-deps: leave the conda-managed runtime deps alone.
    # Add --no-build-isolation if you are offline and hatchling/hatch-vcs
    # are already in the env.
    # The build hook (hatch_build.py) runs `npm ci && npm run build` only if
    # pyironflow/static/widget.js is missing; otherwise the existing bundle is kept.
    pip install -e . --no-deps
fi

# --- 3. clean ---------------------------------------------------------------
if [[ $CLEAN -eq 1 ]]; then
    say "Cleaning node_modules/ and pyironflow/static/"
    rm -rf node_modules pyironflow/static
fi

# --- 4. node deps -----------------------------------------------------------
if [[ $UPDATE -eq 1 ]]; then
    say "npm update  (within package.json ranges; rewrites package-lock.json)"
    npm update
elif [[ $CLEAN -eq 1 ]]; then
    say "npm ci  (exact install from package-lock.json)"
    npm ci
else
    say "npm install"
    npm install
fi

# --- 5. bundle --------------------------------------------------------------
if [[ $WATCH -eq 1 ]]; then
    check_python_import
    if [[ "${ANYWIDGET_HMR:-}" == "1" ]]; then
        echo "ok: ANYWIDGET_HMR=1 -- saves hot-reload into the running kernel"
        if ! python -c "import watchfiles" 2>/dev/null; then
            echo "!! 'watchfiles' is not importable; anywidget cannot watch the bundle"
            echo "   and hot reload will silently not happen. Fix with:"
            echo "     pip install watchfiles"
        fi
    else
        echo "note: ANYWIDGET_HMR is not 1, so you still need a kernel restart"
        echo "      per rebuild. Export it before starting the Jupyter server"
        echo "      (PyCharm: set it in the run configuration environment)."
    fi
    say "npm run dev  (esbuild --watch, inline sourcemaps; Ctrl-C to stop)"
    exec npm run dev
fi

say "npm run build"
npm run build

# --- 6. verify --------------------------------------------------------------
say "Build output"
for f in pyironflow/static/widget.js pyironflow/static/widget.css; do
    if [[ -f "$f" ]]; then
        echo "  $f  ($(wc -c <"$f" | tr -d ' ') bytes)"
    else
        echo "  MISSING: $f" >&2
        exit 1
    fi
done

say "Python side"
check_python_import

echo
echo "Done. Restart the Jupyter kernel to pick this up (no browser reload needed)."
