**Title**: Add a `lines` operation

**Description**: Add a `line_count(text)` function to `textkit/core.py` that returns the number of lines in the text. A trailing newline must not count as an extra line (`"a\nb\n"` has 2 lines, `""` has 0). Register it in `OPERATIONS` under the name `"lines"` so that `textkit lines FILE` works from the CLI.
