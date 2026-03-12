#!/usr/bin/env python3
"""
Autograder for Pandora — a flight-recorder data analysis Java project.

Runs a JSON test suite against a student's Pandora JAR, compares outputs
to expected results, and produces grading reports (summary, markdown, JSON).

Usage:
    python autograder.py [options] <path_to_pandora_jar>

See --help for full option list.
"""

import argparse
import concurrent.futures
import json
import math
import os
import subprocess
import sys
import time

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

# ─── Scoring helpers ────────────────────────────────────────────────────────

SCORE_FACTOR = 50


def numeric_score(difference):
    """Exponential-decay score for numeric comparison. 1.0 on exact match."""
    f = SCORE_FACTOR
    return math.floor(pow(f * f, 1 - abs(difference)) / f) / f


def levenshtein_normalised(s1, s2):
    """Return normalised Levenshtein distance in [0, 1]. 0 = identical."""
    if len(s1) < len(s2):
        return levenshtein_normalised(s2, s1)
    if len(s2) == 0:
        return 1.0
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            current_row.append(
                min(
                    previous_row[j + 1] + 1,  # insertion
                    current_row[j] + 1,  # deletion
                    previous_row[j] + (c1 != c2),  # substitution
                )
            )
        previous_row = current_row
    return previous_row[-1] / len(s1)


def compare_output(actual, expected):
    """Score an actual output string against an expected value (0.0–1.0)."""
    if isinstance(expected, (int, float)):
        try:
            return numeric_score(abs(float(actual) - expected))
        except (ValueError, TypeError):
            return 0.0
    if isinstance(expected, str):
        return 1.0 - levenshtein_normalised(actual, expected)
    return 0.0


# ─── Output normalisation ──────────────────────────────────────────────────


def normalise_output(raw_bytes):
    """Decode and normalise subprocess stdout."""
    text = raw_bytes.decode(errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "    ")
    text = text.replace("\n", os.linesep)
    return text.strip()


# ─── Command execution ─────────────────────────────────────────────────────


def run_command(command, timeout, debug, cwd=None):
    """Run *command* in a shell, return normalised stdout or 'TIMEOUT'."""
    if debug:
        print(f"[debug] {command}")
    proc = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=cwd
    )
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        if debug:
            print("[debug] command timed out")
        return "TIMEOUT"
    return normalise_output(stdout)


# ─── Java command builder ──────────────────────────────────────────────────


def build_java_command(
    jar_path,
    *,
    file=None,
    files=None,
    options=None,
    coverage=False,
    jacoco_path=None,
    jacoco_append=True,
):
    """Build a ``java -jar`` invocation string."""
    parts = ["java"]
    if coverage and jacoco_path:
        append = ",append=true" if jacoco_append else ""
        parts.append(f"-javaagent:{jacoco_path}=destfile=target/jacoco.exec{append}")
    parts += ["-Duser.country=US", "-Duser.language=en", "-jar", jar_path]
    if options:
        parts.extend(options)
    if files:
        parts.extend(files)
    elif file:
        parts.append(file)
    return " ".join(parts)


# ─── Version utilities ──────────────────────────────────────────────────────


def parse_version(version_string):
    """Strip leading 'v' and split into a comparable tuple of ints."""
    v = version_string.strip().lstrip("v")
    if v.lower().startswith("pandora@"):
        v = v[len("pandora@") :]
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def format_version(version_tuple):
    return ".".join(str(x) for x in version_tuple)


# ─── Test category helpers ──────────────────────────────────────────────────


def test_category(test):
    """Return the manifest key that must be present for this test to run.

    If 'group' is set, it overrides the default category — the manifest must
    list the group value (e.g. 'imperial') for the test to be included.
    """
    if test.get("group"):
        return test["group"]
    if test.get("metadata"):
        return "metadata"
    if test.get("parameter"):
        return test.get("parameter", "")
    return test.get("feature", "")


def test_aggregation_key(test):
    """Return the key under which this test's score is aggregated in feature scores.

    If 'group' is set, all tests sharing the same group are aggregated together
    under that group name instead of their individual feature/metadata/parameter.
    """
    if test.get("group"):
        return test["group"]
    if test.get("metadata"):
        return "metadata"
    if test.get("parameter"):
        return test["parameter"]
    return test.get("feature", "unknown")


def test_display_name(test):
    """Human-readable label for the test target."""
    base = None
    if test.get("metadata"):
        base = f"metadata:{test['metadata']}"
    elif test.get("parameter"):
        base = test["parameter"]
    else:
        base = test.get("feature", "?")
    if test.get("group"):
        return f"{test['group']}:{base}"
    return base


# ─── Filtering ──────────────────────────────────────────────────────────────


def validate_features(features, source="manifest", warn=True):
    """Validate features against the whitelist.

    If no whitelist is loaded, all features are allowed.

    Args:
        features: List of feature names to validate
        source: Description of the source (for error messages)
        warn: If True, print warnings for invalid features

    Returns:
        List of valid features (filtered to only those in whitelist)
    """
    if ALLOWED_FEATURES is None:
        return features

    valid = []
    invalid = []

    for feature in features:
        if feature in ALLOWED_FEATURES:
            valid.append(feature)
        else:
            invalid.append(feature)

    if invalid and warn:
        print(
            f"WARNING: {source} contains invalid features that will be ignored:",
            file=sys.stderr,
        )
        for feat in invalid:
            print(f"  - {feat}", file=sys.stderr)

    return valid


def validate_test_features(tests, warn=True):
    """Validate features/parameters/metadata used in tests against whitelist.

    If no whitelist is loaded, all features are allowed.

    Args:
        tests: List of test dictionaries
        warn: If True, print warnings for invalid features

    Returns:
        List of invalid features found in tests
    """
    if ALLOWED_FEATURES is None:
        return []

    invalid = []
    seen = set()

    for test in tests:
        # Check feature field
        if "feature" in test and test["feature"]:
            feat = test["feature"]
            if feat not in ALLOWED_FEATURES and feat not in seen:
                invalid.append(feat)
                seen.add(feat)

        # Check parameter field
        if "parameter" in test and test["parameter"]:
            param = test["parameter"]
            if (
                ALLOWED_PARAMETERS is not None
                and param not in ALLOWED_PARAMETERS
                and param not in seen
            ):
                invalid.append(param)
                seen.add(param)

        # Check metadata field - check against metadata_allowed
        if "metadata" in test and test["metadata"]:
            meta = test["metadata"]
            if (
                ALLOWED_METADATA is not None
                and meta not in ALLOWED_METADATA
                and meta not in seen
            ):
                invalid.append(meta)
                seen.add(meta)

    if invalid and warn:
        print(
            f"WARNING: Test suite contains invalid features that will be ignored:",
            file=sys.stderr,
        )
        for feat in invalid:
            print(f"  - {feat}", file=sys.stderr)

    return invalid


def validate_and_generate_test_ids(tests):
    """Ensure all tests have IDs; generate sequential IDs for missing ones."""
    # Find max existing ID
    max_id = 0
    for test in tests:
        if "id" in test:
            try:
                test_id = int(test["id"])
                if test_id > max_id:
                    max_id = test_id
            except (ValueError, TypeError):
                pass

    # Generate IDs for tests missing them
    next_id = max_id + 1
    for test in tests:
        if "id" not in test:
            test["id"] = next_id
            next_id += 1


def filter_tests(tests, implemented_features):
    """Keep only tests whose category appears in the manifest features list."""
    filtered = []
    features_set = set(implemented_features)
    for test in tests:
        cat = test_category(test)
        if cat in features_set:
            test["actual_result"] = ""
            test["score"] = 0.0
            filtered.append(test)
    return filtered


# ─── Test execution ─────────────────────────────────────────────────────────


def _build_feature_command(test, jar_path, cfg):
    """Build the command for a single feature-mode test."""
    options = []
    if test.get("feature") and not test.get("metadata") and not test.get("parameter"):
        options += ["-o", test["feature"]]
    if test.get("metadata"):
        options += ["-m", test["metadata"]]
    if test.get("option"):
        options += test["option"].split()
    if "files" in test:
        file_paths = [resolve_path(f, cfg.get("test_dir")) for f in test["files"]]
        return build_java_command(
            jar_path,
            files=file_paths,
            options=options or None,
            coverage=cfg["coverage"],
            jacoco_path=cfg["jacoco"],
            jacoco_append=True,
        )
    file_path = resolve_path(test["file"], cfg.get("test_dir"))
    return build_java_command(
        jar_path,
        file=file_path,
        options=options or None,
        coverage=cfg["coverage"],
        jacoco_path=cfg["jacoco"],
        jacoco_append=True,
    )


def _run_one_feature_test(test, jar_path, cfg):
    """Run a single feature-mode test (thread-safe)."""
    command = _build_feature_command(test, jar_path, cfg)
    output = run_command(command, cfg["timeout"], cfg["debug"], cwd=cfg.get("pandora_dir"))
    if output == "TIMEOUT":
        test["actual_result"] = "TIMEOUT"
        test["score"] = 0.0
    else:
        test["actual_result"] = output
        test["score"] = compare_output(output, test.get("result", ""))


def run_feature_tests(tests, jar_path, cfg):
    """Execute each feature-mode test individually, optionally in parallel."""
    workers = cfg.get("workers", 1)
    if workers > 1 and len(tests) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_run_one_feature_test, t, jar_path, cfg) for t in tests
            ]
            concurrent.futures.wait(futures)
    else:
        for test in tests:
            _run_one_feature_test(test, jar_path, cfg)


def _run_one_full_group(file, option, group, jar_path, cfg):
    """Run one full-mode group of tests (thread-safe)."""
    options = option.split() if option else None
    if isinstance(file, tuple):
        file_paths = [resolve_path(f, cfg.get("test_dir")) for f in file]
        command = build_java_command(
            jar_path,
            files=file_paths,
            options=options,
            coverage=cfg["coverage"],
            jacoco_path=cfg["jacoco"],
            jacoco_append=True,
        )
    else:
        file_path = resolve_path(file, cfg.get("test_dir"))
        command = build_java_command(
            jar_path,
            file=file_path,
            options=options,
            coverage=cfg["coverage"],
            jacoco_path=cfg["jacoco"],
            jacoco_append=True,
        )
    output = run_command(command, cfg["timeout"], cfg["debug"], cwd=cfg.get("pandora_dir"))
    output_lines = output.split(os.linesep) if output != "TIMEOUT" else []

    for test in group:
        if output == "TIMEOUT":
            test["actual_result"] = "TIMEOUT"
            test["score"] = 0.0
            continue

        lookup_key = (
            test.get("feature") or test.get("metadata") or test.get("parameter", "")
        )
        test["actual_result"] = f"key {lookup_key}: not found"
        test["score"] = 0.0

        for line in output_lines:
            k, _, v = line.partition(":")
            if k.strip() == lookup_key:
                actual = v.strip()
                test["actual_result"] = actual
                test["score"] = compare_output(actual, test["result"])
                break


def run_full_tests(tests, jar_path, cfg):
    """Group full-mode tests by (file, option) and run once per group."""
    groups = {}
    for test in tests:
        if "files" in test:
            key = (tuple(test["files"]), test.get("option", ""))
        else:
            key = (test["file"], test.get("option", ""))
        groups.setdefault(key, []).append(test)

    workers = cfg.get("workers", 1)
    if workers > 1 and len(groups) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_run_one_full_group, file, option, group, jar_path, cfg)
                for (file, option), group in groups.items()
            ]
            concurrent.futures.wait(futures)
    else:
        for (file, option), group in groups.items():
            _run_one_full_group(file, option, group, jar_path, cfg)


# ─── Score aggregation ──────────────────────────────────────────────────────


def average_score(tests):
    scores = [t["score"] for t in tests if "score" in t]
    return sum(scores) / len(scores) if scores else 0.0


def aggregate_feature_scores(tests, implemented_features):
    """Average score per aggregation key (feature name, 'metadata', parameter key)."""
    buckets = {}
    for test in tests:
        key = test_aggregation_key(test)
        buckets.setdefault(key, []).append(test["score"])
    return {k: sum(v) / len(v) for k, v in buckets.items()}


def aggregate_milestone_scores(tests):
    groups = {}
    for t in tests:
        ms = t.get("milestone", 0)
        groups.setdefault(ms, []).append(t)
    return {ms: average_score(ts) for ms, ts in groups.items()}


def group_by_milestone(tests):
    groups = {}
    for t in tests:
        ms = t.get("milestone", 0)
        groups.setdefault(ms, []).append(t)
    return groups


# ─── Pass badge ─────────────────────────────────────────────────────────────


PASS_THRESHOLD = 0.9
PARTIAL_THRESHOLD = 0.5


def badge(score):
    if score >= PASS_THRESHOLD:
        return "🟢"
    if score >= PARTIAL_THRESHOLD:
        return "🟡"
    return "🔴"


def tally_features(feature_scores, tests, all_tests, implemented_features):
    """Count features by validation status.

    Returns dict with keys: validated, almost, missed, not_implemented, total.
    A feature is 'not_implemented' when every test returned 'not found'.
    Features filtered out by the manifest also count as not_implemented.
    TIMEOUT counts as missed.
    """
    # Group run tests by aggregation key
    buckets = {}
    for t in tests:
        key = test_aggregation_key(t)
        buckets.setdefault(key, []).append(t)

    validated = almost = missed = not_implemented = 0
    for key, score in feature_scores.items():
        key_tests = buckets.get(key, [])
        all_not_found = all(
            "not found" in str(t.get("actual_result", "")) for t in key_tests
        )
        if all_not_found and key_tests:
            not_implemented += 1
        elif score >= PASS_THRESHOLD:
            validated += 1
        elif score >= PARTIAL_THRESHOLD:
            almost += 1
        else:
            missed += 1

    # Count features filtered out by the manifest
    features_set = set(implemented_features)
    filtered_out_keys = set()
    for t in all_tests:
        cat = test_category(t)
        if cat not in features_set:
            filtered_out_keys.add(test_aggregation_key(t))
    not_implemented += len(filtered_out_keys)

    return {
        "validated": validated,
        "almost": almost,
        "missed": missed,
        "not_implemented": not_implemented,
        "total": len(feature_scores) + len(filtered_out_keys),
    }


def tally_tests(tests, all_tests, implemented_features):
    """Count individual tests by validation status.

    Returns dict with keys: validated, almost, missed, not_implemented, total.
    Tests filtered out by the manifest count as not_implemented.
    """
    validated = almost = missed = not_implemented = 0
    for t in tests:
        actual = str(t.get("actual_result", ""))
        if "not found" in actual:
            not_implemented += 1
        elif t["score"] >= PASS_THRESHOLD:
            validated += 1
        elif t["score"] >= PARTIAL_THRESHOLD:
            almost += 1
        else:
            missed += 1

    # Count tests filtered out by the manifest
    features_set = set(implemented_features)
    filtered_out = sum(1 for t in all_tests if test_category(t) not in features_set)
    not_implemented += filtered_out

    return {
        "validated": validated,
        "almost": almost,
        "missed": missed,
        "not_implemented": not_implemented,
        "total": len(tests) + filtered_out,
    }


def compute_feature_details(feature_scores, tests):
    """Per-feature detail: score, valid test count, total test count, status.

    Returns {feature: {"score": float, "valid": int, "total": int, "status": str}}
    """
    buckets = {}
    for t in tests:
        key = test_aggregation_key(t)
        buckets.setdefault(key, []).append(t)

    details = {}
    for key, score in feature_scores.items():
        key_tests = buckets.get(key, [])
        total = len(key_tests)
        valid = sum(1 for t in key_tests if t["score"] >= PASS_THRESHOLD)
        all_not_found = all(
            "not found" in str(t.get("actual_result", "")) for t in key_tests
        )
        if all_not_found and key_tests:
            status = "not_implemented"
        elif score >= PASS_THRESHOLD:
            status = "validated"
        elif score >= PARTIAL_THRESHOLD:
            status = "almost"
        else:
            status = "missed"
        details[key] = {
            "score": score,
            "valid": valid,
            "total": total,
            "status": status,
        }
    return details


# ─── Report generators ─────────────────────────────────────────────────────


def _tally_line(tally, label):
    return (
        f"{label}: "
        f"🟢 {tally['validated']} validated  "
        f"🟡 {tally['almost']} almost  "
        f"🔴 {tally['missed']} missed  "
        f"⚪ {tally['not_implemented']} not implemented  "
        f"(total: {tally['total']})"
    )


def report_summary(feature_scores, tally, test_tally):
    """One line per feature with badge."""
    lines = []
    max_len = max((len(k) for k in feature_scores), default=0)
    for feat, score in feature_scores.items():
        lines.append(f"{feat:<{max_len}}  {badge(score)}")
    lines.append("")
    lines.append(_tally_line(tally, "Features"))
    lines.append(_tally_line(test_tally, "Tests"))
    return "\n".join(lines)


def _tally_md(tally):
    return (
        f"🟢 {tally['validated']} validated · "
        f"🟡 {tally['almost']} almost · "
        f"🔴 {tally['missed']} missed · "
        f"⚪ {tally['not_implemented']} not implemented · "
        f"**{tally['total']}** total"
    )


def report_markdown(
    feature_scores,
    tests,
    milestone_scores,
    total_score,
    version_info,
    tally,
    test_tally,
):
    """Full Markdown report."""
    lines = []
    # Version
    lines.append(f"# Autograder Report")
    lines.append("")
    lines.append(f"**Pandora version**: {version_info['reported']}")
    if version_info.get("warning"):
        lines.append(f"> ⚠️ {version_info['warning']}")
    lines.append("")

    # Total
    lines.append(f"**Total Score**: {total_score:.2f}")
    lines.append("")

    # Tallies
    lines.append(f"**Features**: {_tally_md(tally)}")
    lines.append("")
    lines.append(f"**Tests**: {_tally_md(test_tally)}")
    lines.append("")

    # Feature scores
    lines.append("## Feature Scores")
    lines.append("")
    lines.append("| Feature | Pass | Score |")
    lines.append("|---------|------|-------|")
    for feat, score in feature_scores.items():
        lines.append(f"| {feat} | {badge(score)} | {score:.2f} |")
    lines.append("")

    # Per-milestone detail tables
    grouped = group_by_milestone(tests)
    for ms in sorted(grouped.keys(), key=lambda x: (isinstance(x, str), x)):
        ms_tests = grouped[ms]
        lines.append(f"## Milestone {ms}")
        lines.append("")
        lines.append("| id | mode | target | file | expected | actual | Pass | score |")
        lines.append("|----|------|--------|------|----------|--------|------|-------|")
        for t in ms_tests:
            t["file"] = t.get("file", ", ".join(t.get("files", [])))
            lines.append(
                f"| {t['id']} | {t.get('mode','full')} | {test_display_name(t)} "
                f"| {t['file']} | {t['result']} | {t['actual_result']} "
                f"| {badge(t['score'])} | {t['score']:.2f} |"
            )
        lines.append("")

    # Milestone scores
    lines.append("## Milestone Scores")
    lines.append("")
    for ms, sc in milestone_scores.items():
        lines.append(f"- **{ms}**: {sc:.2f}")
    lines.append("")
    lines.append(f"**Total Score**: {total_score:.2f}")

    return "\n".join(lines)


def report_json(
    feature_scores,
    tests,
    milestone_scores,
    total_score,
    implemented_features,
    version_info,
    elapsed,
    tally,
    test_tally,
    feature_details,
    test_suite_metadata=None,
):
    """Build the JSON output dict."""
    data = {
        "version": version_info["reported"],
        "versions": {
            "pandora": version_info["pandora"],
            "manifest": version_info["manifest"],
        },
        "test_suite_metadata": test_suite_metadata,
        "milestone_scores": milestone_scores,
        "total_score": total_score,
        "tally": tally,
        "test_tally": test_tally,
        "features": implemented_features,
        "features_score": feature_scores,
        "features_detail": feature_details,
        "tests_by_milestone": group_by_milestone(tests),
        "time": elapsed,
    }
    if version_info.get("warning"):
        data["version_warning"] = version_info["warning"]
    return data


# ─── Input validation (--check) ────────────────────────────────────────────


def check_inputs(test_suite_path, manifest_path, jar_path, test_dir=None):
    """Validate inputs. Return list of error strings (empty = OK)."""
    errors = []

    # JAR exists
    if not os.path.isfile(jar_path):
        errors.append(f"Pandora JAR not found: {jar_path}")

    # Manifest
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        if "features" not in manifest or not isinstance(manifest["features"], list):
            errors.append("Manifest missing 'features' array.")
        elif ALLOWED_FEATURES is not None:
            # Only validate features if whitelist is loaded
            invalid_features = [
                f for f in manifest["features"] if f not in ALLOWED_FEATURES
            ]
            if invalid_features:
                errors.append(
                    f"Manifest contains invalid features: {', '.join(invalid_features)}"
                )
    except FileNotFoundError:
        errors.append(f"Manifest file not found: {manifest_path}")
    except json.JSONDecodeError as e:
        errors.append(f"Manifest is not valid JSON: {e}")

    # Test suite
    try:
        with open(test_suite_path, "r") as f:
            raw = json.load(f)
        # Support dict-with-metadata or plain array format
        if isinstance(raw, dict):
            tests = raw.get("tests", [])
        elif isinstance(raw, list):
            tests = raw
        else:
            tests = None
            errors.append(
                "Test suite must be a JSON array or an object with a 'tests' key."
            )
        if tests is not None and not isinstance(tests, list):
            errors.append("Test suite 'tests' value must be a JSON array.")
            tests = None
        if tests is not None:
            # Collect invalid features from test suite
            invalid_test_features = set()

            for i, t in enumerate(tests):
                if "id" not in t:
                    errors.append(f"Test #{i}: missing 'id' field.")
                if "file" not in t and "files" not in t:
                    errors.append(f"Test #{i}: missing 'file' field.")
                elif "files" in t:
                    for f in t["files"]:
                        if not os.path.isfile(resolve_path(f, test_dir)):
                            errors.append(f"Test #{i}: file not found: {f}")
                elif not os.path.isfile(resolve_path(t["file"], test_dir)):
                    errors.append(f"Test #{i}: file not found: {t['file']}")
                if "result" not in t:
                    errors.append(f"Test #{i}: missing 'result' field.")
                if not (t.get("feature") or t.get("metadata") or t.get("parameter")):
                    errors.append(
                        f"Test #{i} (id={t.get('id','?')}): "
                        "must have 'feature', 'metadata', or 'parameter'."
                    )

                # Check feature/parameter/metadata against whitelist (only if loaded)
                if ALLOWED_FEATURES is not None:
                    if t.get("feature") and t["feature"] not in ALLOWED_FEATURES:
                        invalid_test_features.add(t["feature"])
                if ALLOWED_PARAMETERS is not None:
                    if t.get("parameter") and t["parameter"] not in ALLOWED_PARAMETERS:
                        invalid_test_features.add(t["parameter"])
                if ALLOWED_METADATA is not None:
                    if t.get("metadata") and t["metadata"] not in ALLOWED_METADATA:
                        invalid_test_features.add(t["metadata"])

            if invalid_test_features:
                errors.append(
                    f"Test suite contains invalid features: {', '.join(sorted(invalid_test_features))}"
                )
    except FileNotFoundError:
        errors.append(f"Test suite file not found: {test_suite_path}")
    except json.JSONDecodeError as e:
        errors.append(f"Test suite is not valid JSON: {e}")

    return errors


# ─── CLI ────────────────────────────────────────────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(
        description="Autograder for the Pandora flight-recorder project.",
        usage="python autograder.py [options] <path_to_pandora_jar>",
    )
    p.add_argument("jar", help="Path to the Pandora JAR file")

    # Path options
    p.add_argument(
        "-P",
        "--pandora-workdir",
        default=None,
        help="Project root for Pandora artifacts (manifest, JAR, JaCoCo); "
        "relative paths for -m, -j, and the JAR argument resolve from here",
    )
    p.add_argument(
        "--test-dir",
        default=None,
        help="Root for test data; -t resolves from here and test file "
        "paths inside the test suite are prefixed with this directory",
    )
    p.add_argument(
        "-t",
        "--tests",
        default="./test/testSuite.json",
        help="Path to test suite JSON (default: ./test/testSuite.json)",
    )
    p.add_argument(
        "-m",
        "--manifest",
        default="./manifest.json",
        help="Path to manifest JSON (default: ./manifest.json)",
    )
    p.add_argument(
        "-j",
        "--jacoco",
        default="target/jacocoagent.jar",
        help="Path to JaCoCo agent JAR",
    )

    # Output options
    output_group = p.add_mutually_exclusive_group()
    output_group.add_argument(
        "--summary", action="store_true", help="Compact per-feature badge output"
    )
    output_group.add_argument(
        "--report", action="store_true", help="Full Markdown report (default)"
    )
    p.add_argument(
        "-f",
        "--format",
        choices=["json", "md"],
        default=None,
        help="Output format (json or md)",
    )
    p.add_argument(
        "-o", "--output", default=None, help="Write output to this file path"
    )

    # Execution options
    p.add_argument(
        "-c", "--coverage", action="store_true", help="Enable JaCoCo code coverage"
    )
    p.add_argument(
        "-d", "--debug", action="store_true", help="Print executed commands to stdout"
    )
    p.add_argument(
        "-T",
        "--timeout",
        type=int,
        default=10,
        help="Per-command timeout in seconds (default: 10)",
    )
    p.add_argument(
        "-w",
        "--workers",
        type=int,
        default=1,
        help="Number of parallel test workers (default: 1)",
    )
    p.add_argument(
        "--check", action="store_true", help="Validate inputs without running tests"
    )

    return p


def resolve_path(path, workdir):
    """If *workdir* is set and *path* is relative, join them."""
    if workdir and not os.path.isabs(path):
        return os.path.join(workdir, path)
    return path


def main():
    parser = build_parser()
    args = parser.parse_args()

    # -P resolves project artifacts: JAR, manifest, jacoco
    pandora_dir = args.pandora_workdir
    jar_path = resolve_path(args.jar, pandora_dir)
    manifest_path = resolve_path(args.manifest, pandora_dir)
    jacoco_path = resolve_path(args.jacoco, pandora_dir)

    # --test-dir resolves test suite path
    test_dir = args.test_dir
    test_suite_path = resolve_path(args.tests, test_dir)

    cfg = {
        "coverage": args.coverage,
        "jacoco": jacoco_path,
        "debug": args.debug,
        "timeout": args.timeout,
        "workers": args.workers,
        "test_dir": test_dir,
        "pandora_dir": pandora_dir,
    }

    # ── --check mode ──────────────────────────────────────────────────
    if args.check:
        errors = check_inputs(test_suite_path, manifest_path, jar_path, test_dir)
        if errors:
            for e in errors:
                print(f"ERROR: {e}")
            sys.exit(1)
        print("All checks passed.")
        sys.exit(0)

    # ── Load inputs ───────────────────────────────────────────────────
    try:
        with open(test_suite_path, "r") as f:
            raw_suite = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Test suite file not found: {test_suite_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Test suite is not valid JSON: {e}")
        print(f"       File: {test_suite_path}")
        sys.exit(1)

    # Support dict-with-metadata or plain array format
    if isinstance(raw_suite, dict):
        test_suite_metadata = raw_suite.get("metadata")
        test_suite = raw_suite.get("tests", [])
    else:
        test_suite_metadata = None
        test_suite = raw_suite

    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Manifest file not found: {manifest_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Manifest is not valid JSON: {e}")
        print(f"       File: {manifest_path}")
        sys.exit(1)

    # ── Validate and generate test IDs ────────────────────────────────
    validate_and_generate_test_ids(test_suite)

    # ── Validate features against whitelist ───────────────────────────
    raw_features = manifest.get("features", [])
    implemented_features = validate_features(
        raw_features, source="Manifest", warn=not args.check
    )

    # Validate test suite features
    validate_test_features(test_suite, warn=not args.check)

    manifest_version_raw = manifest.get("version", "0.0.0")

    # ── Get Pandora version ───────────────────────────────────────────
    version_cmd = build_java_command(
        jar_path,
        options=["--version"],
        coverage=False,
        jacoco_path=jacoco_path,
        jacoco_append=False,
    )
    pandora_version_raw = run_command(version_cmd, cfg["timeout"], cfg["debug"], cwd=pandora_dir)
    if cfg["debug"]:
        print(f"[debug] pandora --version: {pandora_version_raw}")

    # Initialise coverage file if needed
    if cfg["coverage"]:
        help_cmd = build_java_command(
            jar_path,
            options=["--help"],
            coverage=True,
            jacoco_path=jacoco_path,
            jacoco_append=False,
        )
        run_command(help_cmd, cfg["timeout"], cfg["debug"], cwd=pandora_dir)

    # Version comparison
    pandora_v = parse_version(pandora_version_raw)
    manifest_v = parse_version(manifest_version_raw)
    reported_v = max(pandora_v, manifest_v)
    version_info = {
        "pandora": format_version(pandora_v),
        "manifest": format_version(manifest_v),
        "reported": format_version(reported_v),
    }
    if pandora_v != manifest_v:
        version_info["warning"] = (
            f"Version mismatch: manifest declares {format_version(manifest_v)} "
            f"but JAR reports {format_version(pandora_v)}"
        )

    # ── Filter & run tests ────────────────────────────────────────────
    filtered = filter_tests(test_suite, implemented_features)

    start = time.time()

    feature_mode = [t for t in filtered if t.get("mode") == "feature"]
    full_mode = [t for t in filtered if t.get("mode", "full") != "feature"]

    run_feature_tests(feature_mode, jar_path, cfg)
    run_full_tests(full_mode, jar_path, cfg)

    elapsed = time.time() - start

    # ── Aggregate scores ──────────────────────────────────────────────
    feature_scores = aggregate_feature_scores(filtered, implemented_features)
    milestone_scores = aggregate_milestone_scores(filtered)
    total_score = average_score(filtered)
    feature_details = compute_feature_details(feature_scores, filtered)
    tally = tally_features(feature_scores, filtered, test_suite, implemented_features)
    test_tally = tally_tests(filtered, test_suite, implemented_features)

    # ── Determine output mode ─────────────────────────────────────────
    fmt = args.format
    if args.summary:
        fmt = "summary"
    elif args.report:
        fmt = "md"
    elif fmt is None:
        fmt = "md"  # default

    # ── Generate output ───────────────────────────────────────────────
    if fmt == "summary":
        output_text = report_summary(feature_scores, tally, test_tally)
    elif fmt == "json":
        data = report_json(
            feature_scores,
            filtered,
            milestone_scores,
            total_score,
            implemented_features,
            version_info,
            elapsed,
            tally,
            test_tally,
            feature_details,
            test_suite_metadata,
        )
        output_text = json.dumps(data, indent=2, default=str)
    else:
        output_text = report_markdown(
            feature_scores,
            filtered,
            milestone_scores,
            total_score,
            version_info,
            tally,
            test_tally,
        )

    # ── Write or print ────────────────────────────────────────────────
    if args.output:
        out_path = args.output
        # Auto-append extension if missing
        if "." not in os.path.basename(out_path):
            ext = ".json" if fmt == "json" else ".md"
            out_path += ext
        with open(out_path, "w") as f:
            f.write(output_text)
    else:
        print(output_text)

    # Always print total score to stdout
    if args.output or fmt == "summary":
        print(f"Total Score: {total_score:.2f}")
    elif fmt != "json":
        pass  # already in the markdown
    else:
        print(f"Total Score: {total_score:.2f}")


if __name__ == "__main__":
    main()
