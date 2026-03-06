# Feature Whitelist

## Overview

A feature whitelist system has been added to `autograder.py` and `class_grader.py` to prevent "feature bleeding" from manifests and test suites. The whitelist is stored in a shared JSON file (`features-whitelist.json`) that both scripts load at startup.

If the whitelist file is not found, **all features are allowed** (backward compatible mode).

## Configuration File

The whitelist is defined in `features-whitelist.json` located in the same directory as the grader scripts. The file has three sections:

```json
{
  "features": [ ... ],        // Allowed feature names
  "parameters": [ ... ],       // Allowed parameter names  
  "metadata_allowed": [ ... ]  // Allowed metadata field names
}
```

### Features vs Parameters

- **Features**: Data analysis outputs that the Pandora application can compute (e.g., `avgAlt`, `flightDuration`, `takeOff`)
- **Parameters**: Configuration options that control how Pandora processes data (e.g., `number`, `metric`, `imperial`)
- **Metadata**: Specific metadata fields Pandora can extract (e.g., `flight_id`, `origin`, `date`)

## Implementation

### Validation Points

1. **Manifest Validation**: When loading a manifest file, features are validated against the whitelist
2. **Test Suite Validation**: Features, parameters, and metadata in test suites are validated separately
3. **Check Mode**: The `--check` flag validates all features and reports errors

### Warning Output

- **Normal execution**: Invalid features trigger warnings to **stderr** (won't break JSON output)
- **Check mode** (`--check`): Invalid features cause validation errors and non-zero exit

### Backward Compatibility

If `features-whitelist.json` is not found:
- Both graders operate in permissive mode
- All features/parameters/metadata are allowed
- No validation warnings are generated

This ensures existing setups without the whitelist file continue to work.

## Usage

No changes to command-line usage are required. The validation happens automatically when `features-whitelist.json` exists:

```bash
# Regular grading with feature validation
python3 autograder.py -t tests.json -m manifest.json pandora.jar

# Check mode to validate without running tests
python3 autograder.py --check -t tests.json -m manifest.json pandora.jar

# Class grading with feature validation
python3 class_grader.py -d submissions/ -t teacher_tests.json -r reference.jar
```

## Warning Examples

If invalid features are detected during normal execution, warnings go to stderr:
```
WARNING: Manifest contains invalid features that will be ignored:
  - invalidFeature1
  - anotherBadFeature
```

During `--check` mode, errors go to stdout and cause non-zero exit:
```
ERROR: Manifest contains invalid features: invalidFeature1, anotherBadFeature
ERROR: Test suite contains invalid features: unknownParam
```

## Maintaining the Whitelist

To add new features to the whitelist, edit `features-whitelist.json`:

```json
{
  "features": [
    "existingFeature1",
    "newFeatureName"
  ],
  "parameters": [
    "number",
    "metric"
  ],
  "metadata_allowed": [
    "flight_id",
    "new_metadata_field"
  ]
}
```

The file is loaded once at script startup. After editing, no code changes are needed—just run the graders normally.
