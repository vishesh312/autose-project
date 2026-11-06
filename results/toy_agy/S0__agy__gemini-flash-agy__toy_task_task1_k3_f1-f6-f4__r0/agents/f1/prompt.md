You are working fully autonomously in a non-interactive environment. No human is available: nobody will answer questions, approve actions, or review intermediate output.
- Never ask for clarification or confirmation. If something is ambiguous, use your best judgement, note your assumption in one line, and continue.
- The repository is at /var/folders/3q/2m8v425s7p39t7qxjp0kcdw80000gn/T/parbench-host-98l2242k/repo. Make all changes there.
- You may read any file and run the project's existing tests and tools. Do not access the network unless installing a missing dependency is unavoidable.
- Leave your changes in the working tree (committing is optional). Do not modify or delete existing tests unless the task requires it.
- Stop once the task is fully implemented.

## Task

**Title**: Add a `lines` operation

**Description**: Add a `line_count(text)` function to `textkit/core.py` that returns the number of lines in the text. A trailing newline must not count as an extra line (`"a\nb\n"` has 2 lines, `""` has 0). Register it in `OPERATIONS` under the name `"lines"` so that `textkit lines FILE` works from the CLI.
