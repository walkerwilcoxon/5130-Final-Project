

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
* To run performance/stress testing, install pytest-benchmark in venv, then run:
    ```bash
    python run_pytest_benchmark.py
    ```
* To run static analysis, install pylint in venv, then run:
    ```bash
    python run_pylint.py
    ```
<!-- * To run the CodeQL analysis, execute the following command in the terminal:
    ```bash
    codeql database create codeql-db --language=python --source-root=.
    codeql query run example_query.ql --database=codeql-db 
    ``` -->

# Automated Test Case Generation

```bash
pytest --cov=myprog --cov-report=term --cov-report=html
```
# Program Dependency Graphs

We use [Joern](https://docs.joern.io/frontends/python/) on Python code to export PDGs.

## Install

```bash
# Install Joern
mkdir joern && cd joern
curl -L "https://github.com/joernio/joern/releases/latest/download/joern-install.sh" -o joern-install.sh
chmod u+x joern-install.sh
./joern-install.sh --interactive



# Install Java and Graphviz
sudo apt update
sudo apt install default-jdk graphviz

# If you don't have sudo permission, I installed them with anaconda/miniconda
conda install -c conda-forge openjdk 
conda install -c conda-forge graphviz
```

## Parse a Python project

```bash
mkdir $PROJ_DIR
cp json_parser.py $PROJ_DIR # put the python code under a project dir

joern-parse $PROJ_DIR --language PYTHONSRC
joern-export --repr pdg --out $OUTPUT_DIR # output .dot files are saved at $OUTPUT_DIR

bash pdg/draw_pdg.sh # render dot files to pvg files.
```