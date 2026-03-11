# Mid-Term Report Generation Workflow

How to generate (or regenerate) mid-term evaluation reports for the Pandora project.

## Prerequisites

- Python 3 available as `python3`
- `pyyaml` installed (`pip install pyyaml`)

## Step-by-Step

### 1. Update student repos & build

```bash
find ../2026/pandora-2026-submissions -name pom.xml -print0 \
  | xargs -0 -n1 dirname | sort -u \
  | while IFS= read -r d; do (cd "$d" && git pull && mvn package); done
```

### 2. Run class_grader (produces JSON)

```bash
python3 class_grader.py -C config.yml
```

This runs all evaluation phases (teacher eval, validation, self-eval, cross-testing, commits, coverage if enabled) and writes structured JSON output:

```
reports/
├── teacher_eval/      _meta.json + _summary.json + per-group .json
├── validation/
├── self_eval/
├── cross_testing/
├── commits/
├── coverage/          (if enabled)
└── groups/            combined per-group .json (all phases merged)
```

See `docs/output_schema.md` for the full JSON schema.

### 3. Generate reports (reads JSON → .qmd)

```bash
python3 report_generator.py reports/
```

This reads the JSON from step 2 and generates:
- `reports/class_report.qmd` — class-wide summary with feature matrices, rankings, commit analysis
- `reports/groups/<group>.qmd` — individual group reports

### 4. Write/update the class summary narrative

The class summary report (`reports/report_summary.qmd`) is written manually (or with AI assistance) based on:

- The data in the JSON output and `_summary.json` files
- Patterns visible across the individual group reports

The summary typically includes:
- Scoring methodology
- Class-at-a-glance statistics
- Tier-based ranking tables
- Common issues & actionable advice
- Per-tier "What to focus on next" sections

### 5. Render to HTML

```bash
quarto render reports/class_report.qmd
quarto render reports/groups/  # renders all group reports
```

## Key Domain Knowledge

**Critical facts** to keep in mind when writing reports:

- **No multi-file tests exist.** The 12/22→17/22→22/22 pattern is about **output modes** (full report vs feature mode), NOT multi-file handling.
- **Teacher Score is provisional** — use 🟢 validated feature count as the primary metric.
- **Engine power**: students divide by engine count instead of using total plane power.
- **Version numbers**: students choose their own semver scheme — don't comment on it.
- **Flight distance**: needs altitude (3D), but don't tell students — just hint it's complex.
- **Wind speed**: air speed is only in the plane's direction; computing ground speed from GPS is the real challenge.

## File Inventory

| File | Purpose |
|------|---------|
| `class_grader.py` | Batch orchestration + grading → JSON output |
| `report_generator.py` | Reads JSON → generates `.qmd` reports |
| `autograder.py` | Per-group test execution engine |
| `config.yml` | Configuration (dirs, phases, scoring, commits) |
| `reports/groups/<group>.json` | Combined per-group JSON |
| `reports/<phase>/_summary.json` | Class-level phase summaries |
| `reports/_archive/` | Retired scripts (`_gen_reports.py`, `_parse_reports.py`) |
