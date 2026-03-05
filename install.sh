#!/usr/bin/env bash
# Install script for autograder: sets up alias and bash completion.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUTOGRADER="$SCRIPT_DIR/autograder.py"
COMPLETION="$SCRIPT_DIR/autograder-completion.bash"

ALIAS_LINE="alias autograder='python3 $AUTOGRADER'"
SOURCE_LINE="source $COMPLETION"
MARKER="# >>> autograder >>>"
END_MARKER="# <<< autograder <<<"

# Detect shell config file
if [[ -n "$ZSH_VERSION" ]] || [[ "$SHELL" == */zsh ]]; then
    RC="$HOME/.zshrc"
    BASHCOMPAT="autoload -U bashcompinit && bashcompinit"
else
    RC="$HOME/.bashrc"
    BASHCOMPAT=""
fi

BLOCK="$MARKER
${BASHCOMPAT:+$BASHCOMPAT
}$ALIAS_LINE
$SOURCE_LINE
$END_MARKER"

# Remove any previous autograder block, then append the new one
if grep -q "$MARKER" "$RC" 2>/dev/null; then
    # Delete old block (sed in-place, macOS-compatible)
    sed -i '' "/$MARKER/,/$END_MARKER/d" "$RC" 2>/dev/null \
        || sed -i "/$MARKER/,/$END_MARKER/d" "$RC"
    echo "Replaced existing autograder block in $RC"
else
    echo "Adding autograder block to $RC"
fi

printf '\n%s\n' "$BLOCK" >> "$RC"

echo "Done. Run 'source $RC' or open a new terminal to activate."
echo "  alias:      autograder → python3 $AUTOGRADER"
echo "  completion:  $COMPLETION"
