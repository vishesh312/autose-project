${preamble}

You have ${k} tasks to implement in this repository. You are the lead: decide how to divide the work among subagents (e.g. one per task, or grouping tasks that touch the same code). Have each subagent work in its own git worktree and branch (e.g. `git worktree add /tmp/wt-N -b task-N`), so they do not edit the same files at the same time. When they finish, merge their branches into /workspace/repo yourself, resolve any conflicts, and make sure the final working tree of /workspace/repo satisfies every task at the same time. Remove the extra worktrees when done.

${tasks}
