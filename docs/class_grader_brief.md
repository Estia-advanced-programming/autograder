# Class Grader — Requirements Brief

## 1. Purpose

The class grader is a **batch orchestration and analysis tool** for the teacher. It runs the autograder across all student groups, collects results, and produces **JSON output** that evaluates both **student implementations** and **student test suites**.

It calls the autograder as a subprocess (or imports it as a library), processes its JSON output, and writes structured per-phase JSON directories plus combined per-group JSON files. Report generation (Quarto `.qmd`) is handled separately by `report_generator.py`.

---

## 2. Inputs

### 2.1 Directory Layout

The teacher provides a root directory containing one subfolder per student group:

```
class/
├── group1/
│   ├── pandora.jar
│   ├── manifest.json
    ├── test
        ├── testSuite.json
        └── testFiles/

├── group2/
│   ├── pandora.jar
│   ├── manifest.json
|   ├── test
|       ├── testSuite.json
|       └── testFiles/
└── ...
```

The teacher also provides:
- **Reference test suite** (`-t <path>`): the teacher's own test suite.
- **Reference Pandora JAR** (`-r <path>`): the teacher's reference implementation.

### 2.2 CLI Interface

```
python class_grader.py [-C config.yml] [-d <class_dir> -t <teacher_tests> -r <ref_jar>] [options]
```

| Flag | Argument | Required | Description |
|------|----------|----------|-------------|
| `-C` / `--config` | `<path>` | no | Path to a YAML configuration file (CLI options override config values) |
| `-d` | `<path>` | yes* | Root directory containing group subfolders |
| `-t` | `<path>` | yes* | Path to the teacher's reference test suite |
| `-r` | `<path>` | yes* | Path to the teacher's reference Pandora JAR |
| `-W` / `--teacher-workdir` | `<path>` | no | Teacher project root (where teacher test file paths resolve from). Defaults to parent directory of the teacher test suite. |
| `-o` | `<path>` | no | Output directory for reports (default: current directory) |
| `-c` / `--coverage` | — | no | Enable JaCoCo coverage analysis |
| `-j` | `<path>` | no | Path to JaCoCo agent JAR |
| `--json` | — | no | Also produce per-group JSON files |
| `-T` / `--timeout` | `<int>` | no | Per-command timeout in seconds (default: 10) |
| `--debug` | — | no | Enable debug output |
| `--fast` | — | no | Fast mode: only run teacher→students and students→teacher, skip cross-testing |
| `--dryrun` | — | no | Print the autograder commands that would be run without executing them |

\* Required options (`-d`, `-t`, `-r`) can be provided via CLI arguments, the YAML config file, or a combination of both. CLI arguments always override config file values.

Group subfolder names are used as team names throughout all reports.

### 2.3 Optional YAML Configuration

Instead of (or in addition to) command-line arguments, options can be provided via a YAML file passed with `-C` / `--config`. All keys are optional — any value set on the CLI takes precedence over the config file.

```yml
dir: ../2026/pandora-2026-submissions
tests: test/testSuite.json
ref: path/to/reference.jar
teacher_workdir: path/to/teacher/project
output: ./reports
coverage: true
jacoco: path/to/jacoco.jar
json: true
timeout: 15
debug: false
fast: true
dryrun: false
```

**Example usage:**

```bash
# All options from config
python class_grader.py -C config.yml

# Config with CLI override (e.g. disable fast mode for a full run)
python class_grader.py -C config.yml --timeout 20

# Partial config, remaining required options from CLI
python class_grader.py -C config.yml -r path/to/ref.jar
```

Requires the `pyyaml` package (`pip install pyyaml`). Only needed when `--config` is used.
---

## 3. Evaluation Runs

The class grader performs four categories of evaluation. Each produces structured results that feed into the final reports.

### 3.1 Teacher Tests → Student Pandoras

**Goal**: Grade each group's implementation against the reference test suite.

For each group:
```
autograder -t <teacher_test_suite> -m <group>/manifest.json -f json -w <group>/ <group>/pandora.jar
```

Produces: per-feature scores showing how well each group implements each feature.

### 3.2 Student Tests → Teacher Pandora

**Goal**: Validate the quality of each group's test suite by running it against the known-correct reference implementation.

For each group:
```
autograder -t <group>/testSuite.json -m <group>/manifest.json -f json -w <group>/ <teacher_pandora>
```

Any test that the reference Pandora **fails** is a bad test (wrong expected value or malformed). The class grader should:
- Record which tests pass and which fail against the reference.
- Produce a **filtered copy** of the group's test suite containing **only correct tests** (those that pass against the reference). Save as `<group>/testSuite_validated.json`.

### 3.3 Student Tests → All Other Pandoras (Cross-Testing)

**Goal**: Measure how well each group's tests detect issues in other groups' implementations.

For each group G's validated test suite, run it against every other group's Pandora:
```
autograder -t <G>/testSuite_validated.json -m <other>/manifest.json -f json -w <other>/ <other>/pandora.jar
```

This produces a matrix of (tester_group × tested_group × feature) results.

### 3.4 Coverage Analysis (Optional)

**Goal**: Measure dead code in student implementations.

When `--coverage` is enabled, for each group:
1. Run the teacher's test suite with coverage enabled against the group's Pandora.
2. Run the group's own test suite with coverage enabled against the group's Pandora.
3. Report coverage metrics from JaCoCo.

---

## 4. Output

`class_grader.py` produces **JSON only** — no Markdown or Quarto files. Reports are generated by `report_generator.py` (see `docs/output_schema.md` for the full JSON schema).

### 4.1 Directory Structure

```
<output_dir>/
├── teacher_eval/      # Teacher evaluation phase
│   ├── _meta.json
│   ├── _summary.json
│   └── <group>.json
├── validation/        # Test validation phase
├── self_eval/         # Self-evaluation phase
├── cross_testing/     # Cross-testing phase
├── coverage/          # JaCoCo coverage (when enabled)
├── commits/           # Git commit analysis (when enabled)
└── groups/            # Combined per-group JSON (all phases merged)
    └── <group>.json
```

Each phase directory contains:
- One JSON file per group (phase-specific data)
- `_meta.json` — phase metadata (name, date, groups count)
- `_summary.json` — class-level summary with rankings and averages

### 4.2 Combined Per-Group JSON

The `groups/` directory contains one file per group merging all phase data:

```json
{
  "team": "<group_name>",
  "short_name": "<display_name>",
  "version": "<pandora_version>",
  "feature_tally": { "validated": 0, "almost": 22, "missed": 8, "not_implemented": 57, "total": 87 },
  "test_tally": { ... },
  "features_detail": { "<feature>": { "score": 0.55, "valid": 16, "total": 29, "status": "almost" }, ... },
  "manifest_features": ["metadata", "filenames", ...],
  "teacher_evaluation": {
    "features_score": { ... },
    "total_score": 0.85,
    "milestone_scores": { "0": 0.81, "1": 1.0, ... },
    "teacher_score": 42.5,
    "teacher_score_breakdown": { "test_points": 0, "feature_points": 0, "penalty_points": 0 },
    "test_suite": "fast.json",
    "test_suite_metadata": null
  },
  "self_evaluation": { "features_score": { ... }, "total_score": 0.0 },
  "test_quality": {
    "total_tests": 88, "valid_tests": 56, "invalid_tests": 30, "removed_tests": 2,
    "tp": 85, "fp": 333, "tn": 355, "fn": 10,
    "precision": 0.20, "recall": 0.89, "f1": 0.33, "accuracy": 0.56
  },
  "coverage": null,
  "commits": { "student_commits": 52, "group_metrics": { ... }, "authors": { ... }, ... }
}
```

See `docs/output_schema.md` for the complete field reference.

### 4.3 Report Generation

Reports are produced by `report_generator.py`, which reads the JSON output above and generates Quarto `.qmd` files:

---

## 5. About Precision, Recall, and F1 in This Context

The teacher's evaluation serves as **ground truth**. For each (group, feature) pair, the teacher's test suite determines whether a feature is "truly implemented" (score ≥ threshold, e.g. 0.9).

When group G runs their validated tests against group X:
- **True Positive**: G's tests say feature F passes, and teacher agrees F is implemented → G correctly detects a working feature.
- **False Positive**: G's tests say feature F passes, but teacher says F is NOT implemented → G's tests fail to catch a broken feature (test is too lenient or incomplete).
- **True Negative**: G's tests say feature F fails, and teacher agrees F is NOT implemented → G correctly identifies a missing/broken feature.
- **False Negative**: G's tests say feature F fails, but teacher says F IS implemented → G's tests are too strict or test the wrong thing.

**Precision** = TP / (TP + FP) — "When this group's tests say pass, how often is the feature truly working?"

**Recall** = TP / (TP + FN) — "Of all truly working features, how many does this group's tests correctly identify?"

A high-quality test suite has both high precision (doesn't pass broken code) and high recall (doesn't fail correct code).

---

## 6. Technical Constraints

- **Python 3.6+**, standard library only (plus `pyyaml` for config).
- Uses the autograder as the execution engine (either as a subprocess or by importing its functions).
- Outputs: **JSON files only**. Report rendering is handled by `report_generator.py`.
- Should handle groups gracefully when their JAR is missing or crashes — report errors without aborting the entire run.
- Group folder names are used as team identifiers throughout.

## 7. Architecture

```
class_grader.py           → JSON (per-phase dirs + groups/)
report_generator.py       → .qmd reports (reads JSON)
autograder.py             → per-group test execution engine
```

`class_grader.py` is compute-only. All rendering (Quarto `.qmd` generation) lives in `report_generator.py`.
