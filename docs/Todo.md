# todo 

- [x] update class_grader to optionnaly take a yml configuration file instead of command line options
- [ ] test error properly handled in class_grader 

## improve report 

We should have a template for the report that can be filled by the classGrader. 
We use Quarto to display the report in the end.  
THe report should be a single page with all the information about the grading of the students.
The report should be full page 

```
format: 
  html:
    page-layout: full
```

The table should span the full page, be stripped and have hover effect, borderless, responsive. 
the all should have a caption. 
The summary should be primary.


## Documentation of pipe table syntax

```md
| Default | Left | Right | Center |
|---------|:-----|------:|:------:|
| 12      | 12   |    12 |   12   |
| 123     | 123  |   123 |  123   |
| 1       | 1    |     1 |   1    |

: Demonstration of pipe table syntax
```

Using Bootstrap classes
Bootstrap table classes given as attributes next to a table caption are inserted into the <table> element. The classes permitted are those that apply expressly to the entire table, and these are: "primary", "secondary", "success", "danger", "warning", "info", "light", "dark", "striped", "hover", "active", "bordered", "borderless", "sm", "responsive", "responsive-sm", "responsive-md", "responsive-lg", "responsive-xl", "responsive-xxl". For example, the following Markdown table will be rendered with row stripes and the rows will also be highlighted on hover:

```md
| fruit  | price  |
|--------|--------|
| apple  | 2.05   |
| pear   | 1.37   |
| orange | 3.09   |

: Fruit prices {.striped .hover}
```


 - add rows to the observable table. remove the non observable table. 
 - change the ```.column-screen-inset``` to ```.column-screen-inset .dense-table```
 - put the teacher score and the test quality first both a percentage, then commit quality, then the rest
 - rename the file to grade_2026.qmd. have a section to look at the groups reports
 - [x] the total score from the autograder should not be normalized.. it should be the raw score.
- remove thecreation of the valid test suitem count the number of valid tests but do not create a new testSUite_cleaned
- check why the mass have quotes
- add in the autograder the capacity to select the test to run by test id, feature, metadata, option.

- [ ] Correct the flight distance test 4, 5 
- Invincible penguin : 
    - ERROR: Manifest contains invalid features: version, help, parameter, unit, batch, debug
    - ERROR: Test suite contains invalid features: parameters, version
- commit number wrong for the invincible penguin, 
- write the error correctly
- Ethereal : Maybe issue with my cleaned test suite, I will check that.
- mvn clean before package to be sure to have a clean build.


```{=html}
<style>
.dense-table table thead th:not(:first-child) {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    vertical-align: bottom;
    padding: 0.2em 0.5em;
    min-height: 150px;
    white-space: nowrap;
}
.dense-table table thead th:first-child {
    writing-mode: horizontal-tb;
    text-align: left;
}
</style>
```

