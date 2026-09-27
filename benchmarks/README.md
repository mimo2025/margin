# Search and edit benchmark

From the project root, after installing dependencies with `uv sync`:

```bash
uv run python -m benchmarks.search_edit
```

This script generates synthetic ASCII documents in memory; it reads no contract
files and makes no network or AI requests. It tests 1 MiB and 10 MiB documents,
each containing `thirty (30) days` twice: halfway through and at the end.

Search consumes all results, including their bounded context snippets. Edit
validates and replaces only the first match with `sixty (60) days`, which is one
character shorter. Every iteration checks the search positions and resulting
text, including preservation of the second occurrence. Each edit starts from
the same original text.

Fixture creation and correctness assertions are outside the timed sections.
Each size has one warm-up and seven measured runs using `time.perf_counter`.
The script reports the median, minimum, and maximum elapsed times.

## Recorded local run

Measured September 27, 2026, with CPython 3.12.4 on macOS/Darwin 24.5.0,
arm64 architecture. Times are milliseconds.

| Document size | Search median (min–max) | Edit median (min–max) |
| --- | --- | --- |
| 1 MiB / 1,048,576 bytes | 0.244 (0.178–0.551) | 0.190 (0.066–0.416) |
| 10 MiB / 10,485,760 bytes | 1.778 (1.581–4.093) | 1.998 (1.646–4.171) |

These are observations from one local session, not a latency guarantee. Your
results will vary with hardware, system load, Python version, text, and query.
Two sizes and one sparse-match workload do not establish a universal complexity
bound. This does not measure dense matches, concurrent requests, memory peaks,
storage locks, HTTP/JSON serialization, browser rendering, or AI latency.

## Performance considerations

Search uses Python's `str.find` to scan text without an index. The core iterator
yields results one at a time; the API stops after its result limit plus one match
to detect truncation. An absent query can still require scanning every document.
Dense matches add result construction costs beyond scanning.

Editing creates a new string using slices and concatenation. Copying the document
takes time proportional to its length, and temporary strings increase memory
use. This benchmark also retains an expected result for correctness checks, so
its process memory would not directly represent the app's editing memory use.
The API returns the complete edited text, adding serialization and transfer costs
that this benchmark deliberately does not measure.

Scanning is straightforward for this small prototype. An index could help repeated
searches across a larger corpus, but would need updating after edits; conventional
word indexes also do not directly preserve arbitrary exact substring semantics.
Streaming would require extra handling for matches spanning chunk boundaries
and for context/offset tracking. Neither is implemented here.
