# `tests_manager.py` — Implementation Phases

Tracking file for incremental implementation. Each phase is a commit checkpoint.

---

## Phase 0 — Scaffold
- [x] Create `tests_manager.py` with imports and lazy YAML import
- [x] `main()` + argparse with `build` / `list` / `check` subcommands
- [x] Shared helpers: `fatal()`, `warn()`, `load_yaml()`, `load_json()`, `resolve_path()`
- [x] Runnable: `python tests_manager.py --help` works, subcommands print stubs

## Phase 1 — YAML Loading & Validation
- [ ] `load_test_source(path)` — parse one `.yml`, return dict
- [ ] `validate_source(src, path)` — schema checks (mode, conditionals, result/error)
- [ ] Load `features-whitelist.json` for non-fatal warnings
- [ ] `check` command wired: validates selected files, prints summary

## Phase 2 — Expansion Engine
- [ ] `expand_source(src, source_index, id_counter)` → list of flat test dicts
- [ ] Handle all 8 YAML types: full-report features, full+group, feature-mode, feature+phase, metadata, parameters, multi-file, errors
- [ ] File-level defaults inheritance (`mode`, `file`, `option`, `group`, `milestone`)
- [ ] Entry-level override of any default

## Phase 3 — Profile Resolution
- [ ] `load_profile(path)` — parse profile YAML
- [ ] `resolve_sources(profile, tests_dir)` — include/exclude/glob logic
- [ ] `--sources` alternative: direct file/dir list without profile
- [ ] Feature-level post-filter (profile `features` key)

## Phase 4 — ID Allocation & Build Command
- [ ] Sort source files alphabetically for determinism
- [ ] ID = `source_index * 1000 + test_index` + `--id-start` offset
- [ ] `write_test_suite(tests, output_path)` — JSON output (no null keys, sorted)
- [ ] `--dry-run` mode: print summary without writing
- [ ] `build` command wired end-to-end

## Phase 5 — `list` Command
- [ ] Discover all `*.yml` in `tests/` and `profiles/` recursively
- [ ] Print organized listing (sources by directory, profiles separately)
- [ ] Show per-file test count

## Phase 6 — File-reference Validation & Whitelist Warnings
- [ ] `check` verifies every `file` path exists on disk
- [ ] Warn on feature/metadata names not in `features-whitelist.json`
- [ ] Warn on duplicate features within a file block
- [ ] Exit code 1 on errors, 0 on warnings-only

## Phase 7 — Integration Test
- [ ] Create a small sample YAML source file under `test/tests/`
- [ ] Build it and compare output against known-good JSON subset
- [ ] Verify `check`, `list`, `--dry-run` on the sample
