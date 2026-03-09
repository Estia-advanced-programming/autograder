# Tests Manager

This tools help me manage the tests, and generate the testSuite.json file that is used by the autograder to run the tests.

I want to use intermediary files to store the tests, and then generate the testSuite.json file from them. This way, I can easily edit the tests without having to worry about the format of the testSuite.json file.

I think i want my intermediary files to be in yml format, and then use a python script to generate the testSuite.json file from them. This way, I can easily edit the tests in a human-readable format, and then generate the testSuite.json file that is used by the autograder.

the yml should have comment as well to help me understand the tests, and the python script should be able to handle the comments and ignore them when generating the testSuite.json file.


there are multiple kind of test I want to write : 
- "feature" test : test a specific feature of the project, and check if it is working as expected. For that It should use a specific flight record generated for that feature, and check if the result is as expected. (for that I'll use the flightGenerator to generate the flight records for the feature tests)
- full record test: run the full report on a specific flight record, and check if the result for each feature is as expected. 
- metadata test: test if the metadata of a specific flight record is correct, by querying it with the -m option and checking if the result is as expected.

its important to have full and feature test for the same feature: 
- Student usually start with the -o option and forget to do the full report. 
- My philosoph is that the feature test is on custom built flight records. the full record test is on real flight records.


additionally I want to run : "metric" that run as full report on US flight records, and check if the result for each feature is as expected, but only for a subset of the features that are relevant for the metric. for that I'll use the group option. 

I want to have manageable size yml files so their are not to large, and be able to combine them to produce testSuite.json on the fly to manage my goal.

At the beginning of the class, I need to be able to create a "fast" subset of the features set to quickl test student program and help them get of the ground. being able to check will feature I want to include. 

Later on for the final grade a I want to be able to test more and more challenging files. 

I have "real" test flight and custom build test files. At some point I want to be able to test both. For the custom build it's usually one feature and one specific scenario per file (eg. for flightDistance I have a "rocket" plane that only go up). 
For the full flight I want the yml to look something like that (you may update)

```yml
desc: test metric mode with f35 plane
file: path
option: some option like --metric
group: metric
mode: full 
features: 
  - flightDistance: value
  - feature: value
  ...
metadata: 
  - flight_id: value
```

```yml
desc: test the basic feature
mode: feature 
features: 
  - avgAlt:
    - file: avgAlt1.frd
      value: value
      desc: "rocket"
    - file: avgAlt2.frd
      value: value
      option: something
  - filenames: 
    - files: somePath, somePath2
      value: value 
      desc: "test the filenames feature"
```

```yml
desc: test the metadata
mode: feature 
metatada: mass 
- file: somePath
    value: value
```


```yml
desc: test the basic error
mode: feature 
- features: avgAlt 
    - file: avgAlt1.frd
      value: value
      desc: "rocket"
    - file: avgAlt2.frd
      value: value
      option: something
```

the tool should look at the yml files and ask me which one I want to include in the testSuite.json file, and then generate the testSuite.json file with the selected tests. Or maybe use a specific yml that explain what to include. 

I should make tests for the followin scenario / group : 
- metric / imperial on full report
- make strange valid cases : one line flight record, flight records with the minimal number of columns, with columns in different order
- make test for the errors that should use an "error:" field instead of the "value" as the result will be in stderr 

