#!/usr/bin/env python3
"""
Report Generator — reads JSON output from class_grader.py and generates
Quarto (.qmd) reports.

Produces:
  - class_report.qmd   : feature matrices, metrics tables, class summary (OJS)
  - groups/*.qmd        : individual group reports (plain markdown)
  - summary_data.json   : data for interactive OJS tables

Usage:
    python3 report_generator.py --all --input reports/
    python3 report_generator.py --class-report --input reports/
    python3 report_generator.py --group-reports --input reports/
"""

import argparse
import glob
import json
import os
import sys


# ── Helpers ──────────────────────────────────────────────────────────────────

PASS_THRESHOLD = 0.9
PARTIAL_THRESHOLD = 0.5

STATUS_BADGE = {
    "validated": "🟢",
    "almost": "🟡",
    "missed": "🔴",
    "not_implemented": "⚪️",
}


def badge(score, declared=True):
    if not declared:
        return "⚪️"
    if score >= PASS_THRESHOLD:
        return "🟢"
    if score >= PARTIAL_THRESHOLD:
        return "🟡"
    return "🔴"


def shorten_team_name(name):
    import re

    match = re.search(r"the_(\w+)_(\w+)", name)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return name


def _fmt_tally(tally):
    return (
        f"\U0001f7e2{tally.get('validated', 0)} "
        f"\U0001f7e1{tally.get('almost', 0)} "
        f"\U0001f534{tally.get('missed', 0)} "
        f"\u26aa{tally.get('not_implemented', 0)}"
    )


# ── Data loading ─────────────────────────────────────────────────────────────


def load_groups(input_dir):
    """Load all group JSON files from groups/ directory."""
    groups_dir = os.path.join(input_dir, "groups")
    groups = {}
    if not os.path.isdir(groups_dir):
        return groups
    for path in sorted(glob.glob(os.path.join(groups_dir, "*.json"))):
        with open(path) as f:
            data = json.load(f)
        team = data.get("team", os.path.splitext(os.path.basename(path))[0])
        groups[team] = data
    return groups


def load_phase_summary(input_dir, phase_name):
    """Load _summary.json for a given phase."""
    path = os.path.join(input_dir, phase_name, "_summary.json")
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return None


def load_phase_meta(input_dir, phase_name):
    """Load _meta.json for a given phase."""
    path = os.path.join(input_dir, phase_name, "_meta.json")
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return None


def collect_all_features(groups):
    """Collect all features seen across all groups."""
    features = set()
    for data in groups.values():
        for key in ("features_detail",):
            features.update(data.get(key, {}).keys())
        te = data.get("teacher_evaluation", {})
        features.update(te.get("features_score", {}).keys())
    return sorted(features)


def sort_features_by_success(features, groups):
    """Sort features by success rate (most-passed first)."""
    counts = {}
    for feat in features:
        ok = 0
        total = 0
        for data in groups.values():
            fd = data.get("features_detail", {}).get(feat)
            if fd is not None:
                total += 1
                if fd.get("status") == "validated":
                    ok += 1
        counts[feat] = (ok / total if total else 0, feat)
    return sorted(features, key=lambda f: (-counts[f][0], f))


# ── Class report generation ─────────────────────────────────────────────────


def _md_feature_group_matrix(
    title,
    all_features,
    group_names,
    groups,
    score_key="teacher_evaluation",
    use_detail=True,
):
    """Build a markdown feature × group matrix."""
    lines = [f"## {title}", ""]
    lines.append("::: {.column-screen-inset}")
    short_names = [shorten_team_name(g) for g in group_names]
    header = "| Feature | " + " | ".join(short_names) + " |"
    sep = "|---------|" + "|".join(["------"] * len(group_names)) + "|"
    lines += [header, sep]

    for feat in all_features:
        cells = []
        for gname in group_names:
            data = groups.get(gname, {})
            if use_detail:
                detail = data.get("features_detail", {}).get(feat)
                if detail is not None:
                    b = STATUS_BADGE.get(detail.get("status", "missed"), "🔴")
                    cells.append(
                        f"{b} ^{detail.get('valid', 0)}/{detail.get('total', 0)}^"
                    )
                    continue
            # Fallback to score
            score = data.get(score_key, {}).get("features_score", {}).get(feat)
            if score is None:
                cells.append("⚪️")
            else:
                cells.append(badge(score))
        lines.append(f"| {feat} | " + " | ".join(cells) + " |")

    lines.append("")
    lines.append(f": {title} " + "{.striped .hover .borderless .responsive}")
    lines.append(":::")
    lines.append("")
    return "\n".join(lines)


def _md_validation_matrix(title, all_features, group_names, groups):
    """Build validation matrix (student tests → teacher JAR)."""
    lines = [f"## {title}", ""]
    lines.append("::: {.column-screen-inset}")
    short_names = [shorten_team_name(g) for g in group_names]
    header = "| Feature | " + " | ".join(short_names) + " |"
    sep = "|---------|" + "|".join(["------"] * len(group_names)) + "|"
    lines += [header, sep]

    for feat in all_features:
        cells = []
        for gname in group_names:
            data = groups.get(gname, {})
            val_scores = data.get("validation", {}).get("features_score", {})
            manifest = data.get("manifest_features", [])
            score = val_scores.get(feat)
            if score is None:
                cells.append("⚪️")
            else:
                cells.append(
                    badge(score, declared=(feat in manifest if manifest else True))
                )
        lines.append(f"| {feat} | " + " | ".join(cells) + " |")

    lines.append("")
    lines.append(f": {title} " + "{.striped .hover .borderless .responsive}")
    lines.append(":::")
    lines.append("")
    return "\n".join(lines)


def _md_metrics_table(title, group_names, groups):
    """Cross-testing metrics: confusion matrix + precision/recall/F1."""
    lines = []
    lines.append(
        "| Team | Detected & Correct (TP) | Not Detected & Correct (FN) "
        "| Detected & Incorrect (FP) | Not Detected & Incorrect (TN) "
        "| Precision | Recall | F1 | Accuracy |"
    )
    lines.append(
        "|------|:-----------------------:|:---------------------------:"
        "|:-------------------------:|:-----------------------------:"
        "|:---------:|:------:|:--:|:--------:|"
    )
    rows = []
    for gname in group_names:
        tq = groups.get(gname, {}).get("test_quality", {})
        rows.append((gname, tq))
    rows.sort(key=lambda x: -x[1].get("f1", 0))

    for gname, m in rows:
        short_name = shorten_team_name(gname)
        lines.append(
            f"| {short_name} "
            f"| {m.get('tp', 0)} | {m.get('fn', 0)} | {m.get('fp', 0)} | {m.get('tn', 0)} "
            f"| {m.get('precision', 0):.2f} | {m.get('recall', 0):.2f} "
            f"| {m.get('f1', 0):.2f} | {m.get('accuracy', 0):.2f} |"
        )
    lines.append("")
    lines.append(f": {title} " + "{.striped .hover .borderless .responsive}")
    lines.append("")
    return "\n".join(lines)


def _md_summary_table(group_names, groups):
    """Per-group summary table (static markdown)."""
    lines = []
    lines.append(
        "| Team | Version | Teacher Score | Test Quality (F1) "
        "| Features (\U0001f7e2/\U0001f7e1/\U0001f534/\u26aa) "
        "| Tests (\U0001f7e2/\U0001f7e1/\U0001f534/\u26aa) "
        "| Valid Tests | Removed |"
    )
    lines.append(
        "|------|---------|---------------"
        "|------------------"
        "|------------------"
        "|-------------------|-------------|---------|"
    )
    for gname in group_names:
        d = groups.get(gname, {})
        short_name = shorten_team_name(gname)
        version = d.get("version", "?")
        teacher_score = (
            max(0, min(1, d.get("teacher_evaluation", {}).get("teacher_score", 0)))
            * 100
        )
        tq = d.get("test_quality", {})
        f1 = tq.get("f1", 0) * 100
        valid = tq.get("valid_tests", 0)
        total = tq.get("total_tests", 0)
        removed = tq.get("removed_tests", 0)
        ft = d.get("feature_tally", {})
        tt = d.get("test_tally", {})
        feat_cell = _fmt_tally(ft) if ft else ""
        test_cell = _fmt_tally(tt) if tt else ""
        lines.append(
            f"| {short_name} | {version} | {teacher_score:.0f}% | {f1:.0f}% "
            f"| {feat_cell} "
            f"| {test_cell} "
            f"| {valid}/{total} | {removed} |"
        )
    lines.append("")
    lines.append(": Class Summary {.primary .striped .hover .borderless .responsive}")
    lines.append("")
    return "\n".join(lines)


def generate_class_report(input_dir, output_dir, groups, sort_features_by="success"):
    """Generate class_report.qmd from JSON data."""
    group_names = sorted(groups.keys())
    all_features = collect_all_features(groups)

    if sort_features_by == "success":
        all_features = sort_features_by_success(all_features, groups)
    # else: alphabetical (already sorted)

    # Load phase metadata for test counts
    teacher_meta = load_phase_meta(input_dir, "teacher_eval")
    test_count = "?"
    feature_count = len(all_features)
    suite_name = "teacher test suite"
    if teacher_meta:
        test_count = teacher_meta.get("total_tests", "?")
        md = teacher_meta.get("test_suite_metadata") or {}
        suite_name = md.get("suiteName", suite_name)

    # Check which phases have data
    has_teacher = any(groups[g].get("teacher_evaluation") for g in group_names)
    has_validation = any(groups[g].get("validation") for g in group_names)
    has_cross = any(
        groups[g].get("test_quality", {}).get("f1") is not None for g in group_names
    )
    has_coverage = any(groups[g].get("coverage") for g in group_names)
    has_commits = any(groups[g].get("commits") for g in group_names)

    parts = []

    # YAML frontmatter
    parts.append(
        """\
---
title: "Class Grader Report"
format:
  html:
    page-layout: full
---
"""
    )

    # CSS for vertical column headers
    parts.append(
        """```{=html}
<style>
table thead th:not(:first-child) {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    vertical-align: bottom;
    padding: 0.2em 0.5em;
    min-height: 150px;
    white-space: nowrap;
}
table thead th:first-child {
    writing-mode: horizontal-tb;
    text-align: left;
}
</style>
```

"""
    )

    # Legend
    parts.append(
        """\
## Legend

| Badge | Meaning | Score range |
|-------|---------|-------------|
| 🟢 | **Validated** — the feature/test passes | score ≥ 0.9 |
| 🟡 | **Almost** — close but not passing | 0.5 ≤ score < 0.9 |
| 🔴 | **Missed** — the feature was attempted but the output is wrong | score < 0.5 |
| ⚪️ | **Not implemented / not declared** — the feature is not listed in the team's manifest or was not found in the output | — |

: Legend {.striped .hover .borderless .responsive}

"""
    )

    # Teacher Evaluation
    if has_teacher:
        parts.append(
            f"""\
## Teacher Evaluation (Teacher Tests → Student Pandoras)

**Goal**: measure how well each team's Pandora implements the expected features.

The teacher's test suite ({suite_name}, **{test_count} tests** \
covering **{feature_count} features**) is run against each team's JAR.
For every feature, the autograder compares the student's output to the expected \
value with a numeric tolerance. The per-feature score is the average across all \
tests for that feature (1.0 = perfect match, 0.0 = completely wrong or missing).

Only features declared in the team's `manifest.json` are evaluated; \
undeclared features appear as ⚪️.

"""
        )
        parts.append(
            _md_feature_group_matrix(
                "Results",
                all_features,
                group_names,
                groups,
                score_key="teacher_evaluation",
                use_detail=True,
            )
        )

    # Validation
    if has_validation:
        parts.append(
            """\
## Test Suite Validation (Student Tests → Teacher Pandora)

**Goal**: assess the quality of each team's own test suite.

Each team's `testSuite.json` is first **cleaned** (tests referencing missing \
files or non-whitelisted features are removed), then run against the \
**reference implementation** (teacher's JAR, which is assumed to be correct).

A test that passes against the reference is **valid** — it checks something \
that the correct implementation actually produces. A test that fails is \
**invalid** — the expected value in the test is wrong.

"""
        )
        parts.append(
            _md_validation_matrix("Results", all_features, group_names, groups)
        )

    # Cross-testing
    if has_cross:
        parts.append(
            """\
## Test Quality Metrics (Cross-Testing)

**Goal**: evaluate how accurately each team's tests distinguish correct from \
incorrect implementations.

Each team's cleaned test suite is run against **every other team's** Pandora. \
The results are compared to the ground truth (teacher evaluation) to compute \
confusion matrix counts and classification metrics:

| Column | Meaning |
|--------|----------|
| **Detected & Correct (TP)** | Feature correctly implemented AND your tests detect it |
| **Not Detected & Correct (FN)** | Feature correctly implemented BUT your tests miss it |
| **Detected & Incorrect (FP)** | Feature incorrectly implemented BUT your tests say it passes |
| **Not Detected & Incorrect (TN)** | Feature incorrectly implemented AND your tests correctly reject it |
| **Precision** | TP / (TP + FP) — of features your tests accept, how many are truly correct? |
| **Recall** | TP / (TP + FN) — of features that are truly correct, how many do your tests detect? |
| **Accuracy** | (TP + TN) / total — overall rate of correct classifications |

: Column Definitions {.striped .hover .borderless .responsive}

"""
        )
        parts.append(_md_metrics_table("Cross-Testing Results", group_names, groups))

    # Coverage summary
    if has_coverage:
        parts.append(
            """\
## Code Coverage

| Team | Line Coverage | Branch Coverage |
|------|:------------:|:--------------:|"""
        )
        rows = []
        for gname in group_names:
            cov = groups[gname].get("coverage")
            if cov and not cov.get("error"):
                rows.append(
                    (gname, cov.get("line_coverage", 0), cov.get("branch_coverage", 0))
                )
        rows.sort(key=lambda x: -(x[1] or 0))
        for gname, line_cov, branch_cov in rows:
            lc = f"{line_cov:.0%}" if line_cov is not None else "—"
            bc = f"{branch_cov:.0%}" if branch_cov is not None else "—"
            parts.append(f"| {shorten_team_name(gname)} | {lc} | {bc} |")
        parts.append("\n: Code Coverage {.striped .hover .borderless .responsive}\n")

    # Commit quality summary
    if has_commits:
        parts.append(
            """\
## Commit Quality

| Team | Commits | Grade | Conventional | Poor | Branch Discipline | AI Flag |
|------|:-------:|:-----:|:------------:|:----:|:-----------------:|:-------:|"""        )
        rows = []
        for gname in group_names:
            c = groups[gname].get("commits")
            if c:
                gm = c.get("group_metrics", {})
                bd = c.get("branch_discipline", {})
                ai = c.get("ai_detected", {})
                branch_str = ""
                if bd.get("uses_pull_requests"):
                    branch_str = "PR"
                elif bd.get("uses_feature_branches"):
                    branch_str = "branches"
                else:
                    branch_str = "—"
                ai_str = "⚠️" if ai.get("detected") else "—"
                rows.append(
                    (
                        gname,
                        c.get("student_commits", 0),
                        gm.get("quality_grade", "?"),
                        f"{gm.get('conventional_rate', 0):.0%}",
                        f"{gm.get('poor_rate', 0):.0%}",
                        branch_str,
                        ai_str,
                    )
                )
        rows.sort(key=lambda x: -x[1])
        for gname, commits, grade, conv, poor, branch, ai in rows:
            parts.append(
                f"| {shorten_team_name(gname)} | {commits} | {grade} "
                f"| {conv} | {poor} | {branch} | {ai} |"
            )
        parts.append("\n: Commit Quality {.striped .hover .borderless .responsive}\n")

    # Class Summary (static)
    parts.append(
        f"""\
## Class Summary

One row per team. The **Features** and **Tests** columns show how many \
items fall in each category:
🟢 validated · 🟡 almost · 🔴 missed · ⚪ not implemented.

"""
    )
    parts.append(_md_summary_table(group_names, groups))

    # Build summary_data.json for OJS
    summary_rows = _build_summary_data(group_names, groups)
    summary_json_path = os.path.join(output_dir, "summary_data.json")
    with open(summary_json_path, "w") as f:
        json.dump(summary_rows, f, ensure_ascii=False)

    # OJS interactive table
    parts.append(
        """\
```{ojs}
data = FileAttachment("summary_data.json").json()
Inputs.table(data, { sort: "Teacher Score", reverse: true })
```
"""
    )

    report_text = "\n".join(parts)
    report_path = os.path.join(output_dir, "class_report.qmd")
    with open(report_path, "w") as f:
        f.write(report_text)
    print(f"Class report written to {report_path}")
    return report_path


def _build_summary_data(group_names, groups):
    """Build summary_data.json rows for OJS tables."""
    rows = []
    for gname in group_names:
        d = groups.get(gname, {})
        ft = d.get("feature_tally", {})
        tt = d.get("test_tally", {})
        tq = d.get("test_quality", {})
        te = d.get("teacher_evaluation", {})
        cov = d.get("coverage") or {}
        commits = d.get("commits") or {}
        gm = commits.get("group_metrics", {}) if commits else {}
        row = {
            "Team": shorten_team_name(gname),
            "Version": d.get("version", "?"),
            "Teacher Score": round(
                te.get("teacher_score", te.get("teacher_score", 0)), 4
            ),
            "Avg Score": round(te.get("total_score", 0), 2),
            "F\u2705": ft.get("validated", 0),
            "F\U0001f7e1": ft.get("almost", 0),
            "F\u274c": ft.get("missed", 0),
            "F\u26aa": ft.get("not_implemented", 0),
            "T\u2705": tt.get("validated", 0),
            "T\U0001f7e1": tt.get("almost", 0),
            "T\u274c": tt.get("missed", 0),
            "T\u26aa": tt.get("not_implemented", 0),
            "F1": round(tq.get("f1", 0), 2),
            "Valid Tests": tq.get("valid_tests", 0),
            "Total Tests": tq.get("total_tests", 0),
            "Removed": tq.get("removed_tests", 0),
        }
        # Optional columns
        if cov and not cov.get("error"):
            line_cov = cov.get("line_coverage")
            row["Line Cov"] = f"{line_cov:.0%}" if line_cov is not None else ""
        if gm:
            row["Commit Grade"] = gm.get("quality_grade", "")
        rows.append(row)
    return rows


# ── Group report generation ──────────────────────────────────────────────────


def _determine_tier(teacher_score):
    """Return (tier_name, tier_emoji) based on teacher score."""
    if teacher_score >= 0.60:
        return "Advanced", "🏆"
    elif teacher_score >= 0.35:
        return "Progressing", "📈"
    elif teacher_score >= 0.15:
        return "Developing", "🔧"
    return "Getting Started", "🚀"


def _generate_advice(features, ft, tq, coverage, commits):
    """Generate pattern-based advice for a group."""
    f_ok = ft.get("validated", 0)
    f_al = ft.get("almost", 0)
    f_mi = ft.get("missed", 0)
    f_total = f_ok + f_al + f_mi
    f1 = tq.get("f1", 0)
    valid_tests = tq.get("valid_tests", 0)
    total_tests = tq.get("total_tests", 0)

    if f_total == 0:
        return [
            "**Priority: Get your Pandora running.** No features were detected by "
            "the autograder. Make sure your JAR executes correctly, produces output "
            "in the expected format, and that your `manifest.json` declares the "
            "features you have implemented. Start with the simplest features: "
            "`avgAlt`, `maxAlt`, `flightDuration`."
        ]

    teacher_score = (f_ok + f_al * 0.5) / max(f_total, 1)
    if teacher_score == 0 and f_mi > 0:
        return [
            f"**Priority: Fix your output format.** Your Pandora declares {f_mi} "
            "features but none pass. This usually means a formatting or parsing "
            "issue. Double-check your output against the specification. Compare "
            "your output character-by-character with the expected values."
        ]

    advice = []

    if f_al > f_ok and f_al > 5:
        advice.append(
            f'You have **{f_al} features at "almost"** status — these are very '
            "close to passing. Focus on converting these to green. Common causes: "
            "rounding/precision issues, off-by-one in averaging, or only handling "
            "one output mode (full report vs feature mode)."
        )

    has_engine_issue = any(
        feat in ("avgEnginePower", "maxEnginePower") and info.get("status") == "missed"
        for feat, info in features.items()
    )
    if has_engine_issue:
        advice.append(
            "**Engine power** features are failing. Remember: the feature is the "
            "engine power of the *plane*, not individual engines. Make sure you "
            "are using the total engine power."
        )

    has_accel_issue = any(
        ("Acceleration" in feat or "AccelG" in feat)
        for feat, info in features.items()
        if info.get("status") == "missed"
    )
    if has_accel_issue:
        advice.append(
            "**Acceleration** features are not passing. Acceleration requires "
            "computing derivatives from speed data — double-check your formula "
            "and units."
        )

    has_distance_issue = any(
        feat in ("flightDistance", "windSpeed") and info.get("status") == "missed"
        for feat, info in features.items()
    )
    if has_distance_issue:
        advice.append(
            "**Distance/Wind** features need work. For `flightDistance`, the "
            "computation requires altitude data. For `windSpeed`, note that air "
            "speed is only recorded in the direction of the plane."
        )

    phase_missed = [
        feat
        for feat, info in features.items()
        if info.get("status") == "missed"
        and any(
            p in feat
            for p in ("Cruise", "Landing", "TakeOff", "cruise", "landing", "takeOff")
        )
    ]
    if phase_missed:
        advice.append(
            f'**Phase-specific features** ({", ".join(phase_missed[:5])}) are '
            "not passing. Make sure you correctly detect flight phases (takeoff, "
            "cruise, landing) from the altitude/speed profile."
        )

    if total_tests == 0:
        advice.append(
            "**You have not submitted a test suite.** Writing tests is a key "
            "part of the evaluation. Create `testSuite.json` with at least one "
            "test per feature you implemented."
        )
    elif valid_tests == 0 and total_tests > 0:
        advice.append(
            f"**None of your {total_tests} tests are valid** against the "
            "reference implementation. Your expected values are incorrect."
        )
    elif f1 < 0.20 and total_tests > 0:
        advice.append(
            f"Your test suite F1 score is low ({f1:.2f}). Improve test quality "
            "by verifying expected values against the reference output."
        )

    # Coverage advice
    if coverage and not coverage.get("error"):
        line_cov = coverage.get("line_coverage")
        if line_cov is not None and line_cov < 0.3:
            advice.append(
                f"Your line coverage is **{line_cov:.0%}**. Consider adding more "
                "tests to cover untested code paths."
            )

    # Commit advice
    if commits:
        gm = commits.get("group_metrics", {})
        poor_rate = gm.get("poor_rate", 0)
        if poor_rate > 0.4:
            advice.append(
                f"**{poor_rate:.0%} of your commits have poor messages.** Use "
                "conventional commits format: `feat: description`, `fix: bug`, "
                "`test: add tests for X`."
            )
        ai = commits.get("ai_detected", {})
        if ai.get("detected"):
            advice.append(
                "⚠️ **AI-generated code detected** in your commit history. "
                "Make sure all code is understood and can be explained by team members."
            )

    if not advice:
        advice.append(
            "Keep up the good work! Focus on expanding feature coverage and "
            "improving precision on existing features."
        )

    return advice


def generate_group_report(team_name, data):
    """Generate .qmd content for a single group."""
    ft = data.get("feature_tally", {})
    tt = data.get("test_tally", {})
    tq = data.get("test_quality", {})
    features = data.get("features_detail", {})
    te = data.get("teacher_evaluation", {})
    coverage = data.get("coverage")
    commits = data.get("commits")
    version = data.get("version", "?")

    teacher_score = te.get("teacher_score", te.get("teacher_score", 0))
    tier, tier_emoji = _determine_tier(te.get("teacher_score", 0))

    validated = [(k, v) for k, v in features.items() if v.get("status") == "validated"]
    almost = [(k, v) for k, v in features.items() if v.get("status") == "almost"]
    missed = [(k, v) for k, v in features.items() if v.get("status") == "missed"]

    f_ok = ft.get("validated", 0)
    f_al = ft.get("almost", 0)
    f_mi = ft.get("missed", 0)
    f_ni = ft.get("not_implemented", 0)
    f_total = f_ok + f_al + f_mi

    f1 = tq.get("f1", 0)
    valid_tests = tq.get("valid_tests", 0)
    total_tests = tq.get("total_tests", 0)
    removed = tq.get("removed_tests", 0)

    short = shorten_team_name(team_name)
    display_name = short.replace("_", " ").title()

    lines = []
    lines.append("---")
    lines.append(f'title: "Group Report — {display_name}"')
    lines.append("---")
    lines.append("")
    lines.append("[← Back to Class Summary](../class_report.qmd)")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| **Team** | {display_name} |")
    lines.append(f"| **Version** | {version} |")
    lines.append(f"| **Teacher Score** | {teacher_score:.4f} |")
    lines.append(f"| **Average Score** | {te.get('total_score', 0):.0%} |")
    lines.append(f"| **Tier** | {tier_emoji} {tier} |")
    lines.append("")

    # Feature Implementation
    lines.append("## Feature Implementation")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| 🟢 Validated | {f_ok} |")
    lines.append(f"| 🟡 Almost | {f_al} |")
    lines.append(f"| 🔴 Missed | {f_mi} |")
    lines.append(f"| ⚪ Not implemented | {f_ni} |")
    lines.append(f"| **Features attempted** | **{f_total}** / {f_total + f_ni} |")
    lines.append("")

    if validated:
        lines.append("### 🟢 Validated Features")
        lines.append("")
        for feat, info in validated:
            lines.append(
                f'- **{feat}** — {info["valid"]}/{info["total"]} tests passed '
                f'(score: {info["score"]:.0%})'
            )
        lines.append("")

    if almost:
        lines.append("### 🟡 Almost There")
        lines.append("")
        for feat, info in almost:
            lines.append(
                f'- **{feat}** — {info["valid"]}/{info["total"]} tests passed '
                f'(score: {info["score"]:.0%})'
            )
        lines.append("")

    if missed:
        lines.append("### 🔴 Missed Features")
        lines.append("")
        for feat, info in missed:
            lines.append(
                f'- **{feat}** — {info["valid"]}/{info["total"]} tests passed '
                f'(score: {info["score"]:.0%})'
            )
        lines.append("")

    # Self-evaluation comparison
    se = data.get("self_evaluation")
    if se:
        se_score = se.get("total_score", 0)
        te_score = te.get("total_score", 0)
        delta = se_score - te_score
        lines.append("## Self-Evaluation vs Teacher Evaluation")
        lines.append("")
        lines.append("| | Teacher | Self | Δ |")
        lines.append("|---|:---:|:---:|:---:|")
        lines.append(
            f"| Average Score | {te_score:.2f} | {se_score:.2f} | {delta:+.2f} |"
        )
        lines.append("")

    # Test Suite Quality
    lines.append("## Test Suite Quality")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Valid tests | {valid_tests} |")
    lines.append(f"| Total tests submitted | {total_tests} |")
    lines.append(f"| Removed (invalid ref/features) | {removed} |")
    lines.append(f"| F1 score | {f1:.2f} |")
    lines.append("")

    # Coverage
    if coverage and not coverage.get("error"):
        lines.append("## Code Coverage")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lc = coverage.get("line_coverage")
        bc = coverage.get("branch_coverage")
        if lc is not None:
            lines.append(f"| Line coverage | {lc:.0%} |")
        if bc is not None:
            lines.append(f"| Branch coverage | {bc:.0%} |")
        uncovered = coverage.get("uncovered_classes", [])
        if uncovered:
            lines.append(f"| Uncovered classes | {len(uncovered)} |")
        lines.append("")

    # Commits
    if commits:
        gm = commits.get("group_metrics", {})
        bd = commits.get("branch_discipline", {})
        ai = commits.get("ai_detected", {})
        authors = commits.get("authors", {})

        lines.append("## Commit Quality")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Student commits | {commits.get('student_commits', 0)} |")
        lines.append(f"| Quality grade | **{gm.get('quality_grade', '?')}** |")
        lines.append(f"| Quality score | {gm.get('quality_score', 0):.0f}/100 |")
        lines.append(f"| Conventional rate | {gm.get('conventional_rate', 0):.0%} |")
        lines.append(f"| Structured rate | {gm.get('structured_rate', 0):.0%} |")
        lines.append(f"| Poor rate | {gm.get('poor_rate', 0):.0%} |")
        if bd.get("uses_pull_requests"):
            lines.append("| Branch discipline | Pull requests |")
        elif bd.get("uses_feature_branches"):
            lines.append(
                f"| Branch discipline | Feature branches ({bd.get('branch_count', 0)}) |"
            )
        if ai.get("detected"):
            lines.append("| ⚠️ AI detected | Yes |")
        lines.append("")

        # Per-student table
        if authors:
            lines.append("### Per-Student Contributions")
            lines.append("")
            lines.append(
                "| Student | Commits | % of project | Quality | A | B | C | D |"
            )
            lines.append(
                "|---------|:-------:|:------------:|:-------:|:-:|:-:|:-:|:-:|"
            )
            total_student = commits.get("student_commits", 1)
            for author_name, ainfo in sorted(
                authors.items(), key=lambda x: -x[1].get("commits", 0)
            ):
                ac = ainfo.get("commits", 0)
                pct = ainfo.get("pct_of_project", ac / max(total_student, 1))
                aq = ainfo.get("quality_score", 0)
                lines.append(
                    f"| {ainfo.get('name', author_name)} | {ac} | {pct:.0%} | {aq:.0f} "
                    f"| {ainfo.get('tier_a', 0)} | {ainfo.get('tier_b', 0)} "
                    f"| {ainfo.get('tier_c', 0)} | {ainfo.get('tier_d', 0)} |"
                )
            lines.append("")

    # Advice
    advice = _generate_advice(features, ft, tq, coverage, commits)
    lines.append("## Advice & Next Steps")
    lines.append("")
    for a in advice:
        lines.append(f"- {a}")
        lines.append("")

    return "\n".join(lines)


def generate_group_reports(input_dir, output_dir, groups):
    """Generate individual group .qmd reports."""
    groups_qmd_dir = os.path.join(output_dir, "groups")
    os.makedirs(groups_qmd_dir, exist_ok=True)

    # Skip teacher reference
    student_groups = {k: v for k, v in groups.items() if "awesome_teachers" not in k}

    count = 0
    for team_name, data in sorted(student_groups.items()):
        content = generate_group_report(team_name, data)
        short = shorten_team_name(team_name).replace(" ", "_")
        outpath = os.path.join(groups_qmd_dir, f"{short}.qmd")
        with open(outpath, "w") as f:
            f.write(content)
        count += 1

    print(f"Generated {count} group reports in {groups_qmd_dir}/")


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate Quarto reports from class_grader JSON output."
    )
    parser.add_argument(
        "--input",
        default="reports",
        help="Input directory with class_grader JSON output (default: reports/)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory for .qmd files (default: same as --input)",
    )
    parser.add_argument(
        "--class-report", action="store_true", help="Generate class_report.qmd"
    )
    parser.add_argument(
        "--group-reports", action="store_true", help="Generate groups/*.qmd"
    )
    parser.add_argument("--all", action="store_true", help="Generate everything")
    parser.add_argument(
        "--sort-features-by",
        default="success",
        choices=["success", "name"],
        help="Sort features by success rate or name (default: success)",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    input_dir = args.input
    output_dir = args.output or input_dir

    if not os.path.isdir(input_dir):
        print(f"ERROR: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    groups = load_groups(input_dir)
    if not groups:
        print(
            f"ERROR: No group JSON files found in {input_dir}/groups/", file=sys.stderr
        )
        sys.exit(1)

    print(f"Loaded {len(groups)} groups from {input_dir}/groups/")

    do_class = args.class_report or args.all
    do_groups = args.group_reports or args.all

    if not do_class and not do_groups:
        print("Nothing to generate. Use --class-report, --group-reports, or --all.")
        sys.exit(0)

    if do_class:
        generate_class_report(input_dir, output_dir, groups, args.sort_features_by)

    if do_groups:
        generate_group_reports(input_dir, output_dir, groups)


if __name__ == "__main__":
    main()
