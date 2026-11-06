from textkit.core import char_count, run, word_count


def test_word_count():
    assert word_count("a b  c") == 3


def test_char_count():
    assert char_count("ab c") == 4


def test_run():
    assert run("words", "x y") == 2
