import json
import math
import subprocess
import sys
import getopt
import sys
import time
import os

jacoco_agent = "target/jacocoagent.jar"
enable_coverage = False
enable_debug = False
def score0(s):
    factor = 50
    return math.floor(pow(factor * factor, 1 - abs(s)) / factor) / factor


def levenshtein(s1, s2):
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return 1.0
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
        normalized = previous_row[-1] / len(s1)
    return normalized


def compare_output(output, expected_output):
    # regexp the output /\s*(?:[^:]*:)?\s*(.*)/
    if isinstance(expected_output, int) or isinstance(expected_output, float):
        try:
            actual_output = float(output)
            return score0(abs(actual_output - expected_output))
        except ValueError:
            return 0
    elif isinstance(expected_output, str):
        return 1 - levenshtein(output, expected_output)
    else:
        return 0


def run_command(command):
    global enable_debug
    if enable_debug:
        print("Running command: " + command)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    try:
        output, error = process.communicate(input="", timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        if enable_debug:
            print("Command timed out: " + command )
        return "TIMEOUT"
     # Normalisation des retours à la ligne (Windows, macOS, Linux)
    output = output.decode(errors="replace").replace(
        "\r\n", "\n").replace("\r", "\n")

    # Normalisation des tabulations (`\t`)
    output = output.replace("\t", "    ")  # Convertit tabulation en 4 espaces

    # Reformate pour s'adapter au système d'exploitation courant
    return output.replace("\n", os.linesep).strip()


def filter_tests(tests, implemented_features):
    filtered_tests = []
    for test in tests:
        if test['feature'] in implemented_features:
            test['actual_result'] = ''
            filtered_tests.append(test)
    return filtered_tests


def run_feature_tests(tests, path_to_pandora):
    global jacoco_agent, enable_coverage
    
    for test in tests:
        option = f" {test['option']}" if 'option' in test else ""
        jacoco_arg = f" -javaagent:{jacoco_agent}=destfile=target/jacoco.exec,append=true" if enable_coverage else ""
        command = f"java{jacoco_arg} -Duser.country=US -Duser.language=en -jar {path_to_pandora} -o {test['feature']}{option} {test['file']}"
        output = run_command(command)
        if output == "TIMEOUT":
            test['actual_result'] = 'TIMEOUT'
            test['score'] = 0
            continue
        test['actual_result'] = output
        test['score'] = compare_output(output, test['result'])


def run_full_tests(tests, path_to_pandora):
    global jacoco_agent, enable_coverage
    grouped_tests = {}
    for test in tests:
        key = (test['file'], test.get('option', ''))
        if key not in grouped_tests:
            grouped_tests[key] = []
        grouped_tests[key].append(test)

    for (file, option), tests in grouped_tests.items():
        option_str = f" {option}" if option else ""
        jacoco_arg = f" -javaagent:{jacoco_agent}=destfile=target/jacoco.exec,append=true" if enable_coverage else ""
        command = f"java{jacoco_arg} -Duser.country=US -Duser.language=en -jar {path_to_pandora}{option_str} {file}"
        output = run_command(command)
        output_lines = output.split('\n')

        for test in tests:
            feature = test['feature']
            expected_result = test['result']
            test['actual_result'] = 'key ' + test['feature'] + ': not found'
            test['score'] = 0
            if output == "TIMEOUT":
                test['actual_result'] = 'TIMEOUT'
                test['score'] = 0
                continue
            found = False
            for line in output_lines:
                key = line.partition(':')[0].strip()
                if key == feature:
                    # Extract the actual result from the line
                    found = True
                    actual_result = line.partition(':')[2].strip()
                    test['actual_result'] = actual_result
                    test['score'] = compare_output(
                        actual_result, expected_result)
                    break


def group_tests_by_milestone(tests):
    grouped_tests = {}
    for test in tests:
        milestone = test['milestone']
        if milestone not in grouped_tests:
            grouped_tests[milestone] = []
        grouped_tests[milestone].append(test)
    return grouped_tests


def sort_tests_by_milestone(tests):

    return sorted(tests, key=lambda x: x['milestone'])


def generate_markdown_table(tests):
    markdown = "| id | mode |feature | file | expected result | actual result | score |\n"
    markdown += "|----|------|---------|------|----------------|---------------|-------|\n"
    for test in tests:
        markdown += f"| {test['id']} | {test['mode']} | {test['feature']} | {test['file']} | {
            test['result']} | {test['actual_result']} | {test.get('score', '')} |\n"
    return markdown


def sum_scores(tests):
    total_score = 0
    count = 0
    for test in tests:
        if 'score' in test:
            total_score += test['score']
            count += 1
    if count == 0:
        return 0
    return total_score / count


def main():
    global jacoco_agent, enable_coverage, enable_debug

    test_suite_file = ''
    manifest_file = ''
    path_to_pandora = ''
    output_format = 'md'
    output_path = ''

    try:
        opts, args = getopt.getopt(sys.argv[1:], "t:m:f:o:j:cd", ["coverage", "debug"])
    except getopt.GetoptError:
        print(
            "Usage: python autograder.py -t <path_test_suit> -m <path_manifest> -f <json|md> -o <output_path> -j <jacoco_agent_path> [-c|--coverage] [-d|--debug] <pathToPandora>")
        sys.exit(1)

    for opt, arg in opts:
        if opt == '-t':
            test_suite_file = arg
        elif opt == '-m':
            manifest_file = arg
        elif opt == '-f':
            output_format = arg
        elif opt == '-o':
            output_path = arg
        elif opt == '-j':
            jacoco_agent = arg
        elif opt == '-c' or opt == '--coverage':
            enable_coverage = True
        elif opt == '-d' or opt == '--debug':
            enable_debug = True

    if len(args) != 1:
        print(
            "Usage: python autograder.py -t <path_test_suit> -m <path_manifest> -f <json|md> -o <output_path> -j <jacoco_agent_path> [-c|--coverage] [-d|--debug] <pathToPandora>")
        sys.exit(1)

    path_to_pandora = args[0]

    jacoco_arg = f" -javaagent:{jacoco_agent}=destfile=target/jacoco.exec" if enable_coverage else ""
    command = f"java{jacoco_arg} -jar {path_to_pandora} --version"
    output = run_command(command)
    if enable_debug:
        print(output)
    # For coverage, we need to run at least one command with the jacoco agent if enabled
    if enable_coverage:
        jacoco_arg = f" -javaagent:{jacoco_agent}=destfile=target/jacoco.exec,append=true"
        command = f"java{jacoco_arg} -jar {path_to_pandora} --help" 
        output = run_command(command)

    # Read test suite and manifest
    with open(test_suite_file, 'r') as f:
        test_suite = json.load(f)
    with open(manifest_file, 'r') as f:
        manifest = json.load(f)

    # Extract data from manifest
    implemented_features = [feature
                            for feature in manifest['features']]

    # Filter tests by implemented features
    filtered_tests = filter_tests(test_suite, implemented_features)

    startTime = time.time()
    # Run feature tests
    feature_tests = [
        test for test in filtered_tests if test['mode'] == 'feature']
    run_feature_tests(feature_tests, path_to_pandora)

    # Run full tests
    full_tests = [test for test in filtered_tests if test['mode'] == 'full']
    run_full_tests(full_tests, path_to_pandora)
    stopTime = time.time()

    # Group tests by milestone and sort by milestone
    sorted_tests = sort_tests_by_milestone(filtered_tests)
    grouped_tests = group_tests_by_milestone(sorted_tests)

    # Generate markdown tables for each milestone
    markdown_tables = []
    for milestone, tests in grouped_tests.items():
        markdown_table = generate_markdown_table(tests)
        markdown_tables.append(markdown_table)

    # Sum scores per milestone and total score
    milestone_scores = {milestone: sum_scores(
        tests) for milestone, tests in grouped_tests.items()}
    total_score = sum_scores(filtered_tests)

    features_score = {feature: 0 for feature in implemented_features}
    features_count = {feature: 0 for feature in implemented_features}
    for test in filtered_tests:
        if 'score' in test:
            features_score[test['feature']] += test['score']
            features_count[test['feature']] += 1

    for feature in implemented_features:
        if features_count[feature] > 0:
            features_score[feature] /= features_count[feature]

    # Print or save output based on format and output path
    if output_format == 'json':
        output_data = {
            'milestone_scores': milestone_scores,
            'total_score': total_score,
            'features': implemented_features,
            'features_score': features_score,
            'tests': grouped_tests,
            'time': stopTime - startTime
        }
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(output_data, f)
        else:
            print(json.dumps(output_data, indent=4))
    elif output_format == 'md':
        output_text = ''
        for markdown_table in markdown_tables:
            output_text += markdown_table + '\n\n'
        output_text += "Milestone Scores:\n"
        output_text += str(milestone_scores) + '\n'
        output_text += "Total Score: " + str(total_score)
        if output_path:
            with open(output_path, 'w') as f:
                f.write(output_text)
        else:
            print(output_text)
    else:
        print("Invalid output format. Please choose 'json' or 'md'.")
    # print the total score
    print("Total Score: " + str(total_score))

if __name__ == '__main__':
    main()
