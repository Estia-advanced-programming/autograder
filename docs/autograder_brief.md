# Autograder — Requirements Brief

## 1. Purpose

The autograder is a CLI tool for an Advanced Programming course. It grades a student Java project called **Pandora** — a flight-recorder data analysis tool packaged as an executable JAR.

It serves two audiences:

- **Students** use it to self-evaluate in a test-driven development workflow: they write their own test suite and manifest, then run the autograder against their own Pandora to track progress.
- **The teacher** uses it to run a reference test suite against every group's Pandora, and to validate the quality of each group's test suite.

---

## 2. Domain: What Pandora Does

Pandora reads flight-recorder data files and produces analysis outputs. Its CLI has several modes:

### 2.1 Full Report (no `-o` flag)

```
java -jar pandora.jar <file>
```

Outputs a multi-line report with one `key: value` pair per line, covering all computed features for the given file.

### 2.2 Single Feature (`-o <feature>`)

```
java -jar pandora.jar -o <feature> <file>
```

Outputs a single value to stdout corresponding to the requested feature (e.g. max altitude, average speed, etc.).

### 2.3 Metadata (`-m <metadata_key>`)

```
java -jar pandora.jar -m <metadata_key> <file>
```

Retrieves a specific metadata value from the flight record (e.g. number of motors, flight ID, date). This is **not** behind `-o`; it is its own flag.

### 2.4 Parameters (row count, recorded parameters)

Pandora can output the number of rows/records and the list of recorded flight parameters. These are **not** behind `-o` either; they have their own flags/options (e.g. `-p`).

### 2.5 Output Modifiers

Some flags modify the output rather than selecting what to output. Currently:

- **Unit system**: `-u Metric` or `-u Imperial` changes numeric output units.

### 2.6 Version

```
java -jar pandora.jar --version
```

Prints the Pandora version string.

---

## 3. Data Contracts

### 3.1 Test Suite (`testSuite.json`)

A JSON array of test objects. Each test targets one of several categories:

| Field        | Type                   | Required | Description |
|--------------|------------------------|----------|-------------|
| `id`         | string or number       | yes      | Unique test identifier |
| `mode`       | `"feature"` or `"full"` | no (default: "full")     | Execution mode (see §5) |
| `feature`    | string                 | conditional | The feature name. Required for feature-mode and full-mode tests targeting a standard `-o` feature. |
| `metadata`   | string                 | conditional | The metadata key to query (e.g. `"flight_id"`). When set, test targets the `-m` flag. |
| `parameter`  | string                 | conditional | A parameter-related key (e.g. `"number"`, `"parameters"`). When set, test targets parameter flags. |
| `group`      | string                 | no       | Override aggregation and filtering category. When set, the test’s score is aggregated under this value (e.g. `"imperial"`) instead of its feature/metadata/parameter, and the manifest must list this value for the test to run. |
| `option`     | string                 | no       | Additional CLI flag(s) passed to Pandora (e.g. `"-p"`, `"--imperial"`). Space-separated if multiple. |
| `file`       | string                 | yes      | Path to the test input file (relative to the working directory) |
| `result`     | string, int, or float  | yes      | Expected output value |
| `milestone`  | string or number       | no (default: 0)      | Grouping label for milestone-based reporting |

Exactly one of `feature`, `metadata`, or `parameter` should be set per test to determine the test category. The optional `group` field overrides how the test is categorized for filtering and score aggregation.

### 3.2 Manifest (`manifest.json`)

Declares what the student claims to have implemented:

```json
{
  "version": "1.2.0",
  "features": ["altitude_max", "speed_avg", "parameter", "imperial", "metadata", ...]
}
```

The `features` array can contain:
- Standard feature names (matched against the `feature` field in tests)
- `"metadata"` — enables all tests that have a `metadata` field
- `"parameter"` — enables all tests that have a `parameter` field
- `"imperial"` — enables tests that involve unit conversion
- Any other declared capability

Only tests whose relevant category appears in the manifest are executed.

---

## 4. CLI Interface

```
python autograder.py [options] <path_to_pandora_jar>
```

The path to the student's JAR is a **positional argument** (exactly one required).

### 4.1 Path Options

| Flag | Argument | Description |
|------|----------|-------------|
| `-w` | `<path>` | Working directory / project folder. When provided, all relative paths (Pandora JAR, test files, manifest) are resolved relative to this directory. |
| `-j` | `<path>` | Path to the JaCoCo agent JAR (default: `target/jacocoagent.jar`) |
| `-t` | `<path>` | Path to the test suite JSON file, default to "./test/testSuite.json" |
| `-m` | `<path>` | Path to the manifest JSON file, default to "./manifest.json" |

### 4.2 Output Options

by default the autograder outputs :`Total Score: <score>` to stdout (unless `--check` is used). It can also produce more detailed output with the following options:

| Flag | Argument | Description |
|------|----------|-------------|
| `--summary` | — | Output a compact summary: one line per feature with its badge (🟢🟡🔴). Designed for students tracking progress.|
| `--report` | — | Output the full Markdown report with per-test detail tables.  |
| `-f` | `json|md` | Output results as a JSON object or a Markdown report (see §7.2) |
| `-o` | `<path>` | Write output to this file instead of stdout. The filename should be customizable to reflect the team name (e.g. `-o results_team3.md`). Can omit the extension |

### 4.3 Execution Options

| Flag | Argument | Description |
|------|----------|-------------|
| `-c` / `--coverage` | — | Enable JaCoCo code coverage collection |
| `-d` / `--debug` | — | Enable debug mode (prints executed commands to stdout) |
| `-T` / `--timeout` | `<seconds>` | Set the timeout for each test command (default: 10 seconds) |
| `--check` | — | Validate inputs without running tests. Checks that: (1) the test suite JSON is valid and well-formed, (2) the manifest JSON is valid and well-formed, (3) every `file` referenced in the test suite exists on disk, (4) the Pandora JAR exists. Reports all problems found and exits. |

### 4.5 Exit Behavior

- Exits with code 1 and prints usage on invalid arguments.
- `--check` exits with code 0 if all checks pass, 1 if any fail.

---

## 5. Test Execution Modes

### 5.1 Feature Mode (`"mode": "feature"`)

Each test is run as an individual JAR invocation. Command construction depends on the test category:

- **Standard feature**: `-o <feature> [options] <file>`
- **Metadata**: `-m <metadata_key> [options] <file>`
- **Parameter**: `[parameter_flags] [options] <file>` — uses the `option` field which contains the appropriate flag (e.g. `"-p"`)

The entire stdout is compared against the expected result.

### 5.2 Full Mode (`"mode": "full"`)

Tests sharing the same `file` and `option` combination are grouped into a single JAR invocation (no `-o` flag). The stdout is expected to contain `key: value` lines. Each test's `feature` is used to look up the corresponding key in the output.

---

## 6. JAR Invocation

Every JAR execution follows this pattern:

```
java [-javaagent:<jacoco_agent>=destfile=target/jacoco.exec[,append=true]] \
     -Duser.country=US -Duser.language=en \
     -jar <path_to_jar> [options] [file]
```

- JVM locale is always forced to `en_US`.
- JaCoCo agent is only present when coverage is enabled.
- **Timeout**: default 10 seconds per command. Timed-out tests score 0 with result `"TIMEOUT"`.

### Startup Sequence

1. Run `--version` to capture the Pandora version string.
2. If coverage is enabled, run `--help` with JaCoCo to initialize the coverage file.

---

## 7. Scoring

### 7.1 Output Comparison

- **Numeric expected values** (int/float): Parse actual output as float. Score = `floor(F^(2·(1−|actual−expected|))) / F` where `F = 50`. Gives 1.0 for exact match; drops off sharply.
- **String expected values**: Score = `1 − normalized_levenshtein(actual, expected)`. Levenshtein distance is normalized by dividing by the length of the longer string.
- Parse failure or unsupported type → score = 0.

### 7.2 Output Normalization

Before comparison, stdout is:
1. Decoded with error replacement
2. Line endings normalized (CRLF/CR → LF)
3. Tabs → 4 spaces
4. Reformatted to OS-native line endings
5. Leading/trailing whitespace stripped

### 7.3 Aggregation

- **Per-test**: Individual score 0.0–1.0.
- **Per-feature**: Average score across all tests sharing the same `feature` value. Additionally, all `metadata` tests are aggregated together under the `"metadata"` key,  `parameter` tests under their key (`number`, `unit`, `metric`...).
- **Per-group**: When a test has a `group` field, its score is aggregated under the group name instead of its feature/metadata/parameter key. This allows grouping tests for different features under a single umbrella (e.g. `"imperial"` groups all imperial-unit tests regardless of which feature they target).
- **Per-milestone**: Average score across all tests in that milestone.
- **Total score**: Average score across all filtered tests.

### 7.4 Pass Badges

- 🟢 score ≥ 0.9
- 🟡 score ≥ 0.8
- 🔴 score < 0.8

---

## 8. Version Tracking

The report must include the **Pandora version**:

version might be of the form v1.2.3 or 1.2.3, but the `v` prefix should be stripped if present. The version is obtained from two sources:

- Obtained from `pandora --version` at startup.
- Also read from the manifest's `version` field.
- The **higher** of the two versions is reported.
- If the two versions differ, include a **warning** in the report indicating the discrepancy (e.g. manifest says 1.3.0 but JAR reports 1.2.0).

---

## 9. Output Formats

### 9.1 Summary (`--summary`)

Compact output for student progress tracking:

```
altitude_max  🟢
speed_avg     🟡
metadata      🔴
parameter     🟢
imperial      🟢
```

One line per feature declared in the manifest, with its aggregated badge.

### 9.2 Markdown Report (`--report`, default)

Full report containing:

1. **Version** line (with warning if discrepancy).
2. **Total Score**.
3. **Feature Scores table**: One row per feature/category with pass badge and score feature are grouped by milestone with a header row for each milestone.
4. **Test detail tables**: One table per milestone listing every test with id, mode, feature, file, expected result, actual result, pass badge, and score.


### 9.3 JSON (`-f json`)

```json
{
  "version": "<highest_version>",
  "versions" : {
    "pandora": "<version_from_jar>",
    "manifest": "<version_from_manifest>"
  },
  "version_warning": "<optional, present only on mismatch>",
  "milestone_scores": { "<milestone>": <score>, ... },
  "total_score": <float>,
  "features": ["<feature>", ...],
  "features_score": {
    "<feature or parameter key>": <score>,
    "metadata": <score>,
    ...
  },
  "tests_by_milestone": { "<milestone>": [<test_objects>], ... },
  "time": <elapsed_seconds>
}
```

---

## 10. Technical Constraints

- **Python 3.6+**, standard library only (no external packages). Must be trivial for students to deploy.
- **Java runtime** on PATH.
- **JaCoCo agent JAR** required only when coverage is enabled.
- Single-file or minimal-file distribution preferred.
