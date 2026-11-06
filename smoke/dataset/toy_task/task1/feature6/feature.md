**Title**: Ignore punctuation-only tokens in word counts

**Description**: Change `word_count` in `textkit/core.py` so that whitespace-separated tokens containing no letter or digit (such as `"--"` or `"..."`) are not counted as words. `"hello -- world ..."` has 2 words; `"it's 2 o'clock"` still has 3.
