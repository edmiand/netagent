#!/usr/bin/env bash
# Fetch the latest version from GitHub and upgrade this local deployment:
#   - fast-forward pulls main (refuses to clobber local changes)
#   - syncs Python deps via `pip install -e .` (adds new deps, no-ops if unchanged)
#   - checks the local Ollama embeddings model is pulled (config/models.yaml)
#   - rebuilds the RAG knowledge base if knowledge_base/*.md changed
#   - restarts the app via webui-ctl.sh
#
# Usage: ./upgrade.sh [--dry-run] [--yes] [--no-restart]
set -uo pipefail

DRY_RUN=0
ASSUME_YES=0
NO_RESTART=0

for arg in "$@"; do
    case "$arg" in
        --dry-run)    DRY_RUN=1 ;;
        --yes|-y)     ASSUME_YES=1 ;;
        --no-restart) NO_RESTART=1 ;;
        *) echo "Usage: $0 [--dry-run] [--yes] [--no-restart]"; exit 1 ;;
    esac
done

_confirm() {
    [[ $ASSUME_YES -eq 1 ]] && return 0
    read -rp "$1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "== netagent upgrade =="

# --- 1. Preconditions -------------------------------------------------
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    echo "Not a git repository." >&2
    exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
    echo "On branch '$BRANCH', not 'main'. Switch to main before upgrading." >&2
    exit 1
fi

# Local changes to *tracked* files would block a fast-forward pull.
# (config/mcp.yaml, .env, data/chroma/, etc. are gitignored and untouched by this.)
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "Local modifications to tracked files detected:" >&2
    git status --porcelain --untracked-files=no >&2
    echo "Commit, stash, or discard them before upgrading." >&2
    exit 1
fi

echo "Fetching origin..."
git fetch origin main || { echo "git fetch failed." >&2; exit 1; }

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [[ "$LOCAL" == "$REMOTE" ]]; then
    echo "Already up to date (${LOCAL:0:12})."
    exit 0
fi

echo
echo "New commits on origin/main:"
git log --oneline "$LOCAL..$REMOTE"
echo

if [[ $DRY_RUN -eq 1 ]]; then
    echo "(dry run — stopping here, no changes made)"
    exit 0
fi

_confirm "Pull these changes and upgrade?" || { echo "Aborted."; exit 0; }

# --- 2. Stop the app before code underneath it changes -----------------
if [[ $NO_RESTART -eq 0 ]]; then
    echo "Stopping app..."
    ./webui-ctl.sh stop
fi

# --- 3. Pull (fast-forward only — refuses to create a merge commit) ----
CHANGED_FILES=$(git diff --name-only "$LOCAL" "$REMOTE")

echo "Pulling..."
if ! git pull --ff-only origin main; then
    echo "Fast-forward pull failed — resolve manually (git status)." >&2
    exit 1
fi

# --- 4. Sync Python dependencies ---------------------------------------
if echo "$CHANGED_FILES" | grep -q '^pyproject.toml$'; then
    echo "pyproject.toml changed — syncing dependencies..."
else
    echo "Syncing dependencies (no-op if nothing changed)..."
fi
.venv/bin/pip install -e . --quiet || { echo "pip install failed." >&2; exit 1; }

# --- 5. Check the local embeddings model is present ---------------------
EMBED_MODEL=$(.venv/bin/python -c "
import yaml
print(yaml.safe_load(open('config/models.yaml')).get('embeddings', {}).get('model', ''))
" 2>/dev/null)

if [[ -n "$EMBED_MODEL" ]] && command -v ollama &>/dev/null; then
    if ! ollama list | awk '{print $1}' | grep -qx "${EMBED_MODEL}:latest\|${EMBED_MODEL}"; then
        echo "Embeddings model '$EMBED_MODEL' not found locally."
        if _confirm "Pull it now (ollama pull $EMBED_MODEL)?"; then
            ollama pull "$EMBED_MODEL"
        else
            echo "Skipping — RAG knowledge base build will fail until this is pulled." >&2
        fi
    fi
fi

# --- 6. Rebuild the RAG knowledge base if its sources changed -----------
if echo "$CHANGED_FILES" | grep -q '^knowledge_base/'; then
    echo "knowledge_base/ changed — rebuilding vector store..."
    .venv/bin/python scripts/build_knowledge_base.py
fi

# --- 7. Restart -----------------------------------------------------------
if [[ $NO_RESTART -eq 0 ]]; then
    echo "Starting app..."
    ./webui-ctl.sh start
else
    echo "Skipping restart (--no-restart). Run './webui-ctl.sh start' when ready."
fi

echo
echo "Upgraded $(echo "$LOCAL" | cut -c1-12) -> $(echo "$REMOTE" | cut -c1-12)."
