**Title**: Read from standard input when the file is `-`

**Description**: In `textkit/cli.py`, when the FILE argument is `-`, read the text from standard input instead of opening a file. Update the argument's help text to say so. Behaviour for real file paths is unchanged.
