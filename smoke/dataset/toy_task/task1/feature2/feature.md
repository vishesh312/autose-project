**Title**: Add a `unique` operation

**Description**: Add a `unique_words(text)` function to `textkit/core.py` that returns the number of distinct whitespace-separated words, compared case-insensitively (`"The the THE cat"` has 2 unique words). Register it in `OPERATIONS` under the name `"unique"` so that `textkit unique FILE` works from the CLI.
