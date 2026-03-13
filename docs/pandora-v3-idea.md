# Pandora v3 Ideas

THis document is a brainstorming space for ideas to implement in Pandora v3. It is not a specification, but rather a collection of potential features and improvements that could be added to the project in the future.

they concern pandora, not the grading process

# Doc 
- [ ] rename the features to computations
# CLI Option
--full : Trigger the full report
--part=computation, or --computation=... : Trigger a specific computation or a set of computations, multiple --computation are possible
--check: check if flight records are valid (e.g., no missing fields, correct format)
--output : output directory for the report
--format: md, json
--human : add the unit to the output (e.g., 1000m instead of 1000)

# Performance
- Pandora should process a file under 2s. 

# Full Report
md format with sections for collecting the metadata and the computations.
```md
# metadata
...
# Computations
```


# Test suite
Rename the modes : full, partial