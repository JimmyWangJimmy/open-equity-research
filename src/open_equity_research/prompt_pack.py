from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .exceptions import ValidationError
from .io_utils import atomic_write_json, load_json, load_jsonl, utc_now_iso


ROLE_INSTRUCTIONS = {
    "fundamental": (
        "Explain the business and financial trajectory using only supplied evidence. Separate observations "
        "from hypotheses. Every material claim must cite one or more evidence_ids."
    ),
    "bear": (
        "Assume the attractive thesis is wrong. Identify the strongest disconfirming explanations, accounting "
        "risks, cyclicality, dilution, leverage, and missing evidence. Do not invent facts."
    ),
    "risk": (
        "Assess data, model, valuation, concentration, liquidity, regulatory, and operational risks. Mark each "
        "item as observed, inferred, or unresolved."
    ),
    "verifier": (
        "Audit proposed claims against the evidence ledger. Reject unsupported claims, over-strong causal "
        "language, mismatched periods, and derived metrics without adequate lineage."
    ),
}


OUTPUT_SCHEMA = {
    "summary": "string",
    "claims": [
        {
            "text": "string",
            "stance": "supportive|adverse|neutral",
            "confidence": "low|medium|high",
            "evidence_ids": ["E-..."],
            "limitations": ["string"],
        }
    ],
    "open_questions": ["string"],
}


def export_prompt_pack(company_dir: Path, company: dict[str, Any]) -> Path:
    evidence = load_jsonl(company_dir / "evidence.jsonl")
    findings = load_jsonl(company_dir / "findings.jsonl")
    claims = load_jsonl(company_dir / "claims.jsonl")
    task_dir = company_dir / "agent_tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    sections = load_json(company_dir / "source_snapshots" / "10k_sections.json", {}) or {}
    compact_context = {
        "company": company,
        "evidence": evidence,
        "deterministic_findings": findings,
        "deterministic_claims": claims,
        "narrative_sections": {key: str(value)[:20_000] for key, value in sections.items()},
        "policy": {
            "no_trade_execution": True,
            "no_buy_sell_rating": True,
            "evidence_ids_required": True,
            "unresolved_items_must_be_explicit": True,
        },
    }
    for role, instructions in ROLE_INSTRUCTIONS.items():
        atomic_write_json(
            task_dir / f"{role}.json",
            {
                "role": role,
                "created_at": utc_now_iso(),
                "instructions": instructions,
                "output_schema": OUTPUT_SCHEMA,
                "context": compact_context,
            },
        )
    return task_dir


def run_command_agents(
    task_dir: Path,
    output_dir: Path,
    command: str,
    roles: Iterable[str] | None = None,
    timeout_seconds: int = 300,
) -> list[Path]:
    """Run an explicitly configured local command once per task.

    The command receives a task JSON document on stdin and must emit one JSON object on stdout.
    It is executed without a shell. Outputs remain untrusted until a verifier or human reviews them.
    """

    arguments = shlex.split(command, posix=os.name != "nt")
    if not arguments:
        raise ValidationError("Agent command is empty")
    selected = list(roles or ROLE_INSTRUCTIONS)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for role in selected:
        task_path = task_dir / f"{role}.json"
        if not task_path.exists():
            raise ValidationError(f"Missing task for role {role}: {task_path}")
        task = load_json(task_path)
        completed = subprocess.run(
            arguments,
            input=json.dumps(task, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise ValidationError(
                f"Agent command failed for {role} with exit code {completed.returncode}: "
                f"{completed.stderr.strip()}"
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Agent output for {role} was not valid JSON: {exc}") from exc
        if not isinstance(result, dict):
            raise ValidationError(f"Agent output for {role} must be a JSON object")
        result["role"] = role
        result["trusted"] = False
        result["generated_at"] = utc_now_iso()
        path = output_dir / f"{role}.json"
        atomic_write_json(path, result)
        written.append(path)
    return written
