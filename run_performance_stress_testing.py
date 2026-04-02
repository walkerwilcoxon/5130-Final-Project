"""
Note: might have to remove beginning comment from course_management_system.py to work
"""

import json
import subprocess
import sys
from pathlib import Path

# path to result output
json_path = Path("test_results/performance_stress_testing/benchmark_results.json")
summary_path = Path("test_results/performance_stress_testing/benchmark_summary.json")

# run pytest with benchmark
try:
    subprocess.run(
        [sys.executable, "-m", "pytest",
         "performance_stress_testing.py",
         "--benchmark-only",
         f"--benchmark-json={json_path}",
         "--benchmark-storage=none"],
        check=True
    )
except subprocess.CalledProcessError as e:
    print("Pytest failed:", e)
    sys.exit(1)

# remove machine_info and commit_info from json result
if json_path.exists():
    print("Trimming benchmark results...")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data.pop("machine_info", None)
    data.pop("commit_info", None)

    for benchmark in data.get("benchmarks", []):
        benchmark.get("stats", {}).pop("data", None)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"'machine_info' and 'commit_info' removed from {json_path}")
    
	# generate summary sorted by min, max, mean
    benchmarks = data.get("benchmarks", [])

    if benchmarks:
        print("Creating benchmark summary...")

        # metrics to summarize
        metrics = ["min", "max", "mean", "median", "ops", "stddev", "total"]

        summary = {}
        for metric in metrics:
            # create sorted array of dicts with name and value
            summary[metric] = sorted(
                [
                    {"name": b["name"], "value": b["stats"].get(metric)}
                    for b in benchmarks
                    if b.get("stats") and metric in b["stats"]
                ],
                key=lambda x: x["value"] if x["value"] is not None else float("inf")
            )

        # write the JSON summary
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"summary": summary}, f, indent=2)

        print(f"Benchmark JSON summary written to {summary_path}")
        
else:
    print(f"Benchmark JSON file {json_path} not found.")