You are working fully autonomously in a non-interactive environment. No human is available: nobody will answer questions, approve actions, or review intermediate output.
- Never ask for clarification or confirmation. If something is ambiguous, use your best judgement, note your assumption in one line, and continue.
- The repository is at /var/folders/3q/2m8v425s7p39t7qxjp0kcdw80000gn/T/parbench-host-5rzdrpj_/repo. Make all changes there.
- You may read any file and run the project's existing tests and tools. Do not access the network unless installing a missing dependency is unavoidable.
- Leave your changes in the working tree (committing is optional). Do not modify or delete existing tests unless the task requires it.
- Stop once the task is fully implemented.

You have 2 tasks to implement in this repository. Implement all of them yourself, one after another; the final code must satisfy every task at the same time.

### Task 1

**Title**: Add a `--json` output flag to the CLI

**Description**: Add a `--json` flag to `textkit` (`textkit/cli.py`). When given, print a single JSON object `{"op": <operation name>, "result": <result>}` instead of the plain result. Without the flag, output is unchanged.

### Task 2

**Title**: Add a `slugify` helper

**Description**: Add a new module `textkit/slug.py` with a function `slugify(text, sep="-")` that lowercases the text, replaces every run of characters that are not ASCII letters or digits with `sep`, and strips leading/trailing separators. Example: `slugify("  Hello, World!! ")` returns `"hello-world"`, and `slugify("A B", sep="_")` returns `"a_b"`.
