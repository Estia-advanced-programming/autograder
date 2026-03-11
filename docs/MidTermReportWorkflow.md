# Mid-Term Report Generation Workflow

How to generate (or regenerate) mid-term evaluation reports for the Pandora project.

## Prerequisites

- Python 3 available as `python3`
- Autograder has already been run, producing:
  - `reports/json/pandora-2026-the_*.json` — one JSON per student group
  - `reports/summary_data.json` — aggregated summary data
  - `reports/class_report.qmd` — raw feature matrix (autograder output)

## Step-by-Step

### 1. Generate individual group reports

```bash
cd /path/to/autograder_python
python3 reports/_gen_reports.py
```

This reads all JSON data from `reports/json/` and `reports/summary_data.json`, then generates one `.qmd` file per group in `reports/groups/`.

**Options:**
```
--json-dir DIR     Directory with per-group JSONs (default: reports/json)
--summary PATH     Path to summary_data.json (default: reports/summary_data.json)
--out-dir DIR      Output directory for .qmd files (default: reports/groups)
```

### 2. Write/update the class summary

The class summary (`reports/report_summary.qmd`) is written manually (or with AI assistance) based on:

- The data in `reports/summary_data.json` (rankings, scores, feature tallies)
- Patterns visible across the individual group reports
- Teacher pointers stored in the memory file (see below)

The summary should include:
- Scoring methodology (🟢 count as primary metric, teacher score as provisional)
- Class-at-a-glance statistics
- Tier-based ranking tables (Advanced ≥60%, Progressing 35-59%, Developing 15-34%, Getting Started <15%)
- Key patterns discovered across the class
- Common issues & actionable advice (numbered sections)
- Awards for notable achievements
- Per-tier "What to focus on next" sections
- Links to individual group reports

### 3. Review and revise

After generating both the group reports and the class summary:
1. Re-read the class summary
2. Cross-reference with the individual reports for accuracy
3. Improve with deeper patterns discovered during the review

## Key Domain Knowledge

**Critical facts** to keep in mind when writing reports — stored in `/memories/repo/pandora-teacher-pointers.md`:

- **No multi-file tests exist.** The 12/22→17/22→22/22 pattern is about **output modes** (full report vs feature mode), NOT multi-file handling.
- **Teacher Score is provisional** — use 🟢 validated feature count as the primary metric.
- **Engine power**: students divide by engine count instead of using total plane power.
- **Version numbers**: students choose their own semver scheme — don't comment on it.
- **Flight distance**: needs altitude (3D), but don't tell students — just hint it's complex.
- **Wind speed**: air speed is only in the plane's direction; computing ground speed from GPS is the real challenge.

## File Inventory

| File | Purpose |
|------|---------|
| `reports/_gen_reports.py` | Generates individual group `.qmd` reports |
| `reports/_parse_reports.py` | Quick data inspection/debugging utility |
| `reports/report_summary.qmd` | Class-wide summary report (manual/AI) |
| `reports/groups/*.qmd` | Individual group reports (auto-generated) |
| `reports/summary_data.json` | Input: aggregated summary data |
| `reports/json/pandora-2026-the_*.json` | Input: per-group detailed JSON |
| `reports/class_report.qmd` | Input: raw feature matrix from autograder |

## Rendering (Quarto)

To render the reports to HTML:
```bash
quarto render reports/report_summary.qmd
quarto render reports/groups/  # renders all group reports
```
