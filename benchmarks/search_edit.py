"""Run from the project root: uv run python -m benchmarks.search_edit."""

import platform
from statistics import median
from time import perf_counter

from app.core import iter_matches, replace_target
from app.models import Document

RUNS = 7
QUERY = "thirty (30) days"
REPLACEMENT = "sixty (60) days"


def benchmark(size_mib: int) -> None:
    size = size_mib * 1024 * 1024
    halfway = size // 2
    # ASCII makes byte and character counts equal. Put matches halfway and at the end.
    text = "a" * halfway + QUERY + "b" * (size - halfway - 2 * len(QUERY)) + QUERY
    document = Document(id="benchmark", title="Synthetic benchmark", text=text)
    assert len(text.encode("utf-8")) == size
    expected_positions = [halfway, size - len(QUERY)]
    expected_text = text[:halfway] + REPLACEMENT + text[halfway + len(QUERY) :]
    timings = {"search": [], "edit": []}

    # First iteration warms up the code; the remaining seven are measured.
    for run in range(RUNS + 1):
        start = perf_counter()
        matches = list(iter_matches(document, QUERY))
        search_ms = (perf_counter() - start) * 1000

        assert [match.target.start for match in matches] == expected_positions
        assert all(match.target.text == QUERY for match in matches)
        assert all(match.target.end == match.target.start + len(QUERY) for match in matches)

        start = perf_counter()
        updated = replace_target(text, matches[0].target, REPLACEMENT)
        edit_ms = (perf_counter() - start) * 1000

        # Checks are outside the timed sections. The second occurrence must survive.
        assert updated == expected_text
        assert updated.count(QUERY) == 1
        assert updated.endswith(QUERY)
        assert len(updated) == size + len(REPLACEMENT) - len(QUERY)
        if run > 0:
            timings["search"].append(search_ms)
            timings["edit"].append(edit_ms)
        del updated, matches

    print(f"\n{size_mib} MiB ({size:,} ASCII bytes), 2 matches")
    for operation, samples in timings.items():
        print(
            f"  {operation}: median {median(samples):.3f} ms "
            f"(min {min(samples):.3f}, max {max(samples):.3f})"
        )


if __name__ == "__main__":
    print(f"Python {platform.python_version()} | {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}; processor: {platform.processor() or 'unknown'}")
    print(f"One warm-up + {RUNS} measured runs per size; correctness checked every run.")
    print("Core functions only: no HTTP, JSON, browser, storage lock, or AI calls.")
    for size_mib in (1, 10):
        benchmark(size_mib)
