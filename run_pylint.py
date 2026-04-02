import subprocess
import json
import re

# run pylint and get JSON output
def run_pylint_json(file_path):
    # run pylint with JSON output
    result = subprocess.run(
        ['pylint', '--output-format=json', file_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    pylint_stdout = result.stdout.decode()
    pylint_stderr = result.stderr.decode()

    # parse the JSON output from stdout
    try:
        pylint_output = json.loads(pylint_stdout)
    except json.JSONDecodeError:
        print("Error: Failed to parse JSON output from Pylint.")
        return None, pylint_stdout, pylint_stderr
    
    return pylint_output, pylint_stdout, pylint_stderr

def run_pylint_score(file_path):
    # run pylint without --output-format=json
    result = subprocess.run(
        ['pylint', file_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    
    pylint_stdout = result.stdout.decode()
    pylint_stderr = result.stderr.decode()
    
    # extract the score from the terminal output (stdout)
    score = extract_score_from_stdout(pylint_stdout)
    
    return score, pylint_stdout, pylint_stderr

# extract score from Pylint's stdout
def extract_score_from_stdout(stdout):
    # Regex to match the score in the form "Your code has been rated at X.XX/10"
    score_match = re.search(r'Your code has been rated at (\d+\.\d+)/10', stdout)
    if score_match:
        return float(score_match.group(1))
    return None

# save the JSON report to a file
def save_json(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"Saved to {filename}")

# separate issues by type and save to individual files
def separate_issues_by_type(pylint_output):
    issue_types = ['error', 'warning', 'convention', 'refactor', 'critical']
    separated_issues = {issue_type: [] for issue_type in issue_types}
    
    # categorize issues by type
    for issue in pylint_output:
        issue_type = issue['type']
        if issue_type in separated_issues:
            separated_issues[issue_type].append(issue)
    
    # save each category as a separate JSON file
    for issue_type, issues in separated_issues.items():
        if issues:  # Only save if there are issues of that type
            filename = f"test_results/static_analysis/pylint_{issue_type}_issues.json"
            save_json(issues, filename)

def main(file_path):
    # run pylint and get JSON output
    pylint_output, pylint_stdout_json, pylint_stderr_json = run_pylint_json(file_path)
    
    if pylint_output is None:
        return
    
	# run pylint with no tags
    score, pylint_stdout_score, pylint_stderr_score = run_pylint_score(file_path)

    # print Pylint error
    if pylint_stderr_json or pylint_stderr_score:
        print(f"Pylint error: {pylint_stderr_json or pylint_stderr_score}")
    
    # separate the issues by type and save them to individual JSON files
    separate_issues_by_type(pylint_output)
    
	# add the score to the Pylint output
    if score is not None:
        print(f"Pylint Score: {score}/10")
        # add the score to the JSON report
        pylint_output.append({'score': score})
    else:
        print("Pylint Score not found in the output.")
        
	# save the full pylint JSON report
    save_json(pylint_output, 'test_results/static_analysis/pylint_full_report.json')

if __name__ == "__main__":
    main('course_management_system.py')