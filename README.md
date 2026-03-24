

# Installation:
Note: Artheris requires Linux so it is recommended to use WSL on Windows.


## Python Dependencies
1. Create a virtual environment:
    ```bash
    python -m venv venv
    ```
2.  Activate the virtual environment:
    ```bash
    source venv/bin/activate
    ```
3. Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## CodeQL
1. Install CodeQL CLI from the official GitHub repository [CodeQL CLI](https://github.com/github/codeql-cli-binaries/releases). You should install the Linux version if you are using WSL.
2. Extract the downloaded archive and add the `codeql` executable to your system's PATH.
3. Open a terminal and run the following command:
    ```bash
    codeql pack install
    ```

# Usage:
* To run the fuzzing tests, execute the following command in the terminal:
    ```bash
    mkdir -p corpus
    python fuzz_json.py corpus/ seed_corpus/
    ```
* To run with coverage reporting, execute the following commands. Once you do, you can open the report by opening `htmlcov/index.html` in a web browser.
    ```bash
    coverage run fuzz_json.py corpus/ seed_corpus/
    coverage report
    coverage html
    ```
<!-- * To run the CodeQL analysis, execute the following command in the terminal:
    ```bash
    codeql database create codeql-db --language=python --source-root=.
    codeql query run example_query.ql --database=codeql-db 
    ``` -->
