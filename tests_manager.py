#!/usr/bin/env python3
"""
Tests Manager — compile YAML test definitions into testSuite.json.

Manages test definitions in human-readable YAML source files and compiles
them into the JSON format consumed by the autograder.

Usage:
    python tests_manager.py <command> [options]

Commands:
    build   Compile YAML sources into testSuite.json
    list    List available YAML source files and profiles
    check   Validate YAML source files
"""

import argparse
import glob
import json
import os
import sys

try:
    import yaml
except ImportError:
    yaml = None

# ─── Helpers ───────────────────────────────────────────────────────────────


def fatal(msg):
    """Print error message to stderr and exit."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    """Print warning message to stderr."""
    print(f"Warning: {msg}", file=sys.stderr)


def require_yaml():
    """Exit with a helpful message if PyYAML is not installed."""
    if yaml is None:
        fatal("PyYAML is required. Install with: pip install pyyaml")


def load_yaml(path):
    """Load and return the contents of a YAML file."""
    require_yaml()
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        fatal(f"file not found: {path}")
    except yaml.YAMLError as e:
        fatal(f"invalid YAML in {path}: {e}")
    if data is None:
        fatal(f"empty YAML file: {path}")
    return data


def load_json(path):
    """Load and return the contents of a JSON file."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        fatal(f"file not found: {path}")
    except json.JSONDecodeError as e:
        fatal(f"invalid JSON in {path}: {e}")


def resolve_path(path, base):
    """If path is relative, resolve it against base directory."""
    if os.path.isabs(path):
        return path
    return os.path.join(base, path)


def collect_yaml_files(path, base):
    """Collect .yml files from a path (file or directory)."""
    full = resolve_path(path, base)
    if os.path.isfile(full):
        return [full]
    if os.path.isdir(full):
        found = sorted(glob.glob(os.path.join(full, "**", "*.yml"), recursive=True))
        if not found:
            warn(f"no .yml files found in {full}")
        return found
    fatal(f"source path not found: {full}")


def load_feature_whitelist():
    """Load features-whitelist.json if available. Returns dict or None."""
    wl_path = os.path.join(os.path.dirname(__file__), "features-whitelist.json")
    if not os.path.isfile(wl_path):
        return None
    return load_json(wl_path)


# ─── YAML source loading & validation ─────────────────────────────────────

VALID_MODES = {"feature", "full"}
DATA_SECTIONS = {"features", "metadata", "parameters", "errors"}
FILE_LEVEL_KEYS = {"desc", "mode", "file", "option", "group", "milestone"} | DATA_SECTIONS


def load_test_source(path):
    """Load a YAML test source file and return its contents as a dict."""
    src = load_yaml(path)
    if not isinstance(src, dict):
        fatal(f"{path}: expected a YAML mapping at top level, got {type(src).__name__}")
    return src


def validate_source(src, path, whitelist=None):
    """Validate a YAML test source. Returns (errors, warnings) lists."""
    errors = []
    warnings = []

    # --- mode ---
    mode = src.get("mode")
    if mode is None:
        errors.append(f"{path}: missing required field 'mode'")
    elif mode not in VALID_MODES:
        errors.append(f"{path}: invalid mode '{mode}' (expected: feature, full)")

    # --- at least one data section ---
    sections_present = [s for s in DATA_SECTIONS if s in src]
    if not sections_present:
        errors.append(
            f"{path}: must contain at least one of: {', '.join(sorted(DATA_SECTIONS))}"
        )

    # --- unknown top-level keys ---
    for key in src:
        if key not in FILE_LEVEL_KEYS:
            warnings.append(f"{path}: unknown top-level key '{key}'")

    # --- validate each data section ---
    if "features" in src:
        _validate_map_section(src["features"], "features", mode, path, whitelist, errors, warnings)

    if "metadata" in src:
        _validate_map_section(src["metadata"], "metadata", mode, path, whitelist, errors, warnings)

    if "parameters" in src:
        _validate_map_section(src["parameters"], "parameters", mode, path, whitelist, errors, warnings)

    if "errors" in src:
        _validate_errors_section(src["errors"], path, errors, warnings)

    return errors, warnings


def _validate_map_section(section, section_name, mode, path, whitelist, errors, warnings):
    """Validate a features/metadata/parameters map section."""
    if not isinstance(section, dict):
        errors.append(f"{path}: '{section_name}' must be a mapping")
        return

    # whitelist check
    wl_key = {
        "features": "features",
        "metadata": "metadata_allowed",
        "parameters": "parameters",
    }.get(section_name)
    allowed = set(whitelist.get(wl_key, [])) if whitelist and wl_key else None

    for name, value in section.items():
        # whitelist warning
        if allowed and name not in allowed:
            warnings.append(f"{path}: {section_name} name '{name}' not in whitelist")

        if mode == "full" and not isinstance(value, list):
            # full-mode: scalar value (one expected result per feature)
            _validate_result_value(value, f"{path}: {section_name}.{name}", errors)
        elif isinstance(value, list):
            # feature-mode: list of test entries
            _validate_entry_list(value, f"{path}: {section_name}.{name}", errors)
        elif mode == "feature":
            errors.append(
                f"{path}: {section_name}.{name}: feature-mode expects a list of entries, got {type(value).__name__}"
            )


def _validate_entry_list(entries, ctx, errors):
    """Validate a list of test entries (feature-mode or parameter)."""
    if not isinstance(entries, list):
        errors.append(f"{ctx}: expected a list of entries")
        return
    for i, entry in enumerate(entries):
        tag = f"{ctx}[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{tag}: entry must be a mapping, got {type(entry).__name__}")
            continue
        # must have file
        if "file" not in entry:
            errors.append(f"{tag}: missing required field 'file'")
        # must have exactly one of result or error
        has_result = "result" in entry
        has_error = "error" in entry
        if has_result and has_error:
            errors.append(f"{tag}: entry has both 'result' and 'error' (need exactly one)")
        elif not has_result and not has_error:
            errors.append(f"{tag}: entry missing 'result' (or 'error' for error tests)")


def _validate_result_value(value, ctx, errors):
    """Validate a scalar result value (full-mode)."""
    if isinstance(value, (str, int, float)):
        return
    errors.append(f"{ctx}: expected a scalar result (str/int/float), got {type(value).__name__}")


def _validate_errors_section(section, path, errors, warnings):
    """Validate the errors section (list of error test entries)."""
    if not isinstance(section, list):
        errors.append(f"{path}: 'errors' must be a list")
        return
    for i, entry in enumerate(entries := section):
        tag = f"{path}: errors[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{tag}: entry must be a mapping")
            continue
        if "file" not in entry:
            errors.append(f"{tag}: missing required field 'file'")
        if "feature" not in entry:
            errors.append(f"{tag}: missing required field 'feature'")
        if "error" not in entry:
            errors.append(f"{tag}: missing required field 'error'")
        if "result" in entry:
            errors.append(f"{tag}: error entries must not have 'result'")


def gather_sources(args):
    """Resolve the list of YAML source files from --sources or --profile."""
    tests_dir = args.tests_dir
    if args.sources:
        files = []
        for s in args.sources:
            files.extend(collect_yaml_files(s, "."))
        return sorted(set(files))
    if getattr(args, "profile", None):
        # Profile resolution — Phase 3, stub for now
        fatal("--profile not yet implemented (Phase 3)")
    # Default: all .yml in tests_dir
    return collect_yaml_files(tests_dir, ".")


# ─── CLI ───────────────────────────────────────────────────────────────────


def build_parser():
    """Build the argument parser with subcommands."""
    p = argparse.ArgumentParser(
        description="Compile YAML test definitions into testSuite.json.",
        usage="python tests_manager.py <command> [options]",
    )
    sub = p.add_subparsers(dest="command", help="Available commands")

    # ── build ──
    build_p = sub.add_parser("build", help="Compile YAML sources into testSuite.json")
    build_p.add_argument(
        "-p",
        "--profile",
        metavar="PATH",
        help="Profile YAML for source selection",
    )
    build_p.add_argument(
        "-s",
        "--sources",
        nargs="+",
        metavar="PATH",
        help="Explicit YAML source files or directories",
    )
    build_p.add_argument(
        "-o",
        "--output",
        default="testSuite.json",
        metavar="PATH",
        help="Output path (default: testSuite.json)",
    )
    build_p.add_argument(
        "-d",
        "--tests-dir",
        default="tests/",
        metavar="PATH",
        help="Root directory for YAML sources (default: tests/)",
    )
    build_p.add_argument(
        "--id-start",
        type=int,
        default=1000000,
        metavar="N",
        help="Starting ID offset (default: 1000000)",
    )
    build_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without writing output",
    )

    # ── list ──
    list_p = sub.add_parser("list", help="List available sources and profiles")
    list_p.add_argument(
        "-d",
        "--tests-dir",
        default="tests/",
        metavar="PATH",
        help="Root directory for YAML sources (default: tests/)",
    )

    # ── check ──
    check_p = sub.add_parser("check", help="Validate YAML source files")
    check_p.add_argument(
        "-p",
        "--profile",
        metavar="PATH",
        help="Profile YAML for source selection",
    )
    check_p.add_argument(
        "-s",
        "--sources",
        nargs="+",
        metavar="PATH",
        help="Explicit YAML source files or directories",
    )
    check_p.add_argument(
        "-d",
        "--tests-dir",
        default="tests/",
        metavar="PATH",
        help="Root directory for YAML sources (default: tests/)",
    )

    return p


# ─── Command stubs ─────────────────────────────────────────────────────────


def cmd_build(args):
    """Build testSuite.json from YAML sources."""
    require_yaml()
    print("build: not yet implemented (Phase 2+)")


def cmd_list(args):
    """List available YAML source files and profiles."""
    require_yaml()
    print("list: not yet implemented (Phase 5)")


def cmd_check(args):
    """Validate YAML source files."""
    require_yaml()
    files = gather_sources(args)
    if not files:
        fatal("no YAML source files found")

    whitelist = load_feature_whitelist()
    total_errors = 0
    total_warnings = 0

    for path in files:
        src = load_test_source(path)
        errs, warns = validate_source(src, path, whitelist)
        total_errors += len(errs)
        total_warnings += len(warns)
        for e in errs:
            print(f"  ERROR: {e}", file=sys.stderr)
        for w in warns:
            print(f"  WARN:  {w}", file=sys.stderr)

    print(f"\nChecked {len(files)} file(s): {total_errors} error(s), {total_warnings} warning(s)")
    if total_errors:
        sys.exit(1)


# ─── Main ──────────────────────────────────────────────────────────────────


COMMANDS = {
    "build": cmd_build,
    "list": cmd_list,
    "check": cmd_check,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
