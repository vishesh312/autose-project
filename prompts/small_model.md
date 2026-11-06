Working rules (follow strictly):
1. Do NOT use git at all: no branches, no commits, no config. Do NOT create notes, tracking or helper files (nothing under .opencode, no AGENTS.md, no scratch files in or outside the repo).
2. Work in this order: (a) find the one or two source files the task names, with a single grep or ls; (b) read them with the read tool; (c) change them with the edit tool, writing real code; (d) run the relevant existing tests once with the project's test runner (python -m pytest <file> -x -q) and fix any failure you caused.
3. Edit the existing source files directly. Never just describe a change in text; it only counts if it is in a file.
4. Keep every tool call purposeful. If two calls in a row return nothing useful, change approach and start editing.
5. When all tasks are implemented in the files, stop with a one-line summary.
