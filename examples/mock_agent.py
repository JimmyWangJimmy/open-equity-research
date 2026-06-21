#!/usr/bin/env python3
"""A deterministic adapter used to test the command-agent contract."""

import json
import sys

task = json.load(sys.stdin)
role = task.get("role", "unknown")
evidence = task.get("context", {}).get("evidence", [])
first_id = evidence[0].get("evidence_id") if evidence else None
result = {
    "summary": f"Mock output for {role}; this is not an analytical model.",
    "claims": [
        {
            "text": "The evidence packet was received.",
            "stance": "neutral",
            "confidence": "low",
            "evidence_ids": [first_id] if first_id else [],
            "limitations": ["Mock adapter only."],
        }
    ],
    "open_questions": ["Connect a reviewed local or hosted model adapter."],
}
json.dump(result, sys.stdout)
