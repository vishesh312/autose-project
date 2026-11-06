You are working fully autonomously in a non-interactive environment. No human is available: nobody will answer questions, approve actions, or review intermediate output.
- Never ask for clarification or confirmation. If something is ambiguous, use your best judgement, note your assumption in one line, and continue.
- The repository is at /var/folders/3q/2m8v425s7p39t7qxjp0kcdw80000gn/T/parbench-host-nj3gokka/repo. Make all changes there.
- You may read any file and run the project's existing tests and tools. Do not access the network unless installing a missing dependency is unavoidable.
- Leave your changes in the working tree (committing is optional). Do not modify or delete existing tests unless the task requires it.
- Stop once the task is fully implemented.

## Task

# feat: add detailed logging for route pattern handling

**Description:**

Adds detailed debug-level logging for route pattern handling to make debugging easier and to provide more transparency into how patterns are parsed and processed.

- Adds logging infrastructure for pattern handling in `Handle` and `HandleFunc`
- Logs pattern parsing information including method detection
- Integrates with existing logging mechanism

## Public API

```go
// Turns on debug-level logging; off by default.
func EnableDebugLogging()
```

## Issue Context:

Developers have reported difficulty debugging route handling issues, particularly with complex patterns or when methods are involved. This change provides more visibility into the pattern handling process.
