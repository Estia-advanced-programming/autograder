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
        "-p", "--profile", metavar="PATH",
        help="Profile YAML for source selection",
    )
    build_p.add_argument(
        "-s", "--sources", nargs="+", metavar="PATH",
        help="Explicit YAML source files or directories",
    )
    build_p.add_argument(
        "-o", "--output", default="testSuite.json", metavar="PATH",
        help="Output path (default: testSuite.json)",
    )
    build_p.add_argument(
        "-d", "--tests-dir", default="tests/", metavar="PATH",
        help="Root directory for YAML sources (default: tests/)",
    )
    build_p.add_argument(
        "--id-start", type=int, default=1000000, metavar="N",
        help="Starting ID offset (default: 1000000)",
    )
    build_p.add_argument(
        "--dry-run", action="store_true",
        help="Print summary without writing output",
    )

    # ── list ──
    list_p = sub.add_parser("list", help="List available sources and profiles")
    list_p.add_argument(
        "-d", "--tests-dir", default="tests/", metavar="PATH",
        help="Root directory for YAML sources (default: tests/)",
    )

    # ── check ──
    check_p = sub.add_parser("check", help="Validate YAML source files")
    check_p.add_argument(
        "-p", "--profile", metavar="PATH",
        help="Profile YAML for source selection",
    )
    check_p.add_argument(
        "-s", "--sources", nargs="+", metavar="PATH",
        help="Explicit YAML source files or directories",
    )
    check_p.add_argument(
        "-d", "--tests-dir", default="tests/", metavar="PATH",
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
    print("check: not yet implemented (Phase 1)")


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
