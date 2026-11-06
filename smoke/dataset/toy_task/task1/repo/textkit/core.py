"""Core text operations."""


def word_count(text: str) -> int:
    """Number of whitespace-separated words."""
    return len(text.split())


def char_count(text: str) -> int:
    """Number of characters, including whitespace."""
    return len(text)


OPERATIONS = {
    "words": word_count,
    "chars": char_count,
}


def run(op: str, text: str):
    """Apply the named operation to text."""
    if op not in OPERATIONS:
        raise KeyError(f"unknown operation: {op}")
    return OPERATIONS[op](text)
