#!/usr/bin/env python3
"""
Class Grader — batch orchestration and cross-group analysis tool.

Runs the autograder across all student groups, validates test suites,
performs cross-testing, and produces class-wide reports.

Usage:
    python class_grader.py -d <class_dir> -t <teacher_tests> -r <ref_jar> [options]
"""

import argparse
import concurrent.futures
import copy
import json
import math
import os
import re
import shlex
import subprocess
import sys

try:
    import yaml
except ImportError:
    yaml = None

PASS_THRESHOLD = 0.9
PARTIAL_THRESHOLD = 0.5

# ─── Feature whitelist loader ──────────────────────────────────────────────


def load_feature_whitelist():
    """Load feature whitelist from features-whitelist.json.

    If the file is not found, return None (allow all features).
    Returns a dict with 'features', 'parameters', and 'metadata_allowed' keys.
    """
    whitelist_path = os.path.join(os.path.dirname(__file__), "features-whitelist.json")
    if not os.path.isfile(whitelist_path):
        return None

    try:
        with open(whitelist_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


FEATURE_WHITELIST = load_feature_whitelist()

# Convenience sets for validation
ALLOWED_FEATURES = (
    set(FEATURE_WHITELIST.get("features", [])) if FEATURE_WHITELIST else None
)
ALLOWED_PARAMETERS = (
    set(FEATURE_WHITELIST.get("parameters", [])) if FEATURE_WHITELIST else None
)
ALLOWED_METADATA = (
    set(FEATURE_WHITELIST.get("metadata_allowed", [])) if FEATURE_WHITELIST else None
)

# ─── Badges ─────────────────────────────────────────────────────────────────


def badge(score, declared=True):
    """Return a badge for a score. ⚪️ if feature not declared."""
    if not declared:
        return "⚪️"
    if score >= PASS_THRESHOLD:
        return "🟢"
    if score >= PARTIAL_THRESHOLD:
        return "🟡"
    return "🔴"


def shorten_team_name(name):
    """Extract 'the_word1_word2' pattern and return 'word1 word2'."""
    import re

    match = re.search(r"the_(\w+)_(\w+)", name)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return name


# ─── Autograder invocation ──────────────────────────────────────────────────


def find_autograder():
    """Locate autograder.py next to this script."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "autograder.py")


def check_test_suite(
    test_suite,
    manifest,
    jar,
    test_dir=None,
    pandora_dir=None,
    timeout=10,
    debug=False,
    dryrun=False,
):
    """Run autograder --check to validate test suite inputs.

    Returns True if all checks pass, False otherwise.
    In dryrun mode, prints the command and returns True.
    """
    autograder = find_autograder()
    cmd = [sys.executable, autograder, "--check", "-t", test_suite, "-m", manifest]
    if test_dir:
        cmd += ["--test-dir", test_dir]
    if pandora_dir:
        cmd += ["-P", pandora_dir]
    if timeout != 10:
        cmd += ["-T", str(timeout)]
    if debug:
        cmd.append("-d")
    cmd.append(jar)

    if dryrun:
        print(f"    $ {shlex.join(cmd)}")
        return True

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return proc.returncode == 0
    except Exception:
        return False


def run_autograder(
    jar,
    test_suite,
    manifest,
    test_dir=None,
    pandora_dir=None,
    coverage=False,
    jacoco=None,
    timeout=10,
    workers=1,
    debug=False,
    dryrun=False,
):
    """Run the autograder as a subprocess and return parsed JSON output.

    Args:
        test_dir: --test-dir for autograder (CWD for Pandora, test file resolution)
        pandora_dir: -P for autograder (manifest/jar/jacoco resolution)
        workers: number of parallel test workers inside the autograder
        dryrun: if True, print the command instead of running it

    Returns (dict, None) on success or (None, error_string) on failure.
    In dryrun mode, returns (None, None).
    """
    autograder = find_autograder()
    cmd = [sys.executable, autograder, "-f", "json", "-t", test_suite, "-m", manifest]
    if test_dir:
        cmd += ["--test-dir", test_dir]
    if pandora_dir:
        cmd += ["-P", pandora_dir]
    if coverage:
        cmd.append("-c")
    if jacoco:
        cmd += ["-j", jacoco]
    if timeout != 10:
        cmd += ["-T", str(timeout)]
    if workers > 1:
        cmd += ["-w", str(workers)]
    if debug:
        cmd.append("-d")
    cmd.append(jar)

    if dryrun:
        print(f"    $ {shlex.join(cmd)}")
        return None, None

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as e:
        return None, str(e)

    # Check exit code — if non-zero, autograder encountered an error
    if proc.returncode != 0:
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        # If stdout has an error message, use it; otherwise fall back to stderr
        if stdout:
            return None, stdout
        elif stderr:
            return None, stderr
        else:
            return None, f"autograder failed with exit code {proc.returncode}"

    # The autograder prints JSON to stdout, possibly followed by "Total Score: ..."
    stdout = proc.stdout.strip()
    if not stdout:
        return None, f"empty output (stderr: {proc.stderr.strip()})"

    # Extract the JSON object (everything up to the last })
    brace_end = stdout.rfind("}")
    if brace_end == -1:
        return None, f"no JSON in output: {stdout[:200]}"
    json_str = stdout[: brace_end + 1]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    return data, None


# ─── Group discovery ────────────────────────────────────────────────────────


def discover_groups(class_dir):
    """Return sorted list of (group_name, group_path) for valid group folders."""
    groups = []
    for name in sorted(os.listdir(class_dir)):
        path = os.path.join(class_dir, name)
        if os.path.isdir(path) and not name.startswith("."):
            groups.append((name, path))
    return groups


def group_jar(group_path):
    return os.path.join(group_path, "target", "pandora.jar")


def group_manifest(group_path):
    return os.path.join(group_path, "manifest.json")


def group_test_suite(group_path):
    return os.path.join(group_path, "test", "testSuite.json")


def group_validated_test_suite(group_path):
    return os.path.join(group_path, "test", "testSuite_validated.json")


def group_cleaned_test_suite(group_path):
    return os.path.join(group_path, "test", "testSuite_cleaned.json")


def load_manifest(group_path):
    mpath = group_manifest(group_path)
    if not os.path.isfile(mpath):
        return None
    with open(mpath, "r") as f:
        return json.load(f)


# ─── Test suite cleaning & validation ───────────────────────────────────────


def _test_feature_key(test):
    """Return the group/feature/parameter/metadata key from a test."""
    return (
        test.get("group")
        or test.get("feature")
        or test.get("parameter")
        or test.get("metadata")
        or ""
    )


def clean_test_suite(group_name, group_path):
    """Remove truly broken tests from a group's test suite.

    Removes tests that:
      - Reference missing files
      - Use features/parameters/metadata not in the whitelist

    Returns (original_tests, cleaned_tests, removed_tests).
    """
    ts_path = group_test_suite(group_path)
    if not os.path.isfile(ts_path):
        return [], [], []

    try:
        with open(ts_path, "r") as f:
            original_tests = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  [!] {group_name}: malformed testSuite.json: {e}", file=sys.stderr)
        return [], [], []

    if not isinstance(original_tests, list):
        print(
            f"  [!] {group_name}: testSuite.json is not a JSON array", file=sys.stderr
        )
        return [], [], []

    cleaned = []
    removed = []

    for test in original_tests:
        # Check for missing file
        test_file = test.get("file", "")
        if test_file:
            resolved = (
                os.path.join(group_path, test_file)
                if not os.path.isabs(test_file)
                else test_file
            )
            if not os.path.isfile(resolved):
                removed.append(test)
                continue

        # Check feature against whitelist (only if whitelist loaded)
        feat = test.get("feature")
        param = test.get("parameter")
        meta = test.get("metadata")

        if ALLOWED_FEATURES is not None and feat and feat not in ALLOWED_FEATURES:
            removed.append(test)
            continue
        if ALLOWED_PARAMETERS is not None and param and param not in ALLOWED_PARAMETERS:
            removed.append(test)
            continue
        if ALLOWED_METADATA is not None and meta and meta not in ALLOWED_METADATA:
            removed.append(test)
            continue

        # Must have at least one of feature/parameter/metadata
        if not (feat or param or meta):
            removed.append(test)
            continue

        # Must have a result field to be runnable
        if "result" not in test:
            removed.append(test)
            continue

        cleaned.append(test)

    # Write cleaned test suite
    cleaned_path = group_cleaned_test_suite(group_path)
    os.makedirs(os.path.dirname(cleaned_path), exist_ok=True)
    with open(cleaned_path, "w") as f:
        json.dump(cleaned, f, indent=2)

    return original_tests, cleaned, removed


def validate_test_suite(group_name, group_path, ref_jar, cfg):
    """Run group's cleaned test suite against reference Pandora.

    Returns (result_dict, valid_tests, invalid_tests, removed_tests)
    or (None, [], [], removed_tests) on error.

    - removed_tests: tests dropped before running (missing files, non-whitelisted)
    - valid_tests: tests that pass against the reference implementation
    - invalid_tests: tests that fail against the reference (wrong expected values)

    The cleaned test suite (all non-removed tests) is used for cross-testing,
    so that both valid and invalid tests contribute to precision/recall.
    """
    original, cleaned, removed = clean_test_suite(group_name, group_path)

    if not cleaned:
        return None, [], [], removed

    cleaned_path = group_cleaned_test_suite(group_path)
    manifest_path = group_manifest(group_path)

    data, err = run_autograder(
        jar=ref_jar,
        test_suite=cleaned_path,
        manifest=manifest_path,
        test_dir=group_path,
        coverage=False,
        jacoco=cfg.get("jacoco"),
        timeout=cfg.get("timeout", 10),
        workers=cfg.get("workers_per_group", 8),
        debug=cfg.get("debug", False),
        dryrun=cfg.get("dryrun", False),
    )
    if err:
        print(f"  [!] {group_name}: validation failed: {err}")
        return None, [], [], removed

    # Build lookup from autograder results — index by id
    scored = {}
    for ms_tests in data.get("tests_by_milestone", {}).values():
        for t in ms_tests:
            key = t.get("id")
            if key is not None:
                scored[key] = t.get("score", 0)

    def _test_score(test, idx):
        tid = test.get("id")
        if tid is not None and tid in scored:
            return scored[tid]
        return 0

    valid = [t for i, t in enumerate(cleaned) if _test_score(t, i) >= PASS_THRESHOLD]
    invalid = [t for i, t in enumerate(cleaned) if _test_score(t, i) < PASS_THRESHOLD]

    return data, valid, invalid, removed


# ─── Collect all features across all groups ─────────────────────────────────


def collect_all_features(groups):
    """Return sorted list of all unique features across all manifests.

    If a whitelist is loaded, only includes features in the ALLOWED_FEATURES.
    If no whitelist is found, includes all features.
    """
    features = set()
    for _, gpath in groups:
        manifest = load_manifest(gpath)
        if manifest:
            manifest_features = manifest.get("features", [])
            if ALLOWED_FEATURES is None:
                # No whitelist — allow all features
                features.update(manifest_features)
            else:
                # Only add features that are in the whitelist
                valid_features = [f for f in manifest_features if f in ALLOWED_FEATURES]
                features.update(valid_features)
    return sorted(features)


# ─── Feature score extraction ───────────────────────────────────────────────


def extract_feature_scores(data, all_features, manifest_features):
    """From autograder JSON output, return {feature: score} for all features.
    Features not in manifest get None; features in manifest but not tested get 0.
    """
    fs = data.get("features_score", {}) if data else {}
    result = {}
    for feat in all_features:
        if feat not in set(manifest_features or []):
            result[feat] = None  # not declared
        else:
            result[feat] = fs.get(feat, 0.0)
    return result


def extract_feature_details(data, all_features, manifest_features):
    """From autograder JSON, return {feature: {score, valid, total, status} | None}.

    Uses the autograder's own classification (features_detail) so that badges
    and tallies are always consistent.
    """
    fd = data.get("features_detail", {}) if data else {}
    manifest_set = set(manifest_features or [])
    result = {}
    for feat in all_features:
        if feat not in manifest_set:
            result[feat] = None
        elif feat in fd:
            result[feat] = fd[feat]
        else:
            result[feat] = {"score": 0.0, "valid": 0, "total": 0, "status": "missed"}
    return result


# ─── Precision / Recall / F1 ───────────────────────────────────────────────


def compute_classification_metrics(tester_verdicts, ground_truth):
    """Compute precision, recall, F1, agreement.

    Args:
        tester_verdicts: {(tested_group, feature): bool_pass}
        ground_truth:    {(tested_group, feature): bool_pass}

    Only considers keys present in both dicts.
    """
    tp = fp = tn = fn = 0
    for key in ground_truth:
        if key not in tester_verdicts:
            continue
        truth = ground_truth[key]
        pred = tester_verdicts[key]
        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif not pred and truth:
            fn += 1
        else:
            tn += 1

    total = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        (2 * precision * recall / (precision + recall))
        if (precision + recall) > 0
        else 0.0
    )
    agreement = (tp + tn) / total if total > 0 else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "agreement": agreement,
    }


def compute_pairwise_agreement(tester_verdicts, ground_truth, tested_group):
    """Agreement rate for a specific tester vs a specific tested group."""
    match = total = 0
    for key, truth in ground_truth.items():
        if key[0] != tested_group:
            continue
        if key not in tester_verdicts:
            continue
        if tester_verdicts[key] == truth:
            match += 1
        total += 1
    return match / total if total > 0 else 0.0


# ─── Teacher score computation ─────────────────────────────────────────────


def compute_teacher_score(
    features_detail,
    test_tally,
    suite_total_tests,
    suite_total_features,
    scoring=None,
):
    """Compute the new teacher score from feature details and test tally.

    scoring: optional dict with keys test_point, feature_point, feature_penalty.

    Returns (score, breakdown) where breakdown has test_points, feature_points, penalty_points.
    """
    if scoring is None:
        scoring = {}
    test_point = scoring.get("test_point", 1)
    feature_point = scoring.get("feature_point", 100)
    feature_penalty = scoring.get("feature_penalty", -10)

    # Test points: validated tests × test_point
    test_points = test_tally.get("validated", 0) * test_point

    # Feature points
    feat_points = 0
    penalty_points = 0
    for _feat, detail in (features_detail or {}).items():
        status = detail.get("status", "not_implemented")
        score = detail.get("score", 0)
        if status == "validated":
            feat_points += feature_point
        elif status == "almost":
            feat_points += feature_point * score
        elif status == "missed":
            penalty_points += feature_penalty
        # not_implemented → 0

    raw = test_points + feat_points + penalty_points
    max_possible = suite_total_tests * test_point + suite_total_features * feature_point
    teacher_score = raw / max_possible if max_possible > 0 else 0.0

    breakdown = {
        "test_points": test_points,
        "feature_points": round(feat_points, 2),
        "penalty_points": penalty_points,
    }
    return round(teacher_score, 4), breakdown


# ─── Git commit analysis ──────────────────────────────────────────────────

# Tier A — strict conventional commit
TIER_A_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\(.+?\))?\s*:\s*.{3,}$"
)

# Tier B — prefix dictionaries (easily expandable by the teacher)
CONVENTIONAL_PREFIXES = [
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
]
EXTENDED_PREFIXES_EN = [
    "feature",
    "update",
    "new",
    "add",
    "implement",
    "hotfix",
    "release",
    "upgrade",
    "clean",
    "debug",
    "improve",
    "remove",
    "rename",
    "move",
    "merge",
    "bump",
]
EXTENDED_PREFIXES_FR = [
    "ajout",
    "correction",
    "modification",
    "modif",
    "suppression",
    "implémentation",
    "amélioration",
    "création",
    "changement",
    "nettoyage",
    "résolution",
    "sauvegarde",
    "MAJ",
    "mise à jour",
    "develop",
    "option",
]
ALL_TIER_B_PREFIXES = (
    CONVENTIONAL_PREFIXES + EXTENDED_PREFIXES_EN + EXTENDED_PREFIXES_FR
)
_prefix_pattern = "|".join(re.escape(p) for p in ALL_TIER_B_PREFIXES)
TIER_B_RE = re.compile(
    rf"^<?({_prefix_pattern})>?\s*[\[\(]?[^\]\)]*[\]\)]?\s*:\s*.+$",
    re.IGNORECASE,
)

# Tier C — descriptive (length >= 15 and contains a verb-like word)
VERBS_EN = {
    "add",
    "added",
    "implement",
    "implemented",
    "create",
    "created",
    "remove",
    "removed",
    "change",
    "changed",
    "update",
    "updated",
    "fix",
    "fixed",
    "resolve",
    "resolved",
    "clean",
    "cleaned",
    "improve",
    "improved",
    "move",
    "moved",
    "rename",
    "renamed",
    "delete",
    "deleted",
    "refactor",
    "refactored",
    "bump",
    "integrate",
}
VERBS_FR = {
    "ajout",
    "ajouté",
    "correction",
    "corrigé",
    "modification",
    "modifié",
    "mise",
    "suppression",
    "implémentation",
    "implémenté",
    "amélioration",
    "création",
    "changement",
    "nettoyage",
    "résolution",
    "sauvegarde",
    "recup",
    "dernière",
    "nouveau",
    "nouvelle",
}
TIER_C_VERBS = VERBS_EN | VERBS_FR

# Tier D — known garbage patterns
GARBAGE_RE = re.compile(r"^(ok|wip|oops|non|test|lol|asdf|todo|tmp)$", re.IGNORECASE)

# Merge commit pattern
MERGE_RE = re.compile(r"^Merge (branch|pull request|remote-tracking|commit)")

# Conventional prefix → category mapping
_CATEGORY_MAP = {
    "feat": "feat",
    "feature": "feat",
    "new": "feat",
    "add": "feat",
    "implement": "feat",
    "ajout": "feat",
    "implémentation": "feat",
    "création": "feat",
    "develop": "feat",
    "option": "feat",
    "fix": "fix",
    "hotfix": "fix",
    "debug": "fix",
    "correction": "fix",
    "résolution": "fix",
    "test": "test",
    "docs": "docs",
    "style": "style",
    "clean": "style",
    "nettoyage": "style",
    "refactor": "refactor",
    "rename": "refactor",
    "move": "refactor",
    "amélioration": "refactor",
    "improve": "refactor",
    "perf": "perf",
    "build": "build",
    "ci": "build",
    "release": "build",
    "upgrade": "build",
    "bump": "build",
    "MAJ": "build",
    "mise à jour": "build",
    "chore": "chore",
    "revert": "chore",
    "remove": "chore",
    "suppression": "chore",
    "update": "chore",
    "modification": "chore",
    "modif": "chore",
    "changement": "chore",
    "sauvegarde": "chore",
}


def _classify_commit(message, prev_message=None):
    """Classify a single commit message into tier A/B/C/D.

    Returns (tier, category) where tier is 'A','B','C','D'
    and category is one of feat/fix/test/docs/style/refactor/perf/build/chore/other.
    """
    msg = message.strip()

    # Tier A
    m = TIER_A_RE.match(msg)
    if m:
        prefix = m.group(1).lower()
        return "A", _CATEGORY_MAP.get(prefix, "other")

    # Tier B
    m = TIER_B_RE.match(msg)
    if m:
        prefix = m.group(1).lower()
        return "B", _CATEGORY_MAP.get(prefix, "other")

    # Tier D checks (before Tier C to catch short garbage)
    if len(msg) < 5:
        return "D", "other"
    if GARBAGE_RE.match(msg):
        return "D", "other"
    words = msg.split()
    if len(words) == 1 and len(msg) < 15:
        return "D", "other"
    # Non-alpha ratio > 50% for short messages
    if len(msg) < 20:
        alpha = sum(1 for c in msg if c.isalpha())
        if alpha < len(msg) * 0.5:
            return "D", "other"
    # Duplicate of previous
    if prev_message and msg == prev_message:
        return "D", "other"

    # Tier C
    if len(msg) >= 15:
        msg_words = set(msg.lower().split())
        if msg_words & TIER_C_VERBS:
            return "C", "other"

    # Falls through to D
    return "D", "other"


def analyze_commits(group_path, commits_cfg=None):
    """Run git log on a group repo and return commit analysis dict.

    commits_cfg: optional dict with keys:
      - teacher_email: str pattern to exclude (matched with 'in')
      - template_hashes: list of commit hash prefixes to exclude
    """
    if commits_cfg is None:
        commits_cfg = {}
    teacher_email = commits_cfg.get("teacher_email", "dhmmasson")
    template_hashes = set(
        commits_cfg.get(
            "template_hashes",
            [
                "3008cff",
                "7dda566",
                "40dc1ea",
                "2aa670a",
                "06f979c",
                "6506964",
                "99e6997",
            ],
        )
    )

    git_dir = os.path.join(group_path, ".git")
    if not os.path.isdir(git_dir):
        return {"error": "not a git repository", "total_commits": 0}

    cmd = ["git", "-C", group_path, "log", "--format=%H|||%ae|||%an|||%s"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"error": str(e), "total_commits": 0}

    total_commits = len(lines)
    excluded = {"template": 0, "teacher": 0, "merge": 0}
    student_records = []  # (hash, email, name, subject)

    for line in lines:
        parts = line.split("|||", 3)
        if len(parts) < 4:
            continue
        full_hash, email, name, subject = parts

        # Exclude template commits
        short_hash = full_hash[:7]
        if short_hash in template_hashes:
            excluded["template"] += 1
            continue
        # Exclude teacher commits
        if teacher_email and teacher_email in email:
            excluded["teacher"] += 1
            continue
        # Exclude merge commits
        if MERGE_RE.match(subject):
            excluded["merge"] += 1
            continue

        student_records.append((full_hash, email, name, subject))

    student_commits = len(student_records)

    # Per-author analysis
    authors = {}  # email -> {name, commits[], tiers, categories}
    prev_message = None
    for full_hash, email, name, subject in reversed(student_records):
        tier, category = _classify_commit(subject, prev_message)
        prev_message = subject.strip()

        if email not in authors:
            authors[email] = {
                "name": name,
                "commits": 0,
                "tier_a": 0,
                "tier_b": 0,
                "tier_c": 0,
                "tier_d": 0,
                "categories": {},
            }
        a = authors[email]
        a["commits"] += 1
        a[f"tier_{tier.lower()}"] += 1
        a["categories"][category] = a["categories"].get(category, 0) + 1

    # Per-author quality score + pct
    for email, a in authors.items():
        c = a["commits"]
        a["pct_of_project"] = round(c / student_commits, 4) if student_commits else 0
        if c > 0:
            descriptive_rate = (a["tier_a"] + a["tier_b"] + a["tier_c"]) / c
            structured_rate = (a["tier_a"] + a["tier_b"]) / c
            poor_rate = a["tier_d"] / c
            volume = min(c / 30, 1.0)
            a["quality_score"] = round(
                40 * descriptive_rate
                + 30 * structured_rate
                + 20 * (1 - poor_rate)
                + 10 * volume,
                1,
            )
        else:
            a["quality_score"] = 0

    # Group-level metrics
    total_a = sum(a["tier_a"] for a in authors.values())
    total_b = sum(a["tier_b"] for a in authors.values())
    total_c = sum(a["tier_c"] for a in authors.values())
    total_d = sum(a["tier_d"] for a in authors.values())

    if student_commits > 0:
        conventional_rate = total_a / student_commits
        structured_rate = (total_a + total_b) / student_commits
        descriptive_rate = (total_a + total_b + total_c) / student_commits
        poor_rate = total_d / student_commits
    else:
        conventional_rate = structured_rate = descriptive_rate = poor_rate = 0

    # Author balance: 1 - (std / mean) of per-author commit counts
    commit_counts = [a["commits"] for a in authors.values()]
    if len(commit_counts) > 1:
        mean_c = sum(commit_counts) / len(commit_counts)
        if mean_c > 0:
            std_c = math.sqrt(
                sum((x - mean_c) ** 2 for x in commit_counts) / len(commit_counts)
            )
            author_balance = round(max(0, 1 - std_c / mean_c), 4)
        else:
            author_balance = 0
    elif len(commit_counts) == 1:
        author_balance = 1.0
    else:
        author_balance = 0

    # Volume bonus
    volume = min(student_commits / 30, 1.0)
    quality_score = round(
        40 * descriptive_rate
        + 30 * structured_rate
        + 20 * (1 - poor_rate)
        + 10 * volume,
        1,
    )

    # Grade
    if student_commits < 3:
        quality_grade = "Insufficient"
    elif quality_score >= 80:
        quality_grade = "Excellent"
    elif quality_score >= 60:
        quality_grade = "Good"
    elif quality_score >= 40:
        quality_grade = "Acceptable"
    elif quality_score >= 20:
        quality_grade = "Poor"
    else:
        quality_grade = "Very Poor"

    # Aggregate categories
    commit_categories = {}
    for a in authors.values():
        for cat, cnt in a["categories"].items():
            commit_categories[cat] = commit_categories.get(cat, 0) + cnt

    # Branch discipline
    merge_evidence = []
    uses_feature_branches = False
    uses_pull_requests = False
    branch_names = set()
    for line in lines:
        parts = line.split("|||", 3)
        if len(parts) < 4:
            continue
        subject = parts[3]
        if subject.startswith("Merge pull request"):
            uses_pull_requests = True
            merge_evidence.append(subject)
            # Extract branch name from "Merge pull request #N from owner/branch"
            m = re.search(r"from\s+\S+/(\S+)", subject)
            if m:
                branch_names.add(m.group(1))
        elif subject.startswith("Merge branch"):
            m = re.search(r"Merge branch '([^']+)'", subject)
            if m:
                bname = m.group(1)
                if bname not in ("main", "master"):
                    uses_feature_branches = True
                    branch_names.add(bname)
                    merge_evidence.append(subject)

    if uses_pull_requests:
        uses_feature_branches = True

    # AI detection
    ai_evidence = []
    ai_branch_re = re.compile(r"codex/", re.IGNORECASE)
    ai_author_re = re.compile(r"(copilot|codex|ai-|bot@)", re.IGNORECASE)
    for line in lines:
        parts = line.split("|||", 3)
        if len(parts) < 4:
            continue
        email, name, subject = parts[1], parts[2], parts[3]
        if ai_branch_re.search(subject):
            ai_evidence.append(subject)
        if ai_author_re.search(email) or ai_author_re.search(name):
            ai_evidence.append(f"{name} <{email}>: {subject}")

    # Sample poor commits (up to 5)
    sample_poor = []
    for full_hash, email, name, subject in student_records:
        tier, _ = _classify_commit(subject)
        if tier == "D" and len(sample_poor) < 5:
            sample_poor.append(
                {
                    "hash": full_hash[:7],
                    "author": email,
                    "message": subject,
                }
            )

    return {
        "total_commits": total_commits,
        "excluded_commits": excluded,
        "student_commits": student_commits,
        "authors": authors,
        "group_metrics": {
            "conventional_rate": round(conventional_rate, 4),
            "structured_rate": round(structured_rate, 4),
            "descriptive_rate": round(descriptive_rate, 4),
            "poor_rate": round(poor_rate, 4),
            "quality_score": quality_score,
            "quality_grade": quality_grade,
            "author_balance": author_balance,
        },
        "branch_discipline": {
            "uses_feature_branches": uses_feature_branches,
            "uses_pull_requests": uses_pull_requests,
            "branch_count": len(branch_names),
            "evidence": merge_evidence[:10],
        },
        "ai_detected": {
            "detected": len(ai_evidence) > 0,
            "evidence": ai_evidence[:10],
        },
        "commit_categories": commit_categories,
        "sample_poor_commits": sample_poor,
        "error": None,
    }


# ─── JaCoCo coverage parsing ──────────────────────────────────────────────


def parse_jacoco_xml(group_path, report_path=None):
    """Parse a JaCoCo XML report and extract coverage metrics.

    Returns a dict with line/branch/class/method/instruction coverage ratios
    and per-package breakdown.
    """
    if report_path is None:
        report_path = os.path.join(group_path, "target", "site", "jacoco", "jacoco.xml")

    if not os.path.isfile(report_path):
        return {"error": f"JaCoCo report not found: {report_path}"}

    try:
        import xml.etree.ElementTree as ET

        tree = ET.parse(report_path)
        root = tree.getroot()
    except Exception as e:
        return {"error": f"Failed to parse JaCoCo XML: {e}"}

    def _coverage_ratio(element, counter_type):
        for counter in element.findall("counter"):
            if counter.get("type") == counter_type:
                missed = int(counter.get("missed", 0))
                covered = int(counter.get("covered", 0))
                total = missed + covered
                return covered / total if total > 0 else 0.0
        return None

    line_cov = _coverage_ratio(root, "LINE")
    branch_cov = _coverage_ratio(root, "BRANCH")
    class_cov = _coverage_ratio(root, "CLASS")
    method_cov = _coverage_ratio(root, "METHOD")
    instruction_cov = _coverage_ratio(root, "INSTRUCTION")

    # Per-package breakdown
    packages = {}
    for pkg in root.findall("package"):
        pkg_name = pkg.get("name", "").replace("/", ".")
        packages[pkg_name] = {
            "line": _coverage_ratio(pkg, "LINE"),
            "branch": _coverage_ratio(pkg, "BRANCH"),
        }

    # Find uncovered classes
    uncovered_classes = []
    for pkg in root.findall("package"):
        pkg_name = pkg.get("name", "").replace("/", ".")
        for cls in pkg.findall("class"):
            cls_name = f"{pkg_name}.{cls.get('name', '').split('/')[-1]}"
            cls_line = _coverage_ratio(cls, "LINE")
            if cls_line is not None and cls_line == 0:
                uncovered_classes.append(cls_name)

    return {
        "line_coverage": round(line_cov, 4) if line_cov is not None else None,
        "branch_coverage": round(branch_cov, 4) if branch_cov is not None else None,
        "class_coverage": round(class_cov, 4) if class_cov is not None else None,
        "method_coverage": round(method_cov, 4) if method_cov is not None else None,
        "instruction_coverage": (
            round(instruction_cov, 4) if instruction_cov is not None else None
        ),
        "uncovered_classes": uncovered_classes,
        "packages": packages,
        "error": None,
    }


def _fmt_tally(tally):
    return (
        f"\U0001f7e2{tally['validated']} "
        f"\U0001f7e1{tally['almost']} "
        f"\U0001f534{tally['missed']} "
        f"\u26aa{tally['not_implemented']}"
    )


# ─── CLI ────────────────────────────────────────────────────────────────────


def load_yaml_config(path):
    """Load a YAML configuration file and return a dict."""
    if yaml is None:
        print(
            "ERROR: PyYAML is required for --config. Install with: pip install pyyaml"
        )
        sys.exit(1)
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def build_parser():
    p = argparse.ArgumentParser(
        description="Class Grader — batch autograder orchestration and analysis.",
        usage="python class_grader.py [-C config.yml] [-d <class_dir> -t <teacher_tests> -r <ref_jar>] [options]",
    )
    p.add_argument(
        "-C",
        "--config",
        default=None,
        help="Path to a YAML configuration file (CLI options override config values)",
    )
    p.add_argument(
        "-d", "--dir", default=None, help="Root directory containing group subfolders"
    )
    p.add_argument(
        "-t", "--tests", default=None, help="Path to teacher's reference test suite"
    )
    p.add_argument(
        "-r", "--ref", default=None, help="Path to teacher's reference Pandora JAR"
    )
    p.add_argument(
        "-W",
        "--teacher-workdir",
        default=None,
        help="Teacher project root (where teacher test file paths resolve from). "
        "Defaults to parent directory of the teacher test suite.",
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output directory for reports (default: current dir)",
    )
    p.add_argument(
        "-c",
        "--coverage",
        default=None,
        action="store_true",
        help="Enable JaCoCo coverage analysis",
    )
    p.add_argument("-j", "--jacoco", default=None, help="Path to JaCoCo agent JAR")
    p.add_argument(
        "-T",
        "--timeout",
        type=int,
        default=None,
        help="Per-command timeout in seconds (default: 10)",
    )
    p.add_argument(
        "--debug",
        default=None,
        action="store_true",
        help="Enable debug output",
    )
    p.add_argument(
        "--fast",
        default=None,
        action="store_true",
        help="Shorthand: only run teacher evaluation, skip all other phases",
    )
    p.add_argument(
        "--dryrun",
        default=None,
        action="store_true",
        help="Print the autograder commands that would be run without executing them",
    )
    p.add_argument(
        "--phase",
        default=None,
        nargs="+",
        choices=[
            "teacher_evaluation",
            "validation",
            "self_evaluation",
            "cross_testing",
            "coverage",
            "commits",
        ],
        help="Run only the specified phase(s). Overrides config phases.",
    )
    return p


# ─── Main ───────────────────────────────────────────────────────────────────


# Mapping from YAML keys to argparse dest names
_YAML_KEY_MAP = {
    "dir": "dir",
    "tests": "tests",
    "ref": "ref",
    "teacher_workdir": "teacher_workdir",
    "output": "output",
    "coverage": "coverage",
    "jacoco": "jacoco",
    "timeout": "timeout",
    "workers": "workers",
    "workers_per_group": "workers_per_group",
    "debug": "debug",
    "fast": "fast",
    "phases": "phases",
    "dryrun": "dryrun",
    "scoring": "scoring",
    "commits": "commits",
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── Merge YAML config with CLI args (CLI wins) ───────────────────
    if args.config:
        file_cfg = load_yaml_config(args.config)
        for yaml_key, attr in _YAML_KEY_MAP.items():
            if yaml_key in file_cfg and getattr(args, attr, None) is None:
                setattr(args, attr, file_cfg[yaml_key])

    # Apply defaults for optional args not set by CLI or config
    if args.output is None:
        args.output = "."
    if args.timeout is None:
        args.timeout = 10
    if not hasattr(args, "workers") or args.workers is None:
        args.workers = 1
    if not hasattr(args, "workers_per_group") or args.workers_per_group is None:
        args.workers_per_group = 8
    if args.coverage is None:
        args.coverage = False
    if args.debug is None:
        args.debug = False
    if args.fast is None:
        args.fast = False
    if not hasattr(args, "phases") or args.phases is None:
        args.phases = {}
    if args.dryrun is None:
        args.dryrun = False
    if not hasattr(args, "scoring") or args.scoring is None:
        args.scoring = {}
    if not hasattr(args, "commits") or args.commits is None:
        args.commits = {}

    # ── Resolve per-phase flags ──────────────────────────────────────
    # Defaults: all phases enabled except coverage (slow)
    _default_phases = {
        "teacher_evaluation": True,
        "validation": True,
        "self_evaluation": True,
        "cross_testing": True,
        "coverage": False,
        "commits": True,
    }
    phases = {k: v for k, v in _default_phases.items()}
    # Override with config phases (if any)
    if isinstance(args.phases, dict):
        for k, v in args.phases.items():
            if k in phases:
                phases[k] = bool(v)
    # --fast overrides: only teacher_evaluation
    if args.fast:
        phases["validation"] = False
        phases["self_evaluation"] = False
        phases["cross_testing"] = False
        phases["coverage"] = False

    # --phase overrides: run only specified phases
    if args.phase:
        for k in phases:
            phases[k] = k in args.phase

    # Validate required options
    missing = []
    if not args.dir:
        missing.append("--dir / -d (or 'dir' in config)")
    if not args.tests:
        missing.append("--tests / -t (or 'tests' in config)")
    if not args.ref:
        missing.append("--ref / -r (or 'ref' in config)")
    if missing:
        parser.error("the following arguments are required: " + ", ".join(missing))

    class_dir = os.path.abspath(args.dir)
    teacher_tests = os.path.abspath(args.tests)
    ref_jar = os.path.abspath(args.ref)
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    # Teacher workdir: where teacher test file paths (e.g. ./test/testsFiles/...) resolve
    if args.teacher_workdir:
        teacher_workdir = os.path.abspath(args.teacher_workdir)
    else:
        # Default: go up from test suite path (e.g. .../project/test/testSuite.json -> .../project/)
        teacher_workdir = os.path.dirname(os.path.dirname(teacher_tests))

    cfg = {
        "coverage": args.coverage,
        "jacoco": args.jacoco,
        "timeout": args.timeout,
        "workers": args.workers,
        "workers_per_group": args.workers_per_group,
        "debug": args.debug,
        "dryrun": args.dryrun,
    }

    concurrent_groups = max(args.workers // args.workers_per_group, 1)

    groups = discover_groups(class_dir)
    if not groups:
        print(f"No group folders found in {class_dir}")
        sys.exit(1)

    group_names = [g[0] for g in groups]
    all_features = collect_all_features(groups)
    print(
        f"Found {len(groups)} groups, {len(all_features)} features across all manifests"
    )

    # Storage for results
    teacher_eval = {}  # group -> autograder JSON result
    teacher_scores = {}  # group -> {feature: score|None}
    teacher_details = {}  # group -> {feature: {score, valid, total, status}|None}
    self_eval = {}  # group -> autograder JSON result
    validation_results = {}  # group -> (data, valid, invalid)
    group_manifests = {}  # group -> manifest features list

    # Pre-load all manifests
    for gname, gpath in groups:
        manifest = load_manifest(gpath)
        group_manifests[gname] = manifest.get("features", []) if manifest else []

    # ── 3.1 Teacher Tests → Student Pandoras ──────────────────────────
    if phases["teacher_evaluation"]:
        print("\n=== Teacher Tests → Student Pandoras ===")

        def _teacher_eval_one(gname, gpath):
            jar = group_jar(gpath)
            manifest_path = group_manifest(gpath)
            if not os.path.isfile(jar):
                return gname, "SKIP_JAR", None, None
            if not os.path.isfile(manifest_path):
                return gname, "SKIP_MANIFEST", None, None
            data, err = run_autograder(
                jar=jar,
                test_suite=teacher_tests,
                manifest=manifest_path,
                test_dir=teacher_workdir,
                coverage=cfg["coverage"],
                jacoco=cfg.get("jacoco"),
                timeout=cfg["timeout"],
                workers=cfg["workers_per_group"],
                debug=cfg["debug"],
                dryrun=cfg["dryrun"],
            )
            return gname, None, data, err

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrent_groups
        ) as pool:
            futures = {
                pool.submit(_teacher_eval_one, gname, gpath): gname
                for gname, gpath in groups
            }
            for future in concurrent.futures.as_completed(futures):
                gname, skip, data, err = future.result()
                if skip == "SKIP_JAR":
                    print(f"  [{gname}] SKIP: target/pandora.jar not found")
                    continue
                if skip == "SKIP_MANIFEST":
                    print(f"  [{gname}] SKIP: manifest.json not found")
                    continue
                if data is None and err is None:
                    continue
                if err:
                    print(f"  [{gname}] ERROR: {err}")
                    continue
                mfeats = group_manifests[gname]
                teacher_eval[gname] = data
                teacher_scores[gname] = extract_feature_scores(
                    data, all_features, mfeats
                )
                teacher_details[gname] = extract_feature_details(
                    data, all_features, mfeats
                )
                ft = data.get("tally", {})
                tt = data.get("test_tally", {})
                print(
                    f"  [{gname}] total: {data.get('total_score', 0):.2f}  "
                    f"features: {_fmt_tally(ft)}  tests: {_fmt_tally(tt)}"
                )

    # Print skipped phases
    skipped = [k for k, v in phases.items() if not v]
    if skipped:
        print(f"\n=== Skipped phases: {', '.join(skipped)} ===")

    # ── 3.2 Student Tests → Teacher Pandora (validation) ─────────────
    if phases["validation"]:
        print("\n=== Student Tests → Teacher Pandora (validation) ===")

        def _validate_one(gname, gpath):
            ts = group_test_suite(gpath)
            if not os.path.isfile(ts):
                return gname, "SKIP", None, None, None, None
            data, valid, invalid, removed = validate_test_suite(
                gname, gpath, ref_jar, cfg
            )
            return gname, None, data, valid, invalid, removed

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrent_groups
        ) as pool:
            futures = {
                pool.submit(_validate_one, gname, gpath): gname
                for gname, gpath in groups
            }
            for future in concurrent.futures.as_completed(futures):
                gname, skip, data, valid, invalid, removed = future.result()
                if skip:
                    print(f"  [{gname}] SKIP: no testSuite.json")
                    continue
                validation_results[gname] = (data, valid, invalid, removed)
                if data:
                    print(
                        f"  [{gname}] valid: {len(valid)}, invalid: {len(invalid)}, removed: {len(removed)}"
                    )
                elif removed:
                    print(
                        f"  [{gname}] all tests removed ({len(removed)} broken/non-whitelisted)"
                    )

    # ── Self-evaluation (student tests → own Pandora) ────────────────
    if phases["self_evaluation"]:
        print("\n=== Self-Evaluation (Student Tests → Own Pandora) ===")

        def _self_eval_one(gname, gpath):
            jar = group_jar(gpath)
            cleaned_ts = group_cleaned_test_suite(gpath)
            manifest_path = group_manifest(gpath)
            if not (os.path.isfile(jar) and os.path.isfile(manifest_path)):
                return gname, "SKIP_FILES", None, None
            if not os.path.isfile(cleaned_ts):
                return gname, "SKIP_CLEANED", None, None
            data, err = run_autograder(
                jar=jar,
                test_suite=cleaned_ts,
                manifest=manifest_path,
                test_dir=gpath,
                timeout=cfg["timeout"],
                workers=cfg["workers_per_group"],
                debug=cfg["debug"],
                dryrun=cfg["dryrun"],
            )
            return gname, None, data, err

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrent_groups
        ) as pool:
            futures = {
                pool.submit(_self_eval_one, gname, gpath): gname
                for gname, gpath in groups
            }
            for future in concurrent.futures.as_completed(futures):
                gname, skip, data, err = future.result()
                if skip == "SKIP_FILES":
                    continue
                if skip == "SKIP_CLEANED":
                    print(f"  [{gname}] SKIP: no cleaned test suite available")
                    continue
                if data is None and err is None:
                    continue
                if err:
                    print(f"  [{gname}] ERROR: {err}")
                    continue
                self_eval[gname] = data
                print(f"  [{gname}] self-score: {data.get('total_score', 0):.2f}")

    # ── 3.3 Cross-Testing ────────────────────────────────────────────
    if phases["cross_testing"]:
        print("\n=== Cross-Testing (Student Tests → Other Pandoras) ===")

        # Build ground truth from teacher evaluation
        ground_truth = {}  # (tested_group, feature) -> bool
        for gname in group_names:
            for feat in all_features:
                score = teacher_scores.get(gname, {}).get(feat)
                if score is not None:
                    ground_truth[(gname, feat)] = score >= PASS_THRESHOLD

        # For each tester group, run their cleaned tests against all other groups
        tester_verdicts = {}  # tester -> {(tested_group, feature): bool}
        cross_results = {}  # (tester, tested) -> autograder JSON

        # Build all (tester, tested) pairs
        cross_jobs = []
        for tester_name, tester_path in groups:
            cleaned_ts = group_cleaned_test_suite(tester_path)
            if not os.path.isfile(cleaned_ts):
                continue
            tester_verdicts[tester_name] = {}
            for tested_name, tested_path in groups:
                if tested_name == tester_name:
                    continue
                jar = group_jar(tested_path)
                manifest_path = group_manifest(tested_path)
                if not (os.path.isfile(jar) and os.path.isfile(manifest_path)):
                    continue
                cross_jobs.append(
                    (
                        tester_name,
                        tester_path,
                        tested_name,
                        jar,
                        manifest_path,
                        cleaned_ts,
                    )
                )

        def _cross_test_one(
            tester_name, tester_path, tested_name, jar, manifest_path, cleaned_ts
        ):
            data, err = run_autograder(
                jar=jar,
                test_suite=cleaned_ts,
                manifest=manifest_path,
                test_dir=tester_path,
                timeout=cfg["timeout"],
                workers=cfg["workers_per_group"],
                debug=cfg["debug"],
                dryrun=cfg["dryrun"],
            )
            return tester_name, tested_name, data, err

        print(f"  Running {len(cross_jobs)} cross-test pairs...")
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrent_groups
        ) as pool:
            futures = [pool.submit(_cross_test_one, *job) for job in cross_jobs]
            for future in concurrent.futures.as_completed(futures):
                tester_name, tested_name, data, err = future.result()
                if data is None and err is None:
                    continue
                if err:
                    print(f"    [{tester_name} → {tested_name}] ERROR: {err}")
                    continue
                cross_results[(tester_name, tested_name)] = data
                fs = data.get("features_score", {})
                tested_manifest = group_manifests.get(tested_name, [])
                for feat in all_features:
                    if feat in set(tested_manifest):
                        score = fs.get(feat, 0)
                        tester_verdicts[tester_name][(tested_name, feat)] = (
                            score >= PASS_THRESHOLD
                        )

        # ── Compute metrics ──────────────────────────────────────────────
        group_metrics = {}
        for tester_name in group_names:
            if tester_name not in tester_verdicts:
                continue
            metrics = compute_classification_metrics(
                tester_verdicts[tester_name], ground_truth
            )
            group_metrics[tester_name] = metrics
    else:
        group_metrics = {}

    # ── Coverage phase ───────────────────────────────────────────────
    coverage_data = {}
    if phases.get("coverage"):
        print("\n=== Coverage Analysis (Student Tests → Own JAR with JaCoCo) ===")

        def _coverage_one(gname, gpath):
            jar = group_jar(gpath)
            cleaned_ts = group_cleaned_test_suite(gpath)
            manifest_path = group_manifest(gpath)
            if not (os.path.isfile(jar) and os.path.isfile(manifest_path)):
                return gname, "SKIP_FILES", None
            if not os.path.isfile(cleaned_ts):
                return gname, "SKIP_CLEANED", None

            # Run autograder with coverage enabled (runs from gpath so
            # destfile=target/jacoco.exec lands inside the group repo)
            data, err = run_autograder(
                jar=jar,
                test_suite=cleaned_ts,
                manifest=manifest_path,
                test_dir=gpath,
                pandora_dir=gpath,
                coverage=True,
                jacoco=cfg.get("jacoco"),
                timeout=cfg["timeout"],
                workers=cfg["workers_per_group"],
                debug=cfg["debug"],
                dryrun=cfg["dryrun"],
            )
            if err:
                return gname, "ERROR", {"error": str(err)}

            # Generate the JaCoCo XML report from the accumulated exec file
            mvn_result = subprocess.run(
                ["mvn", "jacoco:report"],
                cwd=gpath,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
            )
            if mvn_result.returncode != 0 and cfg.get("debug"):
                print(
                    f"  [{gname}] mvn jacoco:report stderr: "
                    f"{mvn_result.stderr.decode(errors='replace').strip()}"
                )

            # Parse the JaCoCo XML report
            cov = parse_jacoco_xml(gpath)
            cov["team"] = gname
            return gname, None, cov

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrent_groups
        ) as pool:
            futures = {
                pool.submit(_coverage_one, gname, gpath): gname
                for gname, gpath in groups
            }
            for future in concurrent.futures.as_completed(futures):
                gname, skip, cov = future.result()
                if skip == "SKIP_FILES" or skip == "SKIP_CLEANED":
                    continue
                if skip == "ERROR":
                    print(f"  [{gname}] ERROR: {cov.get('error')}")
                coverage_data[gname] = cov
                line_c = cov.get("line_coverage")
                branch_c = cov.get("branch_coverage")
                if line_c is not None:
                    branch_str = f"{branch_c:.2%}" if branch_c is not None else "n/a"
                    print(f"  [{gname}] line={line_c:.2%} branch={branch_str}")

    # ── Commit analysis phase ────────────────────────────────────────
    commits_data = {}
    if phases.get("commits"):
        print("\n=== Git Commit Analysis ===")
        commits_cfg = args.commits if isinstance(args.commits, dict) else {}
        for gname, gpath in groups:
            result = analyze_commits(gpath, commits_cfg)
            result["team"] = gname
            result["repo_path"] = gpath
            commits_data[gname] = result
            gm = result.get("group_metrics", {})
            n = result.get("student_commits", 0)
            grade = gm.get("quality_grade", "?")
            print(f"  [{gname}] {n} student commits, quality={grade}")

    # ── Load teacher test suite metadata ─────────────────────────────
    try:
        with open(teacher_tests, "r") as f:
            raw_teacher_suite = json.load(f)
        if isinstance(raw_teacher_suite, dict):
            teacher_test_list = raw_teacher_suite.get("tests", [])
            test_suite_metadata = raw_teacher_suite.get("metadata")
        else:
            teacher_test_list = raw_teacher_suite
            test_suite_metadata = None
        teacher_test_count = len(teacher_test_list)
    except Exception:
        teacher_test_list = []
        teacher_test_count = 0
        test_suite_metadata = None
    teacher_tests_name = os.path.basename(teacher_tests)

    # ── Build per-group JSON data ────────────────────────────────────
    scoring_cfg = args.scoring if isinstance(args.scoring, dict) else {}
    group_data = {}
    for gname in group_names:
        te = teacher_eval.get(gname, {})
        se = self_eval.get(gname, {})
        vr = validation_results.get(gname, (None, [], [], []))
        _, valid, invalid, removed = vr
        metrics = group_metrics.get(
            gname,
            {
                "tp": 0,
                "fp": 0,
                "tn": 0,
                "fn": 0,
                "precision": 0,
                "recall": 0,
                "f1": 0,
                "agreement": 0,
            },
        )

        group_data[gname] = {
            "team": gname,
            "short_name": shorten_team_name(gname),
            "version": te.get("version", "?"),
            "feature_tally": te.get("tally", {}),
            "test_tally": te.get("test_tally", {}),
            "features_detail": te.get("features_detail", {}),
            "manifest_features": group_manifests.get(gname, []),
            "teacher_evaluation": {
                "features_score": teacher_scores.get(gname, {}),
                "total_score": te.get("total_score", 0),
                "milestone_scores": te.get("milestone_scores", {}),
            },
            "self_evaluation": {
                "features_score": se.get("features_score", {}),
                "total_score": se.get("total_score", 0),
            },
            "test_quality": {
                "total_tests": len(valid) + len(invalid) + len(removed),
                "cleaned_tests": len(valid) + len(invalid),
                "valid_tests": len(valid),
                "invalid_tests": len(invalid),
                "removed_tests": len(removed),
                "tp": metrics.get("tp", 0),
                "fp": metrics.get("fp", 0),
                "tn": metrics.get("tn", 0),
                "fn": metrics.get("fn", 0),
                "precision": metrics.get("precision", 0),
                "recall": metrics.get("recall", 0),
                "f1": metrics.get("f1", 0),
                "accuracy": metrics.get("agreement", 0),
            },
            "coverage": coverage_data.get(gname),
            "commits": commits_data.get(gname),
        }

        # Compute new teacher score
        feat_detail = te.get("features_detail", {})
        t_tally = te.get("test_tally", {})
        ts_new, ts_breakdown = compute_teacher_score(
            feat_detail,
            t_tally,
            teacher_test_count,
            len(all_features),
            scoring_cfg,
        )
        group_data[gname]["teacher_evaluation"]["teacher_score"] = ts_new
        group_data[gname]["teacher_evaluation"][
            "teacher_score_breakdown"
        ] = ts_breakdown
        group_data[gname]["teacher_evaluation"]["test_suite"] = teacher_tests_name
        group_data[gname]["teacher_evaluation"][
            "test_suite_metadata"
        ] = test_suite_metadata

    # ── Write per-phase JSON directories ─────────────────────────────
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")

    def _write_phase_json(phase_name, phase_data_by_group, extra_meta=None):
        """Write per-group JSON + _meta.json + _summary.json for a phase."""
        phase_dir = os.path.join(output_dir, phase_name)
        os.makedirs(phase_dir, exist_ok=True)
        for gname, data in phase_data_by_group.items():
            path = os.path.join(phase_dir, f"{gname}.json")
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        meta = {
            "phase": phase_name,
            "date": now,
            "groups_evaluated": len(phase_data_by_group),
        }
        if extra_meta:
            meta.update(extra_meta)
        with open(os.path.join(phase_dir, "_meta.json"), "w") as f:
            json.dump(meta, f, indent=2, default=str)

    # Teacher eval phase JSON
    if phases["teacher_evaluation"] and teacher_eval:
        te_phase_data = {}
        for gname in group_names:
            if gname in teacher_eval:
                te_phase_data[gname] = {
                    "team": gname,
                    "short_name": shorten_team_name(gname),
                    "version": group_data[gname]["version"],
                    "test_suite": teacher_tests_name,
                    "test_suite_metadata": test_suite_metadata,
                    "total_score": group_data[gname]["teacher_evaluation"][
                        "total_score"
                    ],
                    "teacher_score": group_data[gname]["teacher_evaluation"][
                        "teacher_score"
                    ],
                    "teacher_score_breakdown": group_data[gname]["teacher_evaluation"][
                        "teacher_score_breakdown"
                    ],
                    "milestone_scores": group_data[gname]["teacher_evaluation"][
                        "milestone_scores"
                    ],
                    "feature_tally": group_data[gname]["feature_tally"],
                    "test_tally": group_data[gname]["test_tally"],
                    "features_score": group_data[gname]["teacher_evaluation"][
                        "features_score"
                    ],
                    "features_detail": group_data[gname]["features_detail"],
                    "manifest_features": group_data[gname]["manifest_features"],
                    "error": None,
                }
        _write_phase_json(
            "teacher_eval",
            te_phase_data,
            {
                "test_suite": teacher_tests_name,
                "test_suite_metadata": test_suite_metadata,
                "test_count": teacher_test_count,
                "feature_count": len(all_features),
                "ref_jar": os.path.basename(ref_jar),
            },
        )

    # Validation phase JSON
    if phases["validation"] and validation_results:
        val_phase_data = {}
        for gname in group_names:
            vr = validation_results.get(gname)
            if not vr:
                continue
            vdata, valid, invalid, removed = vr
            mfeats = group_manifests.get(gname, [])
            val_phase_data[gname] = {
                "team": gname,
                "short_name": shorten_team_name(gname),
                "version": group_data[gname]["version"],
                "total_tests": len(valid) + len(invalid) + len(removed),
                "cleaned_tests": len(valid) + len(invalid),
                "valid_tests": len(valid),
                "invalid_tests": len(invalid),
                "removed_tests": len(removed),
                "features_score": (
                    extract_feature_scores(vdata, all_features, mfeats) if vdata else {}
                ),
                "features_detail": (
                    extract_feature_details(vdata, all_features, mfeats)
                    if vdata
                    else {}
                ),
                "declared_features": mfeats,
                "error": None,
            }
        _write_phase_json("validation", val_phase_data)

    # Self-eval phase JSON
    if phases["self_evaluation"] and self_eval:
        se_phase_data = {}
        for gname in group_names:
            if gname in self_eval:
                se = self_eval[gname]
                se_phase_data[gname] = {
                    "team": gname,
                    "short_name": shorten_team_name(gname),
                    "version": group_data[gname]["version"],
                    "total_score": se.get("total_score", 0),
                    "features_score": se.get("features_score", {}),
                    "features_detail": se.get("features_detail", {}),
                    "error": None,
                }
        _write_phase_json("self_eval", se_phase_data)

    # Cross-testing phase JSON
    if phases["cross_testing"] and group_metrics:
        ct_phase_data = {}
        for gname in group_names:
            if gname not in group_metrics:
                continue
            m = group_metrics[gname]
            pairwise = {}
            for tested in group_names:
                if tested != gname and gname in tester_verdicts:
                    pairwise[tested] = compute_pairwise_agreement(
                        tester_verdicts[gname], ground_truth, tested
                    )
            ct_phase_data[gname] = {
                "tester": gname,
                "short_name": shorten_team_name(gname),
                "classification": m,
                "pairwise_agreement": pairwise,
                "error": None,
            }
        _write_phase_json("cross_testing", ct_phase_data)

    # Coverage phase JSON
    if phases.get("coverage") and coverage_data:
        _write_phase_json("coverage", coverage_data)

    # Commits phase JSON
    if phases.get("commits") and commits_data:
        _write_phase_json("commits", commits_data)

    # ── Write combined group JSON ────────────────────────────────────
    groups_dir = os.path.join(output_dir, "groups")
    os.makedirs(groups_dir, exist_ok=True)
    for gname, data in group_data.items():
        path = os.path.join(groups_dir, f"{gname}.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    print(f"\nPer-group combined JSON written to {groups_dir}/")

    # ── Write per-phase summaries ────────────────────────────────────
    _write_phase_summaries(
        output_dir, group_data, group_names, all_features, phases, now
    )

    # ── Print summary to stdout ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for gname in group_names:
        d = group_data.get(gname, {})
        short_name = shorten_team_name(gname)
        ts = d.get("teacher_evaluation", {}).get("total_score", 0)
        ts_new = d.get("teacher_evaluation", {}).get("teacher_score", 0)
        ft = d.get("feature_tally", {})
        tt = d.get("test_tally", {})
        vt = d.get("test_quality", {}).get("valid_tests", 0)
        ttests = d.get("test_quality", {}).get("total_tests", 0)
        rm = d.get("test_quality", {}).get("removed_tests", 0)
        feat_str = _fmt_tally(ft) if ft else "n/a"
        test_str = _fmt_tally(tt) if tt else "n/a"
        parts = [f"  {short_name:20s}  avg={ts:.2f}  teacher={ts_new:.4f}"]
        if phases["self_evaluation"]:
            ss = d.get("self_evaluation", {}).get("total_score", 0)
            parts.append(f"self={ss:.2f}")
        if phases["cross_testing"]:
            f1 = d.get("test_quality", {}).get("f1", 0)
            parts.append(f"F1={f1:.2f}")
        if phases.get("commits") and d.get("commits"):
            grade = d["commits"].get("group_metrics", {}).get("quality_grade", "?")
            parts.append(f"commits={grade}")
        parts.append(f"feat={feat_str}  tests={test_str}")
        parts.append(f"suite={vt}/{ttests}  removed={rm}")
        print("  ".join(parts))

    print(f"\nOutput written to {output_dir}/")


def _write_phase_summaries(
    output_dir, group_data, group_names, all_features, phases, now
):
    """Write _summary.json for each enabled phase."""

    if phases.get("teacher_evaluation"):
        phase_dir = os.path.join(output_dir, "teacher_eval")
        if os.path.isdir(phase_dir):
            # Feature rankings
            feature_stats = {}
            for feat in all_features:
                counts = {
                    "validated": 0,
                    "almost": 0,
                    "missed": 0,
                    "not_implemented": 0,
                }
                for gname in group_names:
                    fd = group_data.get(gname, {}).get("features_detail", {}).get(feat)
                    if fd is None:
                        counts["not_implemented"] += 1
                    else:
                        counts[fd.get("status", "missed")] += 1
                total = sum(counts.values())
                counts["success_rate"] = (
                    round(counts["validated"] / total, 4) if total else 0
                )
                feature_stats[feat] = counts

            # Group rankings
            rankings = []
            for gname in group_names:
                d = group_data.get(gname, {})
                rankings.append(
                    {
                        "team": gname,
                        "short_name": shorten_team_name(gname),
                        "teacher_score": d.get("teacher_evaluation", {}).get(
                            "teacher_score", 0
                        ),
                        "total_score": d.get("teacher_evaluation", {}).get(
                            "total_score", 0
                        ),
                        "validated_features": d.get("feature_tally", {}).get(
                            "validated", 0
                        ),
                    }
                )
            rankings.sort(key=lambda x: -x["teacher_score"])

            # Class averages
            scores = [r["teacher_score"] for r in rankings]
            avg_score = sum(scores) / len(scores) if scores else 0
            tallies = [
                group_data.get(g, {}).get("feature_tally", {}) for g in group_names
            ]
            summary = {
                "phase": "teacher_eval",
                "date": now,
                "groups_count": len(group_names),
                "feature_rankings": feature_stats,
                "group_rankings": rankings,
                "class_averages": {
                    "teacher_score": round(avg_score, 4),
                    "validated": round(
                        sum(t.get("validated", 0) for t in tallies)
                        / max(len(tallies), 1),
                        1,
                    ),
                    "almost": round(
                        sum(t.get("almost", 0) for t in tallies) / max(len(tallies), 1),
                        1,
                    ),
                    "missed": round(
                        sum(t.get("missed", 0) for t in tallies) / max(len(tallies), 1),
                        1,
                    ),
                    "not_implemented": round(
                        sum(t.get("not_implemented", 0) for t in tallies)
                        / max(len(tallies), 1),
                        1,
                    ),
                },
            }
            with open(os.path.join(phase_dir, "_summary.json"), "w") as f:
                json.dump(summary, f, indent=2, default=str)

    if phases.get("validation"):
        phase_dir = os.path.join(output_dir, "validation")
        if os.path.isdir(phase_dir):
            rankings = []
            for gname in group_names:
                tq = group_data.get(gname, {}).get("test_quality", {})
                rankings.append(
                    {
                        "team": gname,
                        "short_name": shorten_team_name(gname),
                        "valid_tests": tq.get("valid_tests", 0),
                        "total_tests": tq.get("total_tests", 0),
                        "removed_tests": tq.get("removed_tests", 0),
                        "clean_rate": round(
                            tq.get("cleaned_tests", 0)
                            / max(tq.get("total_tests", 1), 1),
                            4,
                        ),
                    }
                )
            summary = {
                "phase": "validation",
                "date": now,
                "groups_count": len(group_names),
                "group_rankings": sorted(rankings, key=lambda x: -x["valid_tests"]),
            }
            with open(os.path.join(phase_dir, "_summary.json"), "w") as f:
                json.dump(summary, f, indent=2, default=str)

    if phases.get("cross_testing"):
        phase_dir = os.path.join(output_dir, "cross_testing")
        if os.path.isdir(phase_dir):
            rankings = []
            for gname in group_names:
                tq = group_data.get(gname, {}).get("test_quality", {})
                rankings.append(
                    {
                        "team": gname,
                        "short_name": shorten_team_name(gname),
                        "f1": tq.get("f1", 0),
                        "precision": tq.get("precision", 0),
                        "recall": tq.get("recall", 0),
                    }
                )
            summary = {
                "phase": "cross_testing",
                "date": now,
                "groups_count": len(group_names),
                "group_rankings": sorted(rankings, key=lambda x: -x["f1"]),
                "class_averages": {
                    "f1": round(
                        sum(r["f1"] for r in rankings) / max(len(rankings), 1), 4
                    ),
                    "precision": round(
                        sum(r["precision"] for r in rankings) / max(len(rankings), 1), 4
                    ),
                    "recall": round(
                        sum(r["recall"] for r in rankings) / max(len(rankings), 1), 4
                    ),
                },
            }
            with open(os.path.join(phase_dir, "_summary.json"), "w") as f:
                json.dump(summary, f, indent=2, default=str)

    if phases.get("commits"):
        phase_dir = os.path.join(output_dir, "commits")
        if os.path.isdir(phase_dir):
            rankings = []
            for gname in group_names:
                c = group_data.get(gname, {}).get("commits")
                if c:
                    gm = c.get("group_metrics", {})
                    rankings.append(
                        {
                            "team": gname,
                            "short_name": shorten_team_name(gname),
                            "student_commits": c.get("student_commits", 0),
                            "quality_score": gm.get("quality_score", 0),
                            "quality_grade": gm.get("quality_grade", "?"),
                            "conventional_rate": gm.get("conventional_rate", 0),
                            "poor_rate": gm.get("poor_rate", 0),
                            "ai_detected": c.get("ai_detected", {}).get(
                                "detected", False
                            ),
                        }
                    )
            # Grade distribution
            grades = [r["quality_grade"] for r in rankings]
            grade_dist = {}
            for g in grades:
                grade_dist[g] = grade_dist.get(g, 0) + 1
            summary = {
                "phase": "commits",
                "date": now,
                "groups_count": len(group_names),
                "group_rankings": sorted(rankings, key=lambda x: -x["quality_score"]),
                "class_averages": {
                    "quality_score": round(
                        sum(r["quality_score"] for r in rankings)
                        / max(len(rankings), 1),
                        1,
                    ),
                    "student_commits": round(
                        sum(r["student_commits"] for r in rankings)
                        / max(len(rankings), 1),
                        1,
                    ),
                },
                "grade_distribution": grade_dist,
            }
            with open(os.path.join(phase_dir, "_summary.json"), "w") as f:
                json.dump(summary, f, indent=2, default=str)

    if phases.get("coverage"):
        phase_dir = os.path.join(output_dir, "coverage")
        if os.path.isdir(phase_dir):
            rankings = []
            for gname in group_names:
                c = group_data.get(gname, {}).get("coverage")
                if c and not c.get("error"):
                    rankings.append(
                        {
                            "team": gname,
                            "short_name": shorten_team_name(gname),
                            "line_coverage": c.get("line_coverage"),
                            "branch_coverage": c.get("branch_coverage"),
                        }
                    )
            summary = {
                "phase": "coverage",
                "date": now,
                "groups_count": len(group_names),
                "group_rankings": sorted(
                    rankings, key=lambda x: -(x.get("line_coverage") or 0)
                ),
                "class_averages": {
                    "line_coverage": round(
                        sum(r.get("line_coverage") or 0 for r in rankings)
                        / max(len(rankings), 1),
                        4,
                    ),
                    "branch_coverage": round(
                        sum(r.get("branch_coverage") or 0 for r in rankings)
                        / max(len(rankings), 1),
                        4,
                    ),
                },
            }
            with open(os.path.join(phase_dir, "_summary.json"), "w") as f:
                json.dump(summary, f, indent=2, default=str)


if __name__ == "__main__":
    main()
