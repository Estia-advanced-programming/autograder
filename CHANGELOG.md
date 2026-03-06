## v2.1.0 (2026-03-06)

### Feat

- handle multiple files in the testSuite.json
- implement a feature whitelist to prevent feature bleeding in final evaluation
- **classGrade**: enhance md table with shorter team name
- **classGrader**: handle invalid test suit gracefully
- handle validation failure from autograder
- **autograder**: check and correct missing test id
- **classGrader**: create a class grader script
- **autograder**: handle pandora and testSuite root path separately --test-dir and -P

### Fix

- fix bug in md output when multiple file present in a test
- handle malformated json

## v2.0.0 (2026-03-05)

### Feat

- **install**: add an install script
- **completion**: add completion script
- **autograder**: add file checking, parameter and metadata handling, timeout configuration improve output handling

## v1.1.0 (2026-03-04)

### Feat

- **autograder**: add reporting at feature level before test level
- add color to the test output
- add a debug flag
- put code coverage behind a flag

### Refactor

- **autograder**: standardize command generation with command builder
- **autograder**: move debug and codecoveage to globals
