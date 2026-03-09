# Tests Manager

This tools help me manage the tests, and generate the testSuite.json file that is used by the autograder to run the tests.

I want to use intermediary files to store the tests, and then generate the testSuite.json file from them. This way, I can easily edit the tests without having to worry about the format of the testSuite.json file.

I think i want my intermediary files to be in yml format, and then use a python script to generate the testSuite.json file from them. This way, I can easily edit the tests in a human-readable format, and then generate the testSuite.json file that is used by the autograder.

the yml should have comment as well to help me understand the tests, and the python script should be able to handle the comments and ignore them when generating the testSuite.json file.