# JSON Schemas

[JSON Schema draft-07](https://json-schema.org/specification-links.html#draft-7) files for all output produced by `class_grader.py`.

## File mapping

| Schema file | Describes |
|---|---|
| [group.schema.json](group.schema.json) | `groups/<group>.json` — combined all-phases output |
| [commits.schema.json](commits.schema.json) | `commits/<group>.json` and `group.commits` |
| [coverage.schema.json](coverage.schema.json) | `coverage/<group>.json` and `group.coverage` |
| [phase_meta.schema.json](phase_meta.schema.json) | `<phase>/_meta.json` (all phases) |
| [teacher_eval_group.schema.json](teacher_eval_group.schema.json) | `teacher_eval/<group>.json` |
| [teacher_eval_summary.schema.json](teacher_eval_summary.schema.json) | `teacher_eval/_summary.json` |
| [validation_group.schema.json](validation_group.schema.json) | `validation/<group>.json` |
| [validation_summary.schema.json](validation_summary.schema.json) | `validation/_summary.json` |
| [cross_testing_group.schema.json](cross_testing_group.schema.json) | `cross_testing/<group>.json` |
| [cross_testing_summary.schema.json](cross_testing_summary.schema.json) | `cross_testing/_summary.json` |
| [commits_summary.schema.json](commits_summary.schema.json) | `commits/_summary.json` |
| [coverage_summary.schema.json](coverage_summary.schema.json) | `coverage/_summary.json` |

See [docs/output_schema.md](../docs/output_schema.md) for a human-readable field reference.
