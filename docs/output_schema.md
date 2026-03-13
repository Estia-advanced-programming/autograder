# JSON Output Schema

This document describes the JSON output produced by `class_grader.py`.

## Directory structure

```
<output_dir>/
├── teacher_eval/          # Teacher evaluation phase
│   ├── _meta.json
│   ├── _summary.json
│   └── <group>.json       (one per group)
├── validation/            # Test validation phase
│   ├── _meta.json
│   ├── _summary.json
│   └── <group>.json
├── self_eval/             # Self-evaluation phase
│   ├── _meta.json
│   ├── _summary.json
│   └── <group>.json
├── cross_testing/         # Cross-testing phase
│   ├── _meta.json
│   ├── _summary.json
│   └── <group>.json
├── coverage/              # JaCoCo coverage phase
│   ├── _meta.json
│   ├── _summary.json
│   └── <group>.json
├── commits/               # Git commit analysis phase
│   ├── _meta.json
│   ├── _summary.json
│   └── <group>.json
└── groups/                # Combined per-group JSON
    └── <group>.json       (all phases merged)
```

Each phase directory is only created when the corresponding phase is enabled in `config.yml`.

---

## Common structures

### `_meta.json`

Present in every phase directory.

| Field               | Type   | Description                            |
|---------------------|--------|----------------------------------------|
| `phase`             | string | Phase name (e.g. `"teacher_eval"`)     |
| `date`              | string | ISO-8601 timestamp of the run          |
| `groups_evaluated`  | int    | Number of groups processed             |

The `teacher_eval` meta also includes:

| Field                | Type        | Description                         |
|----------------------|-------------|-------------------------------------|
| `test_suite`         | string      | Test suite filename                 |
| `test_suite_metadata`| object/null | Test suite metadata from JSON       |
| `test_count`         | int         | Number of tests                     |
| `feature_count`      | int         | Number of features                  |
| `ref_jar`            | string      | Reference JAR basename              |

### Feature status

Status values used throughout: `"validated"`, `"almost"`, `"missed"`, `"not_implemented"`.

### `feature_tally`

| Field              | Type | Description                   |
|--------------------|------|-------------------------------|
| `validated`        | int  | Features fully passing        |
| `almost`           | int  | Features partially passing    |
| `missed`           | int  | Features attempted but failing|
| `not_implemented`  | int  | Features not declared         |
| `total`            | int  | Sum of all categories         |

### `features_detail`

Keyed by feature name. Each entry:

| Field    | Type   | Description                                    |
|----------|--------|------------------------------------------------|
| `score`  | float  | Ratio of valid tests (0.0–1.0)                 |
| `valid`  | int    | Number of passing tests for this feature        |
| `total`  | int    | Total tests for this feature                    |
| `status` | string | One of `validated`/`almost`/`missed`            |

---

## Phase: `teacher_eval`

### Per-group JSON

| Field                    | Type        | Description                               |
|--------------------------|-------------|-------------------------------------------|
| `team`                   | string      | Full group identifier                     |
| `short_name`             | string      | Shortened display name                    |
| `version`                | string      | Group JAR version                         |
| `test_suite`             | string      | Test suite filename                       |
| `test_suite_metadata`    | object/null | Test suite metadata                       |
| `total_score`            | float       | Raw total score (0.0–1.0)                 |
| `teacher_score`          | float       | Weighted teacher score                    |
| `teacher_score_breakdown`| object      | Score breakdown (see below)               |
| `milestone_scores`       | object      | Per-milestone scores keyed `"0"`..`"N"`   |
| `feature_tally`          | object      | See [feature_tally](#feature_tally)       |
| `test_tally`             | object      | Same structure as feature_tally, for tests|
| `features_score`         | object      | Feature name → float score                |
| `features_detail`        | object      | See [features_detail](#features_detail)   |
| `manifest_features`      | list[str]   | Features declared in group manifest       |
| `error`                  | string/null | Error message, if any                     |

#### `teacher_score_breakdown`

| Field            | Type  | Description                         |
|------------------|-------|-------------------------------------|
| `test_points`    | float | Points from test-level scoring      |
| `feature_points` | float | Points from validated features      |
| `penalty_points` | float | Penalty for invalid/removed tests   |

#### `milestone_scores`

Object keyed by milestone index (string). Each value is a float (0.0–1.0) representing the score for that milestone.

```json
{ "0": 0.811, "1": 1.0, "2": 1.0, "3": 0.487, "4": 0.0, "5": 0.0 }
```

### `_summary.json`

| Field              | Type   | Description                                  |
|--------------------|--------|----------------------------------------------|
| `phase`            | string | `"teacher_eval"`                             |
| `date`             | string | ISO-8601 timestamp                           |
| `groups_count`     | int    | Number of groups                             |
| `feature_rankings` | object | Feature name → status distribution (see below)|
| `group_rankings`   | list   | Groups sorted by `teacher_score` descending  |
| `class_averages`   | object | Class-wide averages                          |

#### `feature_rankings[feature]`

| Field              | Type  | Description                          |
|--------------------|-------|--------------------------------------|
| `validated`        | int   | Groups that validated this feature   |
| `almost`           | int   | Groups with "almost" status          |
| `missed`           | int   | Groups that missed this feature      |
| `not_implemented`  | int   | Groups that did not implement it     |
| `success_rate`     | float | `validated / total`                  |

#### `group_rankings[i]`

| Field                | Type   | Description             |
|----------------------|--------|-------------------------|
| `team`               | string | Full group identifier   |
| `short_name`         | string | Display name            |
| `teacher_score`      | float  | Weighted teacher score  |
| `total_score`        | float  | Raw total score         |
| `validated_features` | int    | Count of validated features |

#### `class_averages`

| Field              | Type  | Description                          |
|--------------------|-------|--------------------------------------|
| `teacher_score`    | float | Mean teacher score across groups     |
| `validated`        | float | Mean validated features per group    |
| `almost`           | float | Mean almost features per group       |
| `missed`           | float | Mean missed features per group       |
| `not_implemented`  | float | Mean not-implemented per group       |

---

## Phase: `validation`

### Per-group JSON

| Field              | Type        | Description                            |
|--------------------|-------------|----------------------------------------|
| `team`             | string      | Full group identifier                  |
| `short_name`       | string      | Display name                           |
| `version`          | string      | Group JAR version                      |
| `total_tests`      | int         | Total tests submitted                  |
| `cleaned_tests`    | int         | Tests after removing duplicates/bad    |
| `valid_tests`      | int         | Tests passing against reference        |
| `invalid_tests`    | int         | Tests failing against reference        |
| `removed_tests`    | int         | Tests removed (compilation, etc.)      |
| `features_score`   | object      | Feature name → float score             |
| `features_detail`  | object      | See [features_detail](#features_detail)|
| `declared_features`| list[str]   | Features declared in manifest          |
| `error`            | string/null | Error message, if any                  |

### `_summary.json`

| Field            | Type   | Description                                |
|------------------|--------|--------------------------------------------|
| `phase`          | string | `"validation"`                             |
| `date`           | string | ISO-8601 timestamp                         |
| `groups_count`   | int    | Number of groups                           |
| `group_rankings` | list   | Groups sorted by `valid_tests` descending  |

#### `group_rankings[i]`

| Field           | Type   | Description                    |
|-----------------|--------|--------------------------------|
| `team`          | string | Full group identifier          |
| `short_name`    | string | Display name                   |
| `valid_tests`   | int    | Valid test count               |
| `total_tests`   | int    | Total test count               |
| `removed_tests` | int    | Removed test count             |
| `clean_rate`    | float  | `cleaned_tests / total_tests`  |

---

## Phase: `self_eval`

### Per-group JSON

| Field            | Type        | Description                            |
|------------------|-------------|----------------------------------------|
| `team`           | string      | Full group identifier                  |
| `short_name`     | string      | Display name                           |
| `version`        | string      | Group JAR version                      |
| `total_score`    | float       | Self-evaluation total score            |
| `features_score` | object      | Feature name → float score             |
| `features_detail`| object      | See [features_detail](#features_detail)|
| `error`          | string/null | Error message, if any                  |

### `_summary.json`

No dedicated self_eval summary is currently produced.

---

## Phase: `cross_testing`

### Per-group JSON

| Field                | Type        | Description                                |
|----------------------|-------------|--------------------------------------------|
| `tester`             | string      | Tester group identifier                    |
| `short_name`         | string      | Display name                               |
| `classification`     | object      | Confusion matrix metrics (see below)       |
| `pairwise_agreement` | object      | Tested group → agreement metrics           |
| `error`              | string/null | Error message, if any                      |

#### `classification` (same as combined `test_quality`)

| Field           | Type  | Description                     |
|-----------------|-------|---------------------------------|
| `total_tests`   | int   | Total tests submitted           |
| `cleaned_tests` | int   | After removing bad tests        |
| `valid_tests`   | int   | Passing against reference       |
| `invalid_tests` | int   | Failing against reference       |
| `removed_tests` | int   | Removed tests                   |
| `tp`            | int   | True positives                  |
| `fp`            | int   | False positives                 |
| `tn`            | int   | True negatives                  |
| `fn`            | int   | False negatives                 |
| `precision`     | float | TP / (TP + FP)                  |
| `recall`        | float | TP / (TP + FN)                  |
| `f1`            | float | Harmonic mean of P and R        |
| `accuracy`      | float | (TP + TN) / total               |

### `_summary.json`

| Field            | Type   | Description                            |
|------------------|--------|----------------------------------------|
| `phase`          | string | `"cross_testing"`                      |
| `date`           | string | ISO-8601 timestamp                     |
| `groups_count`   | int    | Number of groups                       |
| `group_rankings` | list   | Groups sorted by `f1` descending       |
| `class_averages` | object | Class-wide mean `f1`, `precision`, `recall` |

---

## Phase: `coverage`

### Per-group JSON

| Field                  | Type        | Description                        |
|------------------------|-------------|------------------------------------|
| `line_coverage`        | float/null  | Line coverage ratio (0.0–1.0)     |
| `branch_coverage`      | float/null  | Branch coverage ratio              |
| `class_coverage`       | float/null  | Class coverage ratio               |
| `method_coverage`      | float/null  | Method coverage ratio              |
| `instruction_coverage` | float/null  | Instruction coverage ratio         |
| `uncovered_classes`    | list[str]   | Fully uncovered class names        |
| `packages`             | object      | Package name → `{line, branch}`    |
| `error`                | string/null | Error message, if any              |

### `_summary.json`

| Field            | Type   | Description                                  |
|------------------|--------|----------------------------------------------|
| `phase`          | string | `"coverage"`                                 |
| `date`           | string | ISO-8601 timestamp                           |
| `groups_count`   | int    | Number of groups                             |
| `group_rankings` | list   | Groups sorted by `line_coverage` descending  |
| `class_averages` | object | Mean `line_coverage` and `branch_coverage`   |

---

## Phase: `commits`

### Per-group JSON

| Field                | Type        | Description                               |
|----------------------|-------------|-------------------------------------------|
| `team`               | string      | Full group identifier                     |
| `repo_path`          | string      | Path to the git repository                |
| `total_commits`      | int         | Total commits in the repository           |
| `excluded_commits`   | object      | Breakdown of filtered commits (see below) |
| `student_commits`    | int         | Commits attributed to students            |
| `authors`            | object      | Email → author metrics (see below)        |
| `group_metrics`      | object      | Aggregate quality metrics (see below)     |
| `branch_discipline`  | object      | Branch usage analysis (see below)         |
| `ai_detected`        | object      | AI-generated commit detection (see below) |
| `commit_categories`  | object      | Category name → count                     |
| `sample_poor_commits`| list        | Sample of low-quality commits (see below) |
| `error`              | string/null | Error message, if any                     |

#### `excluded_commits`

| Field      | Type | Description                  |
|------------|------|------------------------------|
| `template` | int  | Template/boilerplate commits |
| `teacher`  | int  | Teacher-authored commits     |
| `merge`    | int  | Merge commits                |

#### `authors[email]`

| Field            | Type   | Description                              |
|------------------|--------|------------------------------------------|
| `name`           | string | Author display name                      |
| `commits`        | int    | Total commits by this author             |
| `tier_a`         | int    | Tier A commits (conventional format)     |
| `tier_b`         | int    | Tier B commits (structured but not conventional) |
| `tier_c`         | int    | Tier C commits (descriptive/informal)    |
| `tier_d`         | int    | Tier D commits (poor quality)            |
| `categories`     | object | `{refactor, feat, docs, chore, other}` → count |
| `pct_of_project` | float  | Share of total student commits (0.0–1.0) |
| `quality_score`  | float  | Author quality score (0–100)             |

#### `group_metrics`

| Field              | Type   | Description                                      |
|--------------------|--------|--------------------------------------------------|
| `conventional_rate`| float  | Fraction of commits in Conventional Commits format|
| `structured_rate`  | float  | Fraction with structured messages                |
| `descriptive_rate` | float  | Fraction with descriptive messages               |
| `poor_rate`        | float  | Fraction of poor-quality messages                |
| `quality_score`    | float  | Overall quality score (0–100)                    |
| `quality_grade`    | string | Letter grade: Excellent/Good/Acceptable/Insufficient/Poor/Very Poor |
| `author_balance`   | float  | Balance metric across authors (0.0–1.0)          |

#### `branch_discipline`

| Field                  | Type      | Description                     |
|------------------------|-----------|---------------------------------|
| `uses_feature_branches`| bool      | Whether feature branches exist  |
| `uses_pull_requests`   | bool      | Whether PRs are used            |
| `branch_count`         | int       | Number of branches              |
| `evidence`             | list[str] | Branch names as evidence        |

#### `ai_detected`

| Field      | Type      | Description                       |
|------------|-----------|-----------------------------------|
| `detected` | bool      | Whether AI-generated commits found|
| `evidence` | list[str] | Evidence strings                  |

#### `commit_categories`

Commit type → count. Standard keys: `refactor`, `feat`, `docs`, `chore`, `other`.

#### `sample_poor_commits[i]`

| Field    | Type   | Description           |
|----------|--------|-----------------------|
| `hash`   | string | Abbreviated commit hash|
| `author` | string | Author email          |
| `message`| string | Commit message        |

### `_summary.json`

| Field               | Type   | Description                                  |
|---------------------|--------|----------------------------------------------|
| `phase`             | string | `"commits"`                                  |
| `date`              | string | ISO-8601 timestamp                           |
| `groups_count`      | int    | Number of groups                             |
| `group_rankings`    | list   | Groups sorted by `quality_score` descending  |
| `class_averages`    | object | Mean `quality_score` and `student_commits`   |
| `grade_distribution`| object | Grade → count                                |

---

## Combined group JSON (`groups/<group>.json`)

Merges data from all enabled phases into a single file per group.

| Field                | Type        | Description                               |
|----------------------|-------------|-------------------------------------------|
| `team`               | string      | Full group identifier                     |
| `short_name`         | string      | Shortened display name                    |
| `version`            | string      | Group JAR version (`"?"` if unknown)      |
| `feature_tally`      | object      | See [feature_tally](#feature_tally)       |
| `test_tally`         | object      | Same structure, for tests                 |
| `features_detail`    | object      | See [features_detail](#features_detail)   |
| `manifest_features`  | list[str]   | Declared features                         |
| `teacher_evaluation` | object      | Teacher eval results (see below)          |
| `self_evaluation`    | object      | `{features_score, total_score}`           |
| `test_quality`       | object      | Cross-testing metrics (same as `classification`) |
| `coverage`           | object/null | Coverage data or null if not enabled      |
| `commits`            | object/null | Commits data or null if not enabled       |

### `teacher_evaluation` (combined)

| Field                    | Type        | Description                   |
|--------------------------|-------------|-------------------------------|
| `features_score`         | object      | Feature name → float score    |
| `total_score`            | float       | Raw total score               |
| `milestone_scores`       | object      | Milestone index → score       |
| `teacher_score`          | float       | Weighted teacher score        |
| `teacher_score_breakdown`| object      | See above                     |
| `test_suite`             | string      | Test suite filename           |
| `test_suite_metadata`    | object/null | Test suite metadata           |
