from parbench.runner import _union_s


def test_union_of_agent_intervals():
    assert _union_s([]) == 0
    assert _union_s([(0, 10), (20, 25)]) == 15  # S0 one after another: setup gap not counted
    assert _union_s([(0, 10), (2, 12), (3, 5)]) == 12  # S2 in parallel: overlap counted once
