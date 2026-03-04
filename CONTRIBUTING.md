# Contributing to FlagFoundry

FlagFoundry improves with more training data, better challenge coverage, and community-contributed exploits. Here's how to contribute.

## Training Data

### CTF Writeups
Submit writeups via `data/community/writeups/` in the structured format:

```json
{
  "challenge": { "title": "...", "category": "web", "description": "..." },
  "reasoning": ["Step 1: ...", "Step 2: ..."],
  "exploit": "import requests\n...",
  "flag": "FLAG{...}"
}
```

Guidelines:
- Only include challenges from competitions you participated in or that are publicly documented
- Exploit code must be original or properly attributed
- No writeups for unreleased/private CTF challenges

### Novel Challenge Contributions
If you have challenge ideas, use `synthesis/challenge_generator.py --interactive` to generate a structured challenge package, then submit via PR.

## FlagBench Contributions

Add new evaluation challenges to FlagBench:
1. Create a Docker container for the challenge in `evaluation/challenges/`
2. Verify the challenge has a unique, extractable flag
3. Add an entry to `evaluation/flagbench_manifest.json`
4. Test: `python evaluation/flagbench.py --challenge your_challenge_id`

## Code Contributions

- All contributed code must pass `bash scripts/check_env.sh`
- Follow the code style in existing files (type annotations, docstrings required)
- Agent code: follow the pattern in `agents/web_exploit_agent.py`
- Tests: `python -m pytest tests/`

## Reporting Issues

Use GitHub Issues with:
- `[category]` tag for category-specific bugs (e.g., `[pwn]`, `[crypto]`)
- `[benchmark]` tag for FlagBench evaluation failures
- Minimal reproducible example where possible

## Code of Ethics

FlagFoundry is for CTF competition learning and research. All contributions must be made in this spirit. Do not contribute exploits for unreleased CVEs, private systems, or any non-CTF infrastructure.
