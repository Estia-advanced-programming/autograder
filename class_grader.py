#!/usr/bin/env python3
"""
Class Grader — batch orchestration and cross-group analysis tool.

Runs the autograder across all student groups, validates test suites,
performs cross-testing, and produces class-wide reports.

Usage:
    python class_grader.py -d <class_dir> -t <teacher_tests> -r <ref_jar> [options]
"""

import argparse
import copy
import json
import os
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
    debug=False,
    dryrun=False,
):
    """Run the autograder as a subprocess and return parsed JSON output.

    Args:
        test_dir: --test-dir for autograder (CWD for Pandora, test file resolution)
        pandora_dir: -P for autograder (manifest/jar/jacoco resolution)
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
    if debug:
        cmd.append("-d")
    cmd.append(jar)

    if dryrun:
        print(f"    $ {shlex.join(cmd)}")
        return None, None

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout * 60)
    except subprocess.TimeoutExpired:
        return None, "autograder process timed out"
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

    return {"precision": precision, "recall": recall, "f1": f1, "agreement": agreement}


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


# ─── Markdown report helpers ───────────────────────────────────────────────


def md_feature_group_matrix(title, all_features, group_names, score_matrix):
    """Build a markdown feature x group matrix.

    score_matrix: {group: {feature: score_or_None}}
    """
    lines = [f"## {title}", ""]
    short_names = [shorten_team_name(g) for g in group_names]
    header = "| Feature | " + " | ".join(short_names) + " |"
    sep = "|---------|" + "|".join(["------"] * len(group_names)) + "|"
    lines += [header, sep]
    for feat in all_features:
        cells = []
        for g in group_names:
            score = score_matrix.get(g, {}).get(feat)
            if score is None:
                cells.append("⚪️")
            else:
                cells.append(badge(score))
        lines.append(f"| {feat} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def md_metrics_table(title, group_metrics):
    """One row per group with precision/recall/f1/agreement."""
    lines = [f"## {title}", ""]
    lines.append("| Team | Precision | Recall | F1 | Agreement |")
    lines.append("|------|-----------|--------|----|-----------|")
    for gname, m in sorted(group_metrics.items(), key=lambda x: -x[1]["f1"]):
        short_name = shorten_team_name(gname)
        lines.append(
            f"| {short_name} | {m['precision']:.2f} | {m['recall']:.2f} "
            f"| {m['f1']:.2f} | {m['agreement']:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def md_agreement_heatmap(title, group_names, pairwise):
    """Tester x tested agreement heatmap."""
    lines = [f"## {title}", ""]
    short_names = [shorten_team_name(g) for g in group_names]
    header = "| tested → | " + " | ".join(short_names) + " |"
    sep = "|----------|" + "|".join(["------"] * len(group_names)) + "|"
    lines += [header, sep]
    for i, tester in enumerate(group_names):
        cells = []
        for tested in group_names:
            if tester == tested:
                cells.append("—")
            else:
                val = pairwise.get((tester, tested), 0)
                cells.append(f"{val:.2f}")
        lines.append(f"| {short_names[i]} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def _fmt_tally(tally):
    return (
        f"\U0001f7e2{tally['validated']} "
        f"\U0001f7e1{tally['almost']} "
        f"\U0001f534{tally['missed']} "
        f"\u26aa{tally['not_implemented']}"
    )


def md_summary_table(group_names, group_data):
    """Per-group summary table."""
    lines = []
    lines.append(
        "| Team | Version | Teacher Score "
        "| Features (\U0001f7e2/\U0001f7e1/\U0001f534/\u26aa) "
        "| Tests (\U0001f7e2/\U0001f7e1/\U0001f534/\u26aa) "
        "| Test Quality (F1) | Valid Tests | Removed |"
    )
    lines.append(
        "|------|---------|---------------"
        "|------------------"
        "|------------------"
        "|-------------------|-------------|---------|"
    )
    for gname in group_names:
        d = group_data.get(gname, {})
        short_name = shorten_team_name(gname)
        version = d.get("version", "?")
        teacher_score = d.get("teacher_evaluation", {}).get("total_score", 0)
        tq = d.get("test_quality", {})
        f1 = tq.get("f1", 0)
        valid = tq.get("valid_tests", 0)
        total = tq.get("total_tests", 0)
        removed = tq.get("removed_tests", 0)
        ft = d.get("feature_tally", {})
        tt = d.get("test_tally", {})
        feat_cell = _fmt_tally(ft) if ft else ""
        test_cell = _fmt_tally(tt) if tt else ""
        lines.append(
            f"| {short_name} | {version} | {teacher_score:.2f} "
            f"| {feat_cell} "
            f"| {test_cell} "
            f"| {f1:.2f} | {valid}/{total} | {removed} |"
        )
    lines.append("")
    return "\n".join(lines)


# ─── CLI ────────────────────────────────────────────────────────────────────


def load_yaml_config(path):
    """Load a YAML configuration file and return a dict of settings.

    Raises SystemExit with a clear message on errors.
    """
    if yaml is None:
        print(
            "Error: PyYAML is required to use --config. Install it with: pip install pyyaml"
        )
        sys.exit(1)

    try:
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: config file not found: {path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error: invalid YAML in {path}: {e}")
        sys.exit(1)

    if not isinstance(cfg, dict):
        print(f"Error: config file must be a YAML mapping, got {type(cfg).__name__}")
        sys.exit(1)

    return cfg


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
        "--json",
        default=None,
        action="store_true",
        help="Also produce per-group JSON files",
    )
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
        help="Fast mode: only run teacher→students and students→teacher, skip cross-testing",
    )
    p.add_argument(
        "--dryrun",
        default=None,
        action="store_true",
        help="Print the autograder commands that would be run without executing them",
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
    "json": "json",
    "timeout": "timeout",
    "debug": "debug",
    "fast": "fast",
    "dryrun": "dryrun",
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── Merge YAML config with CLI args (CLI wins) ───────────────────
    if args.config:
        file_cfg = load_yaml_config(args.config)
        for yaml_key, attr in _YAML_KEY_MAP.items():
            if yaml_key in file_cfg and getattr(args, attr) is None:
                setattr(args, attr, file_cfg[yaml_key])

    # Apply defaults for optional args not set by CLI or config
    if args.output is None:
        args.output = "."
    if args.timeout is None:
        args.timeout = 10
    if args.coverage is None:
        args.coverage = False
    if args.json is None:
        args.json = False
    if args.debug is None:
        args.debug = False
    if args.fast is None:
        args.fast = False
    if args.dryrun is None:
        args.dryrun = False

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
        "debug": args.debug,
        "dryrun": args.dryrun,
    }

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
    self_eval = {}  # group -> autograder JSON result
    validation_results = {}  # group -> (data, valid, invalid)
    group_manifests = {}  # group -> manifest features list

    # Pre-load all manifests
    for gname, gpath in groups:
        manifest = load_manifest(gpath)
        group_manifests[gname] = manifest.get("features", []) if manifest else []

    # ── 3.1 Teacher Tests → Student Pandoras ──────────────────────────
    print("\n=== Teacher Tests → Student Pandoras ===")
    for gname, gpath in groups:
        jar = group_jar(gpath)
        manifest_path = group_manifest(gpath)
        if not os.path.isfile(jar):
            print(f"  [{gname}] SKIP: target/pandora.jar not found")
            continue
        if not os.path.isfile(manifest_path):
            print(f"  [{gname}] SKIP: manifest.json not found")
            continue

        mfeats = group_manifests[gname]

        print(f"  [{gname}] running teacher tests...")
        data, err = run_autograder(
            jar=jar,
            test_suite=teacher_tests,
            manifest=manifest_path,
            test_dir=teacher_workdir,
            coverage=cfg["coverage"],
            jacoco=cfg.get("jacoco"),
            timeout=cfg["timeout"],
            debug=cfg["debug"],
            dryrun=cfg["dryrun"],
        )
        if data is None and err is None:
            continue
        if err:
            print(f"  [{gname}] ERROR: {err}")
            continue
        teacher_eval[gname] = data
        teacher_scores[gname] = extract_feature_scores(data, all_features, mfeats)
        ft = data.get("tally", {})
        tt = data.get("test_tally", {})
        print(
            f"  [{gname}] total: {data.get('total_score', 0):.2f}  "
            f"features: {_fmt_tally(ft)}  tests: {_fmt_tally(tt)}"
        )

    fast_mode = args.fast

    # ── 3.2 Student Tests → Teacher Pandora (validation) ─────────────
    if not fast_mode:
        print("\n=== Student Tests → Teacher Pandora (validation) ===")
        for gname, gpath in groups:
            ts = group_test_suite(gpath)
            if not os.path.isfile(ts):
                print(f"  [{gname}] SKIP: no testSuite.json")
                continue

            print(f"  [{gname}] validating test suite...")
            data, valid, invalid, removed = validate_test_suite(
                gname, gpath, ref_jar, cfg
            )
            validation_results[gname] = (data, valid, invalid, removed)
            if data:
                print(
                    f"  [{gname}] valid: {len(valid)}, invalid: {len(invalid)}, removed: {len(removed)}"
                )
            elif removed:
                print(
                    f"  [{gname}] all tests removed ({len(removed)} broken/non-whitelisted)"
                )

    if not fast_mode:
        # ── Self-evaluation (student tests → own Pandora) ────────────────
        print("\n=== Self-Evaluation (Student Tests → Own Pandora) ===")
        for gname, gpath in groups:
            jar = group_jar(gpath)
            cleaned_ts = group_cleaned_test_suite(gpath)
            manifest_path = group_manifest(gpath)
            if not (os.path.isfile(jar) and os.path.isfile(manifest_path)):
                continue

            if not os.path.isfile(cleaned_ts):
                print(f"  [{gname}] SKIP: no cleaned test suite available")
                continue

            print(f"  [{gname}] self-evaluation (using cleaned tests)...")

            data, err = run_autograder(
                jar=jar,
                test_suite=cleaned_ts,
                manifest=manifest_path,
                test_dir=gpath,
                timeout=cfg["timeout"],
                debug=cfg["debug"],
                dryrun=cfg["dryrun"],
            )
            if data is None and err is None:
                continue
            if err:
                print(f"  [{gname}] ERROR: {err}")
                continue
            self_eval[gname] = data
            print(f"  [{gname}] self-score: {data.get('total_score', 0):.2f}")

        # ── 3.3 Cross-Testing ────────────────────────────────────────────
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

        for tester_name, tester_path in groups:
            cleaned_ts = group_cleaned_test_suite(tester_path)
            if not os.path.isfile(cleaned_ts):
                continue

            tester_verdicts[tester_name] = {}
            print(f"  [{tester_name}] cross-testing against other groups...")

            for tested_name, tested_path in groups:
                if tested_name == tester_name:
                    continue
                jar = group_jar(tested_path)
                manifest_path = group_manifest(tested_path)
                if not (os.path.isfile(jar) and os.path.isfile(manifest_path)):
                    continue

                data, err = run_autograder(
                    jar=jar,
                    test_suite=cleaned_ts,
                    manifest=manifest_path,
                    test_dir=tester_path,
                    timeout=cfg["timeout"],
                    debug=cfg["debug"],
                    dryrun=cfg["dryrun"],
                )
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

        # Pairwise agreement
        pairwise_agreement = {}
        for tester_name in group_names:
            if tester_name not in tester_verdicts:
                continue
            for tested_name in group_names:
                if tester_name == tested_name:
                    continue
                pairwise_agreement[(tester_name, tested_name)] = (
                    compute_pairwise_agreement(
                        tester_verdicts[tester_name], ground_truth, tested_name
                    )
                )
    else:
        print(
            "\n=== Fast mode: skipping validation, self-evaluation and cross-testing ==="
        )
        group_metrics = {}
        pairwise_agreement = {}

    # ── Build per-group JSON data ────────────────────────────────────
    group_data = {}
    for gname in group_names:
        te = teacher_eval.get(gname, {})
        se = self_eval.get(gname, {})
        vr = validation_results.get(gname, (None, [], [], []))
        _, valid, invalid, removed = vr
        metrics = group_metrics.get(
            gname, {"precision": 0, "recall": 0, "f1": 0, "agreement": 0}
        )

        group_data[gname] = {
            "team": gname,
            "version": te.get("version", "?"),
            "feature_tally": te.get("tally", {}),
            "test_tally": te.get("test_tally", {}),
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
                "precision": metrics.get("precision", 0),
                "recall": metrics.get("recall", 0),
                "f1": metrics.get("f1", 0),
                "agreement": metrics.get("agreement", 0),
            },
            "coverage": {
                "teacher_suite": None,
                "student_suite": None,
            },
        }

    # ── Write per-group JSON ─────────────────────────────────────────
    if args.json:
        json_dir = os.path.join(output_dir, "json")
        os.makedirs(json_dir, exist_ok=True)
        for gname, data in group_data.items():
            path = os.path.join(json_dir, f"{gname}.json")
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        print(f"\nPer-group JSON written to {json_dir}/")

    # ── Generate Markdown reports ────────────────────────────────────
    # Validation scores matrix (student tests → teacher pandora)
    validation_scores = {}
    for gname, gpath in groups:
        vr = validation_results.get(gname, (None, [], [], []))
        vdata = vr[0]
        mfeats = group_manifests.get(gname, [])
        if vdata:
            validation_scores[gname] = extract_feature_scores(
                vdata, all_features, mfeats
            )
        else:
            validation_scores[gname] = {f: None for f in all_features}

    # Load teacher test suite to get test count
    try:
        with open(teacher_tests, "r") as f:
            teacher_test_list = json.load(f)
        teacher_test_count = len(teacher_test_list)
    except Exception:
        teacher_test_count = "?"
    teacher_tests_name = os.path.basename(teacher_tests)

    report_parts = []
    report_parts.append("# Class Grader Report\n")

    # Add CSS for vertical column headers in Quarto
    css_block = """```{=html}
<style>
/* Vertical column headers for feature matrices */
table thead th:not(:first-child) {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    vertical-align: bottom;
    padding: 0.2em 0.5em;
    min-height: 150px;
    white-space: nowrap;
}

/* Keep first column (Feature/Team) horizontal */
table thead th:first-child {
    writing-mode: horizontal-tb;
    text-align: left;
}
</style>
```

"""
    report_parts.append(css_block)

    # ── Legend ────────────────────────────────────────────────────────
    report_parts.append("""\
## Legend

| Badge | Meaning | Score range |
|-------|---------|-------------|
| 🟢 | **Validated** — the feature/test passes | score ≥ 0.9 |
| 🟡 | **Almost** — close but not passing | 0.5 ≤ score < 0.9 |
| 🔴 | **Missed** — the feature was attempted but the output is wrong | score < 0.5 |
| ⚪️ | **Not implemented / not declared** — the feature is not listed in the team's manifest or was not found in the output | — |

""")

    # ── Teacher Evaluation ───────────────────────────────────────────
    report_parts.append(f"""\
## Teacher Evaluation (Teacher Tests → Student Pandoras)

**Goal**: measure how well each team's Pandora implements the expected features.

The teacher's test suite (`{teacher_tests_name}`, **{teacher_test_count} tests** \
covering **{len(all_features)} features**) is run against each team's JAR.
For every feature, the autograder compares the student's output to the expected \
value with a numeric tolerance. The per-feature score is the average across all \
tests for that feature (1.0 = perfect match, 0.0 = completely wrong or missing).

Only features declared in the team's `manifest.json` are evaluated; \
undeclared features appear as ⚪️.

""")
    report_parts.append(
        md_feature_group_matrix(
            "Results",
            all_features,
            group_names,
            teacher_scores,
        )
    )

    # ── Test Suite Validation ────────────────────────────────────────
    if not fast_mode:
        report_parts.append("""\
## Test Suite Validation (Student Tests → Teacher Pandora)

**Goal**: assess the quality of each team's own test suite.

Each team's `testSuite.json` is first **cleaned** (tests referencing missing \
files or non-whitelisted features are removed), then run against the \
**reference implementation** (teacher's JAR, which is assumed to be correct).

A test that passes against the reference is **valid** — it checks something \
that the correct implementation actually produces. A test that fails is \
**invalid** — the expected value in the test is wrong.

""")
        report_parts.append(
            md_feature_group_matrix(
                "Results",
                all_features,
                group_names,
                validation_scores,
            )
        )

    # ── Cross-Testing Metrics ────────────────────────────────────────
    if not fast_mode:
        if group_metrics:
            report_parts.append("""\
## Test Quality Metrics (Cross-Testing)

**Goal**: evaluate how accurately each team's tests distinguish correct from \
incorrect implementations.

Each team's cleaned test suite is run against **every other team's** Pandora. \
The results are compared to the ground truth (teacher evaluation) to compute \
classification metrics:

| Metric | Definition |
|--------|------------|
| **Precision** | Of the features your tests mark as "passing", how many actually pass? High precision = few false positives. |
| **Recall** | Of the features that actually pass, how many do your tests detect? High recall = few false negatives. |
| **F1** | Harmonic mean of precision and recall — the single best measure of test quality. |
| **Agreement** | Overall rate at which your tests agree with the teacher evaluation. |

""")
            report_parts.append(
                md_metrics_table("Results", group_metrics)
            )
        if pairwise_agreement:
            report_parts.append("""\
## Pairwise Agreement Heatmap

Each cell shows the agreement rate between one team's tests (row) and \
another team's Pandora (column). A value of 1.00 means the tester's \
tests agree with the teacher evaluation for every feature of the tested team.

""")
            report_parts.append(
                md_agreement_heatmap(
                    "Results", group_names, pairwise_agreement
                )
            )

    # ── Class Summary ────────────────────────────────────────────────
    report_parts.append(f"""\
## Class Summary

One row per team. The **Features** and **Tests** columns show how many \
items fall in each category:
🟢 validated · 🟡 almost · 🔴 missed · ⚪ not implemented.

- **Teacher Score**: average across all evaluated tests from the teacher suite.
- **Features (🟢/🟡/🔴/⚪)**: per-feature tally after aggregating test scores.
- **Tests (🟢/🟡/🔴/⚪)**: per-individual-test tally.
- **Test Quality (F1)**: F1 score from cross-testing (0 in fast mode).
- **Valid Tests**: how many of the team's own tests pass against the reference / total tests.
- **Removed**: tests dropped before evaluation (missing files, non-whitelisted features).

""")
    report_parts.append(md_summary_table(group_names, group_data))

    report_text = "\n".join(report_parts)
    report_path = os.path.join(output_dir, "class_report.md")
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"\nClass report written to {report_path}")

    # ── Print summary to stdout ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for gname in group_names:
        d = group_data.get(gname, {})
        short_name = shorten_team_name(gname)
        ts = d.get("teacher_evaluation", {}).get("total_score", 0)
        ft = d.get("feature_tally", {})
        tt = d.get("test_tally", {})
        vt = d.get("test_quality", {}).get("valid_tests", 0)
        ttests = d.get("test_quality", {}).get("total_tests", 0)
        rm = d.get("test_quality", {}).get("removed_tests", 0)
        feat_str = _fmt_tally(ft) if ft else "n/a"
        test_str = _fmt_tally(tt) if tt else "n/a"
        if fast_mode:
            print(
                f"  {short_name:20s}  teacher={ts:.2f}  "
                f"feat={feat_str}  tests={test_str}  "
                f"suite={vt}/{ttests}  removed={rm}"
            )
        else:
            ss = d.get("self_evaluation", {}).get("total_score", 0)
            f1 = d.get("test_quality", {}).get("f1", 0)
            print(
                f"  {short_name:20s}  teacher={ts:.2f}  self={ss:.2f}  "
                f"F1={f1:.2f}  feat={feat_str}  tests={test_str}  "
                f"suite={vt}/{ttests}  removed={rm}"
            )


if __name__ == "__main__":
    main()
