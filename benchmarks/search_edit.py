"""Run from the project root: uv run python -m benchmarks.search_edit."""

import platform
from statistics import median
from time import perf_counter

from app.core import iter_matches, replace_target
from app.models import Document
from app.store import DocumentStore

RUNS = 7
QUERY = "thirty (30) days"
REPLACEMENT = "sixty (60) days"
DENSE_SPACING = 1024


def measure(label, operation, check):
    """Time only the operation; validate every result after stopping the clock."""
    samples = []
    for run in range(RUNS + 1):
        start = perf_counter()
        result = operation()
        elapsed_ms = (perf_counter() - start) * 1000
        check(result)
        if run > 0:  # Discard the first run as a warm-up.
            samples.append(elapsed_ms)
        del result
    print(
        f"  {label}: median {median(samples):.3f} ms "
        f"(min {min(samples):.3f}, max {max(samples):.3f})"
    )


def benchmark(size_mib: int) -> None:
    size = size_mib * 1024 * 1024
    halfway = size // 2
    # ASCII makes byte and character counts equal. Put matches halfway and at the end.
    text = "a" * halfway + QUERY + "b" * (size - halfway - 2 * len(QUERY)) + QUERY
    document = Document(id="benchmark", title="Synthetic benchmark", text=text)
    assert len(text.encode("utf-8")) == size
    expected_positions = [halfway, size - len(QUERY)]
    expected_text = text[:halfway] + REPLACEMENT + text[halfway + len(QUERY) :]
    def check_sparse(matches):
        assert [match.target.start for match in matches] == expected_positions
        assert all(match.target.text == QUERY for match in matches)
        assert all(match.target.end == match.target.start + len(QUERY) for match in matches)

    def check_absent(matches):
        assert matches == []

    def check_edit(updated):
        assert updated == expected_text
        assert updated.count(QUERY) == 1
        assert updated.endswith(QUERY)
        assert len(updated) == size + len(REPLACEMENT) - len(QUERY)

    print(f"\n{size_mib} MiB ({size:,} ASCII bytes)")
    measure("sparse search (2 matches)", lambda: list(iter_matches(document, QUERY)), check_sparse)
    # Same-length missing query keeps the scanning workload comparable.
    measure(
        "absent search", lambda: list(iter_matches(document, "thirty (31) days")), check_absent
    )
    target = next(iter_matches(document, QUERY)).target
    measure("single edit", lambda: replace_target(text, target, REPLACEMENT), check_edit)

    # A match every KiB makes result construction grow with document size.
    block = QUERY + "x" * (DENSE_SPACING - len(QUERY))
    dense = Document(id="dense", title="Dense benchmark", text=block * (size // DENSE_SPACING))
    assert len(dense.text.encode("utf-8")) == size

    def check_dense(matches):
        assert len(matches) == size // DENSE_SPACING
        for index, match in enumerate(matches):
            assert match.target.start == index * DENSE_SPACING
            assert match.target.end == match.target.start + len(QUERY)
            assert match.target.text == QUERY
            assert len(match.context_before) <= 60
            assert len(match.context_after) <= 60

    measure(
        f"dense search (all {size // DENSE_SPACING:,} matches)",
        lambda: list(iter_matches(dense, QUERY)),
        check_dense,
    )
    store = DocumentStore([dense])

    def check_capped(response):
        assert len(response.matches) == 50
        assert response.truncated is True
        assert [match.target.start for match in response.matches] == [
            index * DENSE_SPACING for index in range(50)
        ]

    measure("dense search (store limit 50)", lambda: store.search(QUERY, limit=50), check_capped)


if __name__ == "__main__":
    print(f"Python {platform.python_version()} | {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}; processor: {platform.processor() or 'unknown'}")
    print(f"One warm-up + {RUNS} measured runs per case; correctness checked every run.")
    print("Core functions and capped store search: no HTTP, JSON, browser, or AI calls.")
    for size_mib in (1, 5, 10, 20):
        benchmark(size_mib)
