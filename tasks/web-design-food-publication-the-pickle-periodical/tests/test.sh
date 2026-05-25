#!/bin/bash
set -e

cd /tests

# Run the grader (stderr merged so judge failures appear in test output)
/opt/grader-venv/bin/python grader.py \
    --reference /tests/reference_screenshots \
    --submission /app \
    --meta /tests/task_meta.json \
    --output /logs/verifier/reward.json \
    2>&1

echo "Grading complete. Results:"
cat /logs/verifier/reward.json
