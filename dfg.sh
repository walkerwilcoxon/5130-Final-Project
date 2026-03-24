#!/bin/bash
set -euo pipefail

# Usage:
#   ./generate_python_dataflow.sh <codeql_bin> <source_root> <query_ql> <output_dir>
#
# Example:
#   ./generate_python_dataflow.sh \
#       ~/codeql/codeql \
#       ~/my_python_project \
#       ~/queries/PyDataFlow.ql \
#       ./codeql-python-out

if [[ $# -ne 4 ]]; then
    echo "Usage: $0 <codeql_bin> <source_root> <query_ql> <output_dir>"
    exit 1
fi

CODEQL_BIN="$1"
SOURCE_ROOT="$2"
QUERY_FILE="$3"
OUTPUT_DIR="$4"

DB_DIR="${OUTPUT_DIR}/db-python"
RESULTS_DIR="${OUTPUT_DIR}/results"
BQRS_FILE="${RESULTS_DIR}/dataflow.bqrs"
CSV_FILE="${RESULTS_DIR}/dataflow.csv"
DOT_FILE="${RESULTS_DIR}/dataflow.dot"

mkdir -p "${OUTPUT_DIR}" "${RESULTS_DIR}"

echo "[1/5] Checking inputs..."
if [[ ! -x "${CODEQL_BIN}" ]]; then
    echo "Error: CodeQL binary not executable: ${CODEQL_BIN}"
    exit 1
fi

if [[ ! -d "${SOURCE_ROOT}" ]]; then
    echo "Error: Source root not found: ${SOURCE_ROOT}"
    exit 1
fi

if [[ ! -f "${QUERY_FILE}" ]]; then
    echo "Error: Query file not found: ${QUERY_FILE}"
    exit 1
fi

echo "[2/5] Creating Python CodeQL database..."
rm -rf "${DB_DIR}"
"${CODEQL_BIN}" database create "${DB_DIR}" \
    --language=python \
    --source-root="${SOURCE_ROOT}"

echo "[3/5] Running query..."
"${CODEQL_BIN}" query run \
    --database="${DB_DIR}" \
    --output="${BQRS_FILE}" \
    "${QUERY_FILE}"

echo "[4/5] Decoding results to CSV..."
"${CODEQL_BIN}" bqrs decode "${BQRS_FILE}" \
    --format=csv \
    --output="${CSV_FILE}"

echo "[5/5] Converting CSV to DOT..."
python3 - "$CSV_FILE" "$DOT_FILE" <<'PY'
import csv
import sys

csv_path = sys.argv[1]
dot_path = sys.argv[2]

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')

with open(csv_path, newline="", encoding="utf-8") as f:
    rows = list(csv.reader(f))

with open(dot_path, "w", encoding="utf-8") as out:
    out.write("digraph DataFlow {\n")
    out.write("  rankdir=LR;\n")

    # Expecting at least 4 columns:
    # src node, src label, dst node, dst label
    for row in rows[1:]:
        if len(row) < 4:
            continue
        src_label = esc(row[1])
        dst_label = esc(row[3])
        out.write(f'  "{src_label}" -> "{dst_label}";\n')

    out.write("}\n")
PY

echo
echo "Done."
echo "Database : ${DB_DIR}"
echo "BQRS     : ${BQRS_FILE}"
echo "CSV      : ${CSV_FILE}"
echo "DOT      : ${DOT_FILE}"
echo
echo "Render with:"
echo "  dot -Tpng ${DOT_FILE} -o ${RESULTS_DIR}/dataflow.png"