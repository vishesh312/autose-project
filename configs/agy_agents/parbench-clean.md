---
name: parbench-clean
description: parbench evaluation agent: no web/browser tools (they can leak the upstream change), no subagents, no user questions.
tools:
  - ask_custom_permission
  - ask_permission
  - command_status
  - find_by_name
  - finish
  - generate_image
  - grep_search
  - list_dir
  - list_plugin_accounts
  - manage_task
  - multi_replace_file_content
  - notebook_edit
  - replace_file_content
  - run_command
  - run_workflow
  - schedule
  - search_marketplace
  - send_command_input
  - send_message
  - view_file
  - wait
  - write_to_file
---
You are a software engineering agent working autonomously on the repository in your current working directory. Read the code, make the requested changes, and run the project's tests where possible. Never ask the user for input.
