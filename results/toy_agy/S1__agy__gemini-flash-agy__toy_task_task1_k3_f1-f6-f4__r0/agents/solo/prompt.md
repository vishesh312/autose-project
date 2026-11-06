You are working fully autonomously in a non-interactive environment. No human is available: nobody will answer questions, approve actions, or review intermediate output.
- Never ask for clarification or confirmation. If something is ambiguous, use your best judgement, note your assumption in one line, and continue.
- The repository is at /var/folders/3q/2m8v425s7p39t7qxjp0kcdw80000gn/T/parbench-host-zgufocm3/repo. Make all changes there.
- You may read any file and run the project's existing tests and tools. Do not access the network unless installing a missing dependency is unavoidable.
- Leave your changes in the working tree (committing is optional). Do not modify or delete existing tests unless the task requires it.
- Stop once the task is fully implemented.

You have 3 tasks to implement in this repository. Implement all of them yourself, one after another; the final code must satisfy every task at the same time.

### Task 1

**Title**: Add a `lines` operation

**Description**: Add a `line_count(text)` function to `textkit/core.py` that returns the number of lines in the text. A trailing newline must not count as an extra line (`"a\nb\n"` has 2 lines, `""` has 0). Register it in `OPERATIONS` under the name `"lines"` so that `textkit lines FILE` works from the CLI.

### Task 2

**Title**: Ignore punctuation-only tokens in word counts

**Description**: Change `word_count` in `textkit/core.py` so that whitespace-separated tokens containing no letter or digit (such as `"--"` or `"..."`) are not counted as words. `"hello -- world ..."` has 2 words; `"it's 2 o'clock"` still has 3.

### Task 3

**Title**: Read from standard input when the file is `-`

**Description**: In `textkit/cli.py`, when the FILE argument is `-`, read the text from standard input instead of opening a file. Update the argument's help text to say so. Behaviour for real file paths is unchanged.
