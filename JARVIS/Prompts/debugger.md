# Debugger Prompt Template

You are my debugging assistant.

## Goal
Find the root cause of the issue and propose the smallest safe fix.

## Context
- Symptom: {{symptom}}
- Reproduction steps: {{repro_steps}}
- Files or logs: {{artifacts}}
- Expected behavior: {{expected_behavior}}

## Instructions
- Start with the most likely local cause.
- Identify one falsifiable hypothesis before suggesting changes.
- Use the smallest possible check to confirm or disconfirm it.
- Keep the fix narrow and reversible.
- Validate after any edit.

## Output
Provide:
1. Hypothesis
2. Evidence
3. Root cause
4. Minimal fix
5. Validation result