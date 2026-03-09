# Class Grader — Requirements Brief

## 1. Purpose

The class grader is a **batch orchestration and analysis tool** for the teacher. It runs the autograder across all student groups, collects results, and produces cross-group reports that evaluate both **student implementations** and **student test suites**.

It calls the autograder as a subprocess (or imports it as a library) and processes its JSON output.

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

## 4. Reports

### 4.1 Feature × Group Matrix (Teacher's Test Suite)

A matrix where rows are features and columns are groups:

```
                  group1  group2  group3  group4
altitude_max        🟢      🟡      🔴      🟢
speed_avg           🟢      🟢      ⚪️      🟡
metadata            🔴      🟢      🔴      🔴
parameter           🟢      🟢      🟢      🟢
imperial            🟡      🔴      🟢      🟢
```

A 🟢 here means the feature is correctly implemented (score ≥ 0.9)
A 🟡 means the feature is partially implemented (score between 0.5 and 0.9)
A 🔴 here means the feature is not correctly implemented 
A ⚪️ means the feature is not declared in the manifest (not attempted).

This is the **reference evaluation** — it shows at a glance which features each group has successfully implemented.

Output as: Markdown table and/or CSV.

### 4.2 Feature × Group Matrix (Student Tests → Teacher Pandora)

Same format, but shows which of each group's tests are correct (pass against reference):

```
                  group1  group2  group3  group4
altitude_max        🟢      🟢      🔴      🟢
speed_avg           🟢      🔴      ⚪️      ⚪️
...
```

A 🔴 here means the group's tests for that feature contain errors (bad expected values).
A ⚪️ means the group has no tests for that feature.

### 4.3 Cross-Testing Agreement Matrix

Compares each group's test verdicts against the teacher's test verdicts. The teacher's evaluation (§4.1) is the **ground truth**:

- **Ground truth**: Teacher's test suite says group X has implemented feature F (score ≥ 0.9 → implemented, < 0.9 → not implemented).
- **Group detection**: Group G's validated test suite run against group X says feature F passes or fails.

For each testing group G, compute binary classification metrics against the teacher's ground truth:

| Metric | Definition |
|--------|------------|
| **Precision** | Of the features group G's tests say are implemented, what fraction truly are? High precision = few false positives (group doesn't say "pass" for broken features). |
| **Recall** | Of the features that truly are implemented, what fraction does group G's tests detect? High recall = few false misses (group catches working features). |
| **F1 Score** | Harmonic mean of precision and recall. |
| **Agreement** | Overall percentage of (group × feature) cells where group G's verdict matches the teacher's verdict. |

Output: A table with one row per testing group:

```
            Precision  Recall  F1    Agreement
group1      0.95       0.88    0.91  0.90
group2      0.80       0.92    0.86  0.85
group3      0.70       0.95    0.81  0.78
group4      0.90       0.90    0.90  0.89
```

Also produce a detailed **agreement heatmap matrix** (tester × tested group) showing per-pair agreement to help the teacher identify systematic problems:

```
tested →     group1  group2  group3  group4
tester ↓
group1         —      0.90    0.85    0.92
group2        0.88     —      0.80    0.87
group3        0.75    0.78     —      0.80
group4        0.90    0.88    0.85     —
```

### 4.4 Per-Group JSON

For each group, produce a JSON file:

```json
{
  "team": "<group_name>",
  "version": "<pandora_version>",
  "teacher_evaluation": {
    "features_score": {
      "<feature>": <score_or_0_if_not_implemented>,
      ...
    },
    "total_score": <float>,
    "milestone_scores": { ... }
  },
  "self_evaluation": {
    "features_score": { ... },
    "total_score": <float>
  },
  "test_quality": {
    "total_tests": <int>,
    "valid_tests": <int>,
    "invalid_tests": <int>,
    "precision": <float>,
    "recall": <float>,
    "f1": <float>,
    "agreement": <float>
  },
  "coverage": {
    "teacher_suite": <percentage_or_null>,
    "student_suite": <percentage_or_null>
  }
}
```

Field details:

| Field | Description |
|-------|-------------|
| `version` | Pandora version (from the autograder's version detection) |
| `teacher_evaluation.features_score` | Score from the teacher's test suite. 0 for features not declared in the manifest. |
| `self_evaluation` | Score from the group's own test suite run against their own Pandora. |
| `test_quality.total_tests` | Number of tests in the group's test suite. |
| `test_quality.valid_tests` | Number of tests that pass against the reference implementation. |
| `test_quality.invalid_tests` | Tests with wrong expected values (fail against reference). |
| `test_quality.precision` | Precision of the group's tests as a feature-implementation detector across all groups (see §4.3). |
| `test_quality.recall` | Recall of the group's tests as a feature-implementation detector across all groups (see §4.3). |
| `test_quality.f1` | F1 score combining precision and recall. |
| `test_quality.agreement` | Overall agreement rate with teacher's ground truth. |
| `coverage` | JaCoCo coverage percentages if enabled, `null` otherwise. |

### 4.5 Class Summary

A single Markdown file summarizing the entire class:

1. Feature × Group matrix (teacher evaluation)
2. Test quality ranking (sorted by F1 score)
3. Per-group summary table:

```
| Team   | Version | Teacher Score | Self Score | Test Quality (F1) | Valid Tests |
|--------|---------|---------------|------------|-------------------|-------------|
| group1 | 1.3.0   | 0.85          | 0.90       | 0.91              | 45/48       |
| group2 | 1.2.0   | 0.72          | 0.88       | 0.86              | 40/44       |
```

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

- **Python 3.6+**, standard library only.
- Uses the autograder as the execution engine (either as a subprocess or by importing its functions).
- Outputs: Markdown files, JSON files, optionally CSV.
- Should handle groups gracefully when their JAR is missing or crashes — report errors without aborting the entire run.
- Group folder names are used as team identifiers throughout.
