# Coding Prompt Template

You are my coding assistant.

## Goal
Implement the requested change with minimal, focused edits.

## Context
- Project: {{project_name}}
- Task: {{task_description}}
- Relevant files: {{files}}
- Constraints: {{constraints}}

## Instructions
- Inspect the smallest set of files needed to understand the behavior.
- Prefer new files or isolated extension points over edits to framework-owned code.
- Avoid adding dependencies unless explicitly approved.
- Preserve existing style and naming conventions.
- Do not expose secrets or hardcode credentials.
- Validate the change with the cheapest useful check.

## Output
Provide:
1. What changed
2. Files touched
3. Validation performed
4. Remaining risks
5. Suggested next step