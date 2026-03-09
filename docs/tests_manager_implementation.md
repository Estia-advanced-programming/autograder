# `tests_manager.py` — Implementation Phases

Tracking file for incremental implementation. Each phase is a commit checkpoint.

---

## Phase 0 — Scaffold
- [x] Create `tests_manager.py` with imports and lazy YAML import
- [x] `main()` + argparse with `build` / `list` / `check` subcommands
- [x] Shared helpers: `fatal()`, `warn()`, `load_yaml()`, `load_json()`, `resolve_path()`
- [x] Runnable: `python tests_manager.py --help` works, subcommands print stubs

## Phase 1 — YAML Loading & Validation
- [x] `load_test_source(path)` — parse one `.yml`, return dict
- [x] `validate_source(src, path)` — schema checks (mode, conditionals, result/error)
- [x] Load `features-whitelist.json` for non-fatal warnings
- [x] `check` command wired: validates selected files, prints summary

## Phase 2 — Expansion Engine
- [x] `expand_source(src, source_index, id_counter)` → list of flat test dicts
- [x] Handle all 8 YAML types: full-report features, full+group, feature-mode, feature+phase, metadata, parameters, multi-file, errors
- [x] File-level defaults inheritance (`mode`, `file`, `option`, `group`, `milestone`)
- [x] Entry-level override of any default

## Phase 3 — Profile Resolution
- [x] `load_profile(path)` — parse profile YAML
- [x] `resolve_sources(profile, tests_dir)` — include/exclude/glob logic
- [x] `--sources` alternative: direct file/dir list without profile
- [x] Feature-level post-filter (profile `features` key)

## Phase 4 — ID Allocation & Build Command
- [x] Sort source files alphabetically for determinism
- [x] ID = `source_index * 1000 + test_index` + `--id-start` offset
- [x] `write_test_suite(tests, output_path)` — JSON output (no null keys, sorted)
- [x] `--dry-run` mode: print summary without writing
- [x] `build` command wired end-to-end

## Phase 5 — `list` Command
- [x] Discover all `*.yml` in `tests/` and `profiles/` recursively
- [x] Print organized listing (sources by directory, profiles separately)
- [x] Show per-file test count

## Phase 6 — File-reference Validation & Whitelist Warnings
- [x] `check` verifies every `file` path exists on disk
- [x] Warn on feature/metadata names not in `features-whitelist.json`
- [x] Warn on duplicate features within a file block
- [x] Exit code 1 on errors, 0 on warnings-only

## Phase 7 — Integration Test
- [x] Create sample YAML sources under `test/tests/` (metadata, multi-file, group/option)
- [x] Build and verify JSON output matches expected shapes
- [x] Verify `check`, `list`, `--dry-run` on the samples
