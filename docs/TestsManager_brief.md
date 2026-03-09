# Tests Manager — Requirements Brief

## 1. Purpose

A Python CLI tool (`tests_manager.py`) that manages test definitions in human-readable YAML files and compiles them into the `testSuite.json` consumed by the autograder. This decouples test *authoring* from the autograder's JSON format, making it easy to:

- Write and comment tests without worrying about JSON structure or ID allocation
- Organize tests into small, thematic YAML files (one per concern)
- Selectively combine subsets of YAML files into different `testSuite.json` profiles (fast check, full grading, error-only, etc.)
- Evolve the test bank across the semester without hand-editing a monolithic JSON array

---

## 2. Design Philosophy

### 2.1 Feature tests vs. Full-report tests

Both kinds are needed for every feature:

| Aspect | Feature-mode tests (`-o`) | Full-report tests (no `-o`) |
|--------|---------------------------|-----------------------------|
| Flight record | **Custom-built** via flightGenerator — one scenario per file (e.g. a "rocket" plane that only goes up for `flightDistance`) | **Real** flight records (`mono/`, `US/`) |
| What it checks | The single-feature output path works | The feature appears correctly in the full report |
| Why both? | Students usually start with `-o` and forget the full report. Testing both catches that. |

### 2.2 Additional test families

| Family | Description | Uses `group` |
|--------|-------------|:---:|
| **Metric / Imperial** | Run full report on US flights with `--metric` or `--imperial`; check a subset of unit-sensitive features | yes |
| **Metadata** | Query metadata fields with `-m`; check against known values in the flight record header | no |
| **Parameters** | Test `-p` (list parameters), `-n` (number of records), `--number`, etc. | no |
| **Edge cases** | Strange-but-valid inputs: one-line flight record, minimal columns, columns in different order | no |
| **Error handling** | Invalid inputs that must produce `ERROR: …` on stderr (missing file, corrupted header, etc.) | no |

### 2.3 Progressive difficulty

| Stage | Audience | Profile |
|-------|----------|---------|
| Early semester (fast check) | Students getting started | Small subset of basic features — quick feedback loop |
| Mid-semester | Students developing more features | Standard feature + full tests, metadata, parameters |
| Final grading | Teacher | Everything: all features, all milestones, metric/imperial, edge cases, error handling |

The tool must make it trivial to produce different `testSuite.json` for each stage by selecting which YAML sources to include.

---

## 3. YAML Source Files

### 3.1 File organization

The YAML test sources and the `.frd` test flight records live side by side under `test/`:

```
test/
  testsFiles/                       # ── flight record files (.frd) ──
    mono/                           # RU single-flight (real)
      0_101_MiG-29A.frd
      0_201_MiG-23MLD.frd
      0_301_Su-25T.frd
      0_401_Su-27.frd
      0_501_Tu-142.frd
    US/                             # US single-flight (real)
      0_601_F-14A.frd
      0_701_F-14B.frd
      0_801_F-15C.frd
      0_901_F-16A.frd
      0_a01_F-15E.frd
    feature/                        # custom-built per-feature (generated)
      avgAlt_1.frd … avgAlt_7.frd
      maxAlt_1.frd … maxAlt_7.frd
      avgAirSpeed_1.frd … avgAirSpeed_7.frd
      maxAirSpeed_1.frd … maxAirSpeed_7.frd
      avgEnginePower_1.frd … avgEnginePower_21.frd
      maxEnginePower_1.frd … maxEnginePower_21.frd
      avgTemp_1.frd … minOxygen_7.frd        # environment sensors
      flightDistance_1.frd … windSpeed_3.frd  # advanced features
      ...                           # more generated as needed
    multi/                          # multi-file / batch (real + generated)
      (planned)
    edge/                           # edge-case .frd files (generated)
      one_line.frd
      minimal_columns.frd
      reordered_columns.frd
      corrupted.frd
      no_header.frd
      incomplete_header.frd

  tests/                            # ── YAML test definitions ──
    full/                           # full-report tests on real flights
      full_mig23.yml
      full_su25.yml
      full_f14.yml
      ...
    feature/                        # feature-mode tests on custom flights
      basic.yml                     # avgAlt, maxAlt, avgAirSpeed, ...
      environment.yml               # avgTemp, avgPressure, avgHumidity, ...
      advanced.yml                  # flightDistance, flightDuration, ...
      phases.yml                    # takeOff, cruise, landing, ...
    metadata/                       # metadata tests
      metadata_ru.yml
      metadata_us.yml
    parameters/                     # parameter tests
      parameters.yml
    units/                          # metric / imperial tests
      metric_f14.yml
      imperial_mig23.yml
    cross/                          # cross-flight / batch tests
      batch_ru.yml
      batch_us.yml
    errors/                         # error-handling tests
      missing_file.yml
      corrupted.yml
      incomplete_header.yml
    edge/                           # edge-case tests
      one_line.yml
      minimal_columns.yml
      reordered_columns.yml

  profiles/                         # ── build profiles ──
    fast.yml
    full_grading.yml
    units_only.yml
```

Each YAML file is small and self-contained. The directory layout is organizational, not functional — the tool discovers all `*.yml` files recursively or is given an explicit list. The `.frd` files live in `testsFiles/` and are referenced by relative path from YAML entries.

### 3.2 YAML Schema

Every YAML source file has a **top-level header** and a **list of test entries**. The header carries defaults that individual entries can override.

#### 3.2.1 Full-report tests (one file → many features)

A single flight record tested against multiple features in full-report mode. Each entry under `features:` or `metadata:` becomes one test object in the JSON output.

```yaml
# full/full_mig23.yml — Full report on MiG-23MLD (RU mono flight)
desc: Full report tests on MiG-23MLD
mode: full
file: test/testsFiles/mono/0_201_MiG-23MLD.frd

features:
  avgAlt: 4874.94
  maxAlt: 14321.05
  avgAirSpeed: 273.38
  maxAirSpeed: 641.15
  flightDuration: "00:12:36"
  # ... more features

metadata:
  flight_id: "201"
  flight_code: MiG-23MLD
  origin: RU
  date: "2011-06-01"
  from: krasnodar pashkovsky
  to: tbilissi-lochini
  motor(s): 1
  mass_aircraft: 41780
```

#### 3.2.2 Full-report tests with group override (metric/imperial)

When `group` is set, the `group` value overrides the aggregation key and the manifest must list it. The `option` field carries the CLI flag.

```yaml
# units/imperial_mig23.yml — Imperial unit tests on MiG-23MLD
desc: Full report on MiG-23MLD in imperial units
mode: full
file: test/testsFiles/mono/0_201_MiG-23MLD.frd
option: "--imperial"
group: imperial

features:
  avgAlt: 15994.56        # feet instead of meters
  maxAlt: 46985.40
  avgAirSpeed: 896.59     # ft/s instead of m/s
  flightDistance: 799.97   # miles instead of m
```

#### 3.2.3 Feature-mode tests (one feature → many files)

Custom-built flight records targeting a single feature, each with a specific scenario.

```yaml
# feature/basic.yml — Basic feature tests
desc: Basic single-feature tests on custom-built flight records
mode: feature

features:
  avgAlt:
    - file: test/testsFiles/feature/avgAlt_1.frd
      result: 100.00
      desc: "flat flight at constant altitude"
    - file: test/testsFiles/feature/avgAlt_2.frd
      result: 500.50
      desc: "linear climb"
    - file: test/testsFiles/feature/avgAlt_3.frd
      result: 0.00
      desc: "ground-level only"

  maxAlt:
    - file: test/testsFiles/feature/maxAlt_1.frd
      result: 14000
      desc: "spike to max then descent"
    - file: test/testsFiles/feature/maxAlt_2.frd
      result: 0
      desc: "ground-level only"

  avgAirSpeed:
    - file: test/testsFiles/feature/avgAirSpeed_1.frd
      result: 250.00
    - file: test/testsFiles/feature/avgAirSpeed_2.frd
      result: 0.00
      desc: "stationary"
```

#### 3.2.4 Feature-mode tests with options (v2 phase style)

Phase-scoped features use the v2 syntax: `--phase <name>` combined with `-o <base_feature>`. The `option` field carries the phase flag.

```yaml
# feature/phases.yml (excerpt)
  avgAirSpeed:                                # base feature name
    - file: test/testsFiles/feature/avgAirSpeed_1.frd
      result: 120.00
      option: "--phase takeOff"               # v2 style — restricts to takeOff
      desc: "avg air speed during takeOff"
    - file: test/testsFiles/feature/avgAirSpeed_2.frd
      result: 275.00
      option: "--phase cruise"
      desc: "avg air speed during cruise"
```

#### 3.2.5 Metadata tests

```yaml
# metadata/metadata_ru.yml — Metadata queries on RU flights
desc: Metadata extraction from RU flight records
mode: feature

metadata:
  flight_id:
    - file: test/testsFiles/mono/0_201_MiG-23MLD.frd
      result: "201"
    - file: test/testsFiles/mono/0_301_Su-25T.frd
      result: "301"

  flight_code:
    - file: test/testsFiles/mono/0_201_MiG-23MLD.frd
      result: MiG-23MLD

  origin:
    - file: test/testsFiles/mono/0_201_MiG-23MLD.frd
      result: RU

  mass_fuel:
    - file: test/testsFiles/mono/0_301_Su-25T.frd
      result: 3600
```

#### 3.2.6 Parameter tests

```yaml
# parameters/parameters.yml — Parameter-related tests
desc: Parameter listing and record count
mode: full

parameters:
  number:
    - file: test/testsFiles/mono/0_201_MiG-23MLD.frd
      option: "--number"
      result: 1463
```

#### 3.2.7 Multi-file tests (filenames, cross-flight)

When the input is multiple files, `file` is a list.

```yaml
# feature/basic.yml (continued)
  filenames:
    - file:
        - test/testsFiles/mono/0_201_MiG-23MLD.frd
        - test/testsFiles/mono/0_501_Tu-142.frd
      result: "0_201_MiG-23MLD.frd, 0_501_Tu-142.frd"
      desc: "alphabetical listing of two files"
```

Cross-flight features operate on a folder of flights:

```yaml
# cross/batch_ru.yml — Cross-flight computations on RU flights
desc: Batch tests on all RU mono flights
mode: feature

features:
  cumulDuration:
    - file: test/testsFiles/mono/
      result: "01:23:45"
      desc: "cumulative duration across all RU flights"

  airportTakeOff:
    - file: test/testsFiles/mono/
      result: "krasnodar pashkovsky"
      desc: "most used takeOff airport"

  highestSpeed:
    - file: test/testsFiles/mono/
      result: "201:641.15"
      desc: "MiG-23MLD has highest avg speed"
```

#### 3.2.8 Error-handling tests

For tests that expect an error message on **stderr** instead of a value on stdout, use `error` instead of `result`. The autograder should match the error pattern.

```yaml
# errors/missing_file.yml — Error handling: missing files
desc: Tests that verify proper error reporting
mode: feature

errors:
  - file: test/testsFiles/nonexistent.frd
    feature: avgAlt
    error: "ERROR: MISSING_FILE"
    desc: "missing input file"

  - file: test/testsFiles/edge/corrupted.frd
    feature: avgAlt
    error: "ERROR: CORRUPTED"
    desc: "binary garbage"

  - file: test/testsFiles/edge/no_header.frd
    feature: avgAlt
    error: "ERROR: MISSING_HEADER"
    desc: "file with no metadata section"

  - file: test/testsFiles/edge/incomplete_header.frd
    feature: avgAlt
    error: "ERROR: INCOMPLETE_HEADER"
    desc: "header missing required fields"
```

#### 3.2.9 Edge-case tests

Valid but unusual inputs that stress specific code paths.

```yaml
# edge/one_line.yml — Single-record flight files
desc: Edge cases with minimal valid flight data
mode: feature

features:
  avgAlt:
    - file: test/testsFiles/edge/one_line.frd
      result: 1000.00
      desc: "single data record — avg = that record"

  flightDuration:
    - file: test/testsFiles/edge/one_line.frd
      result: "00:00:00"
      desc: "single record — zero duration"

  flightDistance:
    - file: test/testsFiles/edge/one_line.frd
      result: 0.00
      desc: "single record — zero distance"
```

### 3.3 YAML field reference

| Field | Scope | Type | Required | Description |
|-------|-------|------|:--------:|-------------|
| `desc` | file / entry | string | no | Human-readable description (becomes a YAML comment in context; ignored in JSON) |
| `mode` | file / entry | `"feature"` or `"full"` | yes | Execution mode (see autograder §5) |
| `file` | file / entry | string or list | yes | Path(s) to test flight record(s) |
| `milestone` | file / entry | number | no (default: 0) | Optional grouping label. Informational — students can use it to track progress by project version. Not used for teacher profile filtering. |
| `option` | file / entry | string | no | Extra CLI flags (e.g. `"--imperial"`, `"--phase takeOff"`) |
| `group` | file / entry | string | no | Override aggregation/filtering category (e.g. `"imperial"`, `"metric"`) |
| `features` | file | map | conditional | Feature names → expected values (full-report) or feature names → list of test entries (feature-mode) |
| `metadata` | file | map | conditional | Metadata keys → expected values (full-report) or metadata keys → list of test entries |
| `parameters` | file | map | conditional | Parameter keys → list of test entries |
| `errors` | file | list | conditional | Error-handling test entries (use `error` instead of `result`) |
| `result` | entry | string, number | yes* | Expected stdout value |
| `error` | entry | string | yes* | Expected stderr pattern (for error tests) |

\* Exactly one of `result` or `error` must be present per test entry.

File-level values act as defaults; entry-level values override them.

---

## 4. Profile System — Selecting Which Tests to Include

### 4.1 Profile file

A **profile** is a small YAML file that declares which source files (or directories) to include, and optionally which features/milestones to filter.

```yaml
# profiles/fast.yml — Quick check for early semester
desc: Fast subset for first weeks — basic features only
include:
  - feature/basic.yml
  - metadata/metadata_ru.yml
  - parameters/parameters.yml
```

```yaml
# profiles/full_grading.yml — Final grading profile
desc: Complete test suite for final grading
include:
  - feature/                      # entire directory
  - full/
  - metadata/
  - parameters/
  - units/
  - cross/
  - errors/
  - edge/
```

```yaml
# profiles/units_only.yml — Just metric/imperial
desc: Unit conversion tests only
include:
  - units/
```

### 4.2 Profile field reference

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `desc` | string | no | Human description of the profile |
| `include` | list of paths | yes | YAML source files or directories (relative to `tests/`) |
| `exclude` | list of paths | no | Files/directories to skip (applied after include) |
| `features` | list of strings | no | Keep only tests targeting these features/groups |

---

## 5. CLI Interface

```
python tests_manager.py <command> [options]
```

### 5.1 Commands

| Command | Description |
|---------|-------------|
| `build` | Compile selected YAML sources into `testSuite.json` |
| `list` | List available YAML source files and profiles |
| `check` | Validate YAML source files (schema, file references, duplicate IDs) |

### 5.2 Options

| Flag | Argument | Description |
|------|----------|-------------|
| `-p` / `--profile` | `<path>` | Profile YAML to use for source selection |
| `-s` / `--sources` | `<path> ...` | Explicit list of YAML source files or directories (alternative to profile) |
| `-o` / `--output` | `<path>` | Output path for `testSuite.json` (default: `testSuite.json`) |
| `-d` / `--tests-dir` | `<path>` | Root directory for YAML source files (default: `tests/`) |
| `--dry-run` | — | Print what would be generated without writing |
| `--id-start` | `<number>` | Starting ID for auto-generated test IDs (default: `1000000`) |

### 5.3 Usage examples

```bash
# Build from a profile
python tests_manager.py build -p profiles/fast.yml -o shortTestSuite.json

# Build from explicit sources
python tests_manager.py build -s tests/feature/ tests/metadata/ -o testSuite.json

# List available sources and profiles
python tests_manager.py list

# Validate all YAML files
python tests_manager.py check

# Dry run — show what would be generated
python tests_manager.py build -p profiles/full_grading.yml --dry-run
```

---

## 6. JSON Generation Rules

### 6.1 ID allocation

IDs are auto-generated sequentially within each build. They are **local to a given `testSuite.json`** — the same logical test may have different IDs across different profiles. The purpose of the ID is to let the teacher quickly reference a failing test from the report and reproduce it on the command line.

```
<source_index> <test_index>
   3 digits      3 digits
```

Example: 3rd YAML file, 7th test → `003007`

IDs are deterministic: same inputs always produce same IDs (sorted by source file name, then declaration order within the file).

The autograder report should include a short identifier for the test suite (e.g. a hash of the JSON content or the profile name) so that a `(suite, id)` pair uniquely identifies a test across different builds.

### 6.2 Expansion rules

Each YAML entry expands into one JSON test object. The mapping:

| YAML source | JSON output |
|-------------|-------------|
| `features: { avgAlt: 100 }` (full-mode file) | `{ "mode": "full", "feature": "avgAlt", "result": 100, "file": "<file>", ... }` |
| `features: { avgAlt: [{ file: x, result: y }] }` (feature-mode) | `{ "mode": "feature", "feature": "avgAlt", "file": "x", "result": y, ... }` |
| `metadata: { flight_id: "201" }` (full-mode) | `{ "mode": "feature", "metadata": "flight_id", "result": "201", "file": "<file>", ... }` |
| `metadata: { flight_id: [{ file: x, result: y }] }` | `{ "mode": "feature", "metadata": "flight_id", "file": "x", "result": y, ... }` |
| `parameters: { number: [{ file: x, option: "--number", result: y }] }` | `{ "mode": "full", "parameter": "number", "option": "--number", "file": "x", "result": y, ... }` |
| `errors: [{ file: x, feature: f, error: "..." }]` | `{ "mode": "feature", "feature": "f", "file": "x", "error": "...", ... }` |

File-level `option`, `group`, `milestone` are inherited by entries unless overridden.

### 6.3 Full-mode grouping (optimization)

In `full` mode, tests sharing the same `file` + `option` are grouped by the autograder into a single JAR invocation. The YAML format naturally represents this: one file block → many feature checks.

### 6.4 Validation

Before writing JSON, the tool checks:

1. **Schema**: Every YAML file conforms to the expected structure
2. **File references**: Every `file` path points to an existing file on disk
3. **No duplicate features**: Within a single file block, no feature appears twice
4. **Consistent mode**: A file-level `mode: full` block should not contain feature-mode entry structures (and vice versa)
5. **Error vs. result**: Each entry has exactly one of `result` or `error`

Warnings (non-fatal):
- Feature names not in `features-whitelist.json`
- Metadata keys not in `metadata_allowed`

---

## 7. Relationship to Existing Tools

```
┌────────────────┐                          ┌─────────────┐
│flightGenerator │──────┬──────────────────▶│ .frd files  │
└────────────────┘      │                   └──────┬──────┘
                        │ also emits               │
                ┌───────▼──────┐      referenced by
                │ tests/*.yml  │               │
                │ (generated   │    ┌──────────┴──┐
                │  + authored) │───▶│tests_manager│────▶ testSuite.json
                └──────────────┘    └─────────────┘          │
                                                             │
                ┌──────────────┐    ┌─────────────┐          │
                │ manifest.json│───▶│  autograder  │◀────────┘
                └──────────────┘    └──────┬──────┘
                                           │
                                        report
```

- **flightGenerator** produces custom `.frd` files **and** emits YAML test definitions (file path, expected values, scenario description)
- **tests_manager** compiles YAML → JSON (both hand-authored and generator-emitted)
- **autograder** consumes `testSuite.json` + `manifest.json` → runs Pandora → produces report
- **class_grader** orchestrates autograder across all student groups

---

## 8. Test Scenarios To Cover

### 8.1 Standard features (by category)

| Category | Features | Test type |
|----------|----------|-----------|
| Basic | `avgAlt`, `maxAlt`, `avgAirSpeed`, `maxAirSpeed`, `avgEnginePower`, `maxEnginePower`, `filenames`, `start_time` | feature + full |
| Metadata | all 11 fields (`flight_id`, `flight_code`, `origin`, `date`, `from`, `to`, `motor(s)`, `mass_aircraft`, `mass_fuel`, `lift_coef`, `drag_coef`) | feature |
| Parameters | `-p` (parameters list), `-n` (record count) | feature |
| Environment | `avgTemp`, `minTemp`, `maxTemp`, `avgPressure`, `minPressure`, `maxPressure`, `avgHumidity`, `minHumidity`, `maxHumidity`, `avgHeartRate`, `minHeartRate`, `maxHeartRate`, `avgOxygen`, `minOxygen`, `maxOxygen` | feature + full |
| Advanced | `flightDistance`, `flightDuration`, `avgAcceleration`, `maxAcceleration`, `windSpeed`, `avgMachSpeed`, `maxMachSpeed`, `maxAccelG` | feature + full |
| Phases | `takeOff`, `cruise`, `landing`, `ratioDistance`, phase-scoped features (v2: `--phase <name>` + base feature), `reachAlt`, `reachDist`, `fastWindAlt`, `fastJetAlt`, `noiseTemp`, `stressedPilot`, `oxygenPhase`, `mostPowerPhase`, `mostStressPhase`, `mostAccelPhase` | feature + full |
| Cross-flight | `cumulDuration`, `cumulDistance`, `airportTakeOff`, `airportLanding`, `highestDrag`, `smallestDrag`, `highestLift`, `smallestLift`, `highestSpeed`, `slowestSpeed` | feature |

### 8.2 Metric / Imperial (group tests)

For each unit-sensitive feature, run full report on real flights with `--metric` and `--imperial`:

- Unit-sensitive features: all altitude, speed, distance, power, temperature, pressure features
- Expected values must be pre-computed in the target unit system using the conversion constants from Pandora docs

### 8.3 Edge cases

| Scenario | Description | Expected behavior |
|----------|-------------|-------------------|
| One-line flight | Single data record after header | Averages = that record, duration = 0, distance = 0 |
| Minimal columns | Only required columns (timestamp, lon, lat, alt, air_speed, engine_1) | Features using optional columns should handle gracefully |
| Reordered columns | Column names in non-standard order | Parser must use header names, not positions |
| US vs RU units | US files use feet/lbs, RU use meters/kg | Conversions applied correctly based on `origin` |
| Multi-engine | Flights with 1, 2, 4 engines | `avgEnginePower` sums all engines |

### 8.4 Error handling

Based on Pandora's error specification:

| Error | Test setup | Expected stderr |
|-------|-----------|-----------------|
| `MISSING_FILE` | Non-existent file path | `ERROR: MISSING_FILE - <filename>` |
| `CORRUPTED` | Binary garbage file | `ERROR: CORRUPTED - <filename>` |
| `MISSING_HEADER` | File with no metadata section | `ERROR: MISSING_HEADER - <filename>` |
| `INCOMPLETE_HEADER` | Header missing required fields | `ERROR: INCOMPLETE_HEADER - <filename>=[<fields>]` |
| `MISSING_COLUMN` | Data section missing required columns | `ERROR: MISSING_COLUMN - <filename>=[<columns>]` |
| `MISSING_COLNAMES` | No column header row | `ERROR: MISSING_COLNAMES - <filename>` |
| `ORDERING` | Unsorted timestamps | `ERROR: ORDERING - <filename>` |
| `INVALID_OPTION` | Bad `-o` or `-m` value | `ERROR: Invalid Option ...` |

### 8.5 Current test file inventory

| Directory | Contents | Count |
|-----------|----------|:-----:|
| `test/testsFiles/mono/` | RU single-flight records (MiG-23, Su-25, Su-27, Tu-142, MiG-29) | 5 |
| `test/testsFiles/US/` | US single-flight records (F-14A, F-14B, F-15C, F-16A, F-15E) | 5 |
| `test/testsFiles/feature/` | Custom `.frd` for single-feature tests (generated by flightGenerator) | ~200 |
| `test/testsFiles/multi/` | Multi-file / batch test data | (planned) |
| `test/testsFiles/edge/` | Edge-case and error `.frd` files | (planned) |

---

## 9. Design Decisions (Q&A)

### 9.1 Error test support in autograder

**Q**: The current autograder only compares stdout. Error tests need stderr comparison.

**Resolution**: Design the YAML format with an `error` field now. The autograder will be updated to check `error` (stderr pattern) when present, otherwise check `result` (stdout). This is a **future autograder update** — we design forward.

> **TODO (autograder)**: Add `error` field support — when a test has `error` instead of `result`, compare the expected pattern against stderr instead of stdout. Track in [docs/Todo.md](Todo.md).

### 9.2 IDs and milestones

**Q**: IDs shift when YAML files are added/removed. Milestones are a relic from previous class versions.

**Resolution — IDs**: IDs are auto-generated and **local to a given `testSuite.json`**. Different profiles may assign different IDs to the same logical test — that's fine. The autograder report should embed a short identifier for the test suite (hash or profile name) so that `(suite_id, test_id)` is globally unique for debugging.

**Resolution — Milestones**: Phase out milestones as a grading/filtering mechanism in the teacher's workflow. The field remains available for **students** to structure their own test suites by project version (e.g. aligning with their semver milestones), but the teacher's profiles use directory/file inclusion rather than milestone filtering. The `milestone` field becomes optional and informational.

### 9.3 flightGenerator integration

**Q**: Should `tests_manager.py` invoke the flight generator to create missing `.frd` files?

**Resolution**: Not directly — the YAML test definitions would become bloated with generation parameters (number of records, columns, metadata, scenario constraints). Instead, the workflow is **generate first, test second**:

1. The flightGenerator produces `.frd` files and emits a YAML manifest describing what it generated (file path, feature, expected value, scenario description)
2. `tests_manager.py` consumes those YAML manifests as test sources

This keeps concerns separated. The flightGenerator brief should be updated to define this output format.

> **TODO (flightGenerator)**: Define YAML output format from the generation phase — include file path, target feature, expected result, scenario description. Track in [docs/flightGenerator.md](flightGenerator.md).

### 9.4 Cross-flight tests

**Q**: The `multi/` directory is empty. No batch/folder tests exist.

**Resolution**: Yes — cross-flight tests should be added. They cover features like `cumulDuration`, `cumulDistance`, `airportTakeOff`, `airportLanding`, `highestDrag`, `smallestDrag`, `highestSpeed`, `slowestSpeed`, etc. The flight generator should be able to produce sets of related flights for these tests, in addition to using the existing real flights in `mono/` and `US/`. A `cross/` directory is added under `tests/` for the YAML definitions.

### 9.5 Phase-scoped tests

**Q**: Pandora v2 uses `--phase takeOff` with `-o avgAirSpeed` instead of the v1 `-o avgAirSpeedTakeOff`. Which style?

**Resolution**: **v2 only**. All phase-scoped tests use `--phase <phase_name>` in the `option` field combined with the base feature name in `feature`. The deprecated v1 compound names (`avgAirSpeedTakeOff`, etc.) are not used in new YAML test sources.

