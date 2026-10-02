#!/bin/bash
# Install claude-code-delegate: symlink the CLIs onto PATH and copy the Claude Code skills.
# Usage: ./install.sh [--force]    (BIN_DIR defaults to ~/.local/bin)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
SKILLS_DIR="$HOME/.claude/skills"
FORCE=0; [ "${1:-}" = "--force" ] && FORCE=1

python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
  || { echo "error: python3 >= 3.9 is required" >&2; exit 1; }

mkdir -p "$BIN_DIR" "$SKILLS_DIR"
link() {  # src dst
  if [ -e "$2" ] || [ -L "$2" ]; then
    if [ "$FORCE" = 1 ]; then rm -f "$2"; else echo "skip (exists): $2"; return; fi
  fi
  ln -s "$1" "$2" && echo "linked $2"
}
for f in "$HERE"/delegate/bin/* "$HERE"/review-loop/bin/*; do
  chmod +x "$f"
  link "$f" "$BIN_DIR/$(basename "$f")"
done
for s in delegate adversarial-review; do
  if [ -e "$SKILLS_DIR/$s" ] && [ "$FORCE" != 1 ]; then echo "skip (exists): $SKILLS_DIR/$s"; continue; fi
  rm -rf "$SKILLS_DIR/$s"; cp -R "$HERE/skills/$s" "$SKILLS_DIR/$s" && echo "installed skill $s"
done

case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "note: $BIN_DIR is not on your PATH";; esac
command -v opencode >/dev/null || echo "note: opencode not found; delegate-agent and review-loop need it"
[ -n "${OPENROUTER_API_KEY:-}" ] || echo "note: OPENROUTER_API_KEY is not set"
cat <<EOF

Next:
  1. Read the Security section of README.md.
  2. Add the OpenCode zero-data-retention setting (README, Install step 2).
  3. Append CLAUDE.md.snippet to ~/.claude/CLAUDE.md.
  4. Run: $HERE/review-loop/tests/selftest.sh and $HERE/delegate/tests/extract_selftest.sh
EOF
