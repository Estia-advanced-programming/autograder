#!/usr/bin/env bash
# run_unit_ref.sh — Run the unit (metric + imperial) test suite against the
#                   reference pandora implementation.
#
# Usage:
#   ./run_unit_ref.sh              # run against the default reference jar
#   ./run_unit_ref.sh <jar>        # run against a custom jar
#
# The JSON test suite is rebuilt automatically before each run.
# To skip the rebuild (faster), comment out the "Rebuild" section below.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python3"

# ── Target jar ────────────────────────────────────────────────────────────
REF_JAR="${1:-../2026/pandora-2026-the_awesome_teachers_2026/target/pandora.jar}"
REF_MANIFEST="${REF_JAR%/target/pandora.jar}/manifest.json"

if [[ ! -f "${REF_JAR}" ]]; then
  echo "⚠️  Reference jar not found: ${REF_JAR}"
  echo "   Build it first with:  cd <teacher-repo> && mvn package -DskipTests"
  echo "   Or pass a custom path: $0 <path/to/pandora.jar>"
  exit 1
fi

# ── Config ────────────────────────────────────────────────────────────────
PROFILE="${SCRIPT_DIR}/test/profiles/end_semester.yml"
SUITE="${SCRIPT_DIR}/test/end.json"
TEST_DIR="${SCRIPT_DIR}/test/tests"
WORKERS=8

# ── Rebuild test suite ────────────────────────────────────────────────────
# echo "→ Building unit test suite from ${PROFILE} …"
# "${PYTHON}" "${SCRIPT_DIR}/tests_manager.py" build \
#   -p "${PROFILE}" \
#   -o "${SUITE}" \
#   -d "${TEST_DIR}"

# ── Run autograder ────────────────────────────────────────────────────────
echo "→ Running unit tests against: ${REF_JAR}"
"${PYTHON}" "${SCRIPT_DIR}/autograder.py" \
  "${REF_JAR}" \
  -m "${REF_MANIFEST}" \
  -t "${SUITE}" \
  -w "${WORKERS}" \
  --report \
  -f md \
  # -o "${SCRIPT_DIR}/unit_ref.md"
