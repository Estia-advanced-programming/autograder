## v3.1.2 (2026-03-13)

### Fix

- skip tests where file is an array instead of a single file
- handle "options" in addition to "option" in testSuite

## v3.1.1 (2026-03-13)

### Fix

- forcing encoding utf-8 for python autograder (#5)
- **autograder**: escape metadata value on the cli

## v3.1.0 (2026-03-13)

### Feat

- **converter**: convert file to imperial

### Fix

- count missing test as always incorrect for test quality
- remove blank lines breaking the report tables
- protect against non existant breach_coverage
- run the autograder command from the student repository
- report teacher score and not total score
- filter missing result tests

## v3.0.0 (2026-03-12)

### BREAKING CHANGE

- major refactoring

### Feat

- separate evaluation from reporting

### Refactor

- **grader**: separate compute from render, add commit analysis and coverage

## v2.3.0 (2026-03-11)

### Feat

- **classGrader**: improve table readibily
- **updateGroups**: pull and compile student code from the cli
- parallelize test execution, improve report readability

## v2.2.0 (2026-03-10)

### Feat

- **classGrader**: put different evaluation phase behind flags
- **classGrader**: tally feature and tests
- **autograder**: tally validated tests
- **autograder**: tally validated feature
- **testManager**: handle group at the root level
- **testsManager**: add integration test samples and fix entry-level mode override (Phase 7)
- **testsManager**: add file-reference and duplicate checks (Phase 6)
- **testsManager**: add list command (Phase 5)
- **testsManager**: add build command with ID allocation (Phase 4)
- **testsManager**: add profile resolution (Phase 3)
- **testsManager**: add expansion engine (Phase 2)
- **testManager**: add yaml loading and validation
- **testManager**: add scafolding for the testManager (CLI, file opening)
- **autograder**: add a group option to tests in the testSuite
- **classGrader**: add a dry run option to the class grader
- **classGrader**: read options from config.yml

### Fix

- update teacher testsuite to the local one
- **autograder**: check pandora version in lower case

## v2.1.1 (2026-03-06)

### Fix

- handle pandora version of the format Pandora@X.X.X
- read correct category for parameter test

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
