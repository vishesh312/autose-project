Do both of these:
1. Add a `lines` operation: `line_count(text)` in textkit/core.py (a trailing newline is not an extra line), registered in OPERATIONS as "lines".
2. Add a `unique` operation: `unique_words(text)` in textkit/core.py (distinct words, case-insensitive), registered in OPERATIONS as "unique".
