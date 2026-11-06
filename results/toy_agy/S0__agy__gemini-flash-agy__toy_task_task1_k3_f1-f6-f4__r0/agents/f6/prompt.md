You are working fully autonomously in a non-interactive environment. No human is available: nobody will answer questions, approve actions, or review intermediate output.
- Never ask for clarification or confirmation. If something is ambiguous, use your best judgement, note your assumption in one line, and continue.
- The repository is at /var/folders/3q/2m8v425s7p39t7qxjp0kcdw80000gn/T/parbench-host-g04hyo9o/repo. Make all changes there.
- You may read any file and run the project's existing tests and tools. Do not access the network unless installing a missing dependency is unavoidable.
- Leave your changes in the working tree (committing is optional). Do not modify or delete existing tests unless the task requires it.
- Stop once the task is fully implemented.

## Task

**Title**: Ignore punctuation-only tokens in word counts

**Description**: Change `word_count` in `textkit/core.py` so that whitespace-separated tokens containing no letter or digit (such as `"--"` or `"..."`) are not counted as words. `"hello -- world ..."` has 2 words; `"it's 2 o'clock"` still has 3.
