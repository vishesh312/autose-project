# Smoke prompts

Run one against the toy pool with a harness + model, e.g.

    parbench probe --toy --harness opencode --model qwen3.5-9b-ollama --prompt-file smoke/prompts/01_read_only.md

Check, in order: the agent used tools (see `tool_calls` in the output), edited the right files, stopped by itself,
and did not ask for human input (`nudges` should be 0, or the nudge text should have been enough).
Prompts 01-04 test basic tool use; 05-06 test autonomy; 07-08 are real toy features (f5 slugify, f3 --json) that can
be graded with `parbench check-gold` style tests; 09 tests a vague request.
