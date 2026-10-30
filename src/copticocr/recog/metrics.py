"""Character error rate."""


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def cer(refs: list[str], hyps: list[str]) -> float:
    """Edits needed to turn the hypotheses into the references, per reference character."""
    errors = sum(edit_distance(r, h) for r, h in zip(refs, hyps))
    return errors / max(1, sum(len(r) for r in refs))
