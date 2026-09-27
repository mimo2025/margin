# Search and edit benchmark

From the project root, after installing dependencies with `uv sync`:

```bash
uv run python -m benchmarks.search_edit
```

The script creates synthetic ASCII documents of 1, 5, 10, and 20 MiB in memory.
It reads no contract files and makes no network or AI requests.

## Cases and method

Each size runs five cases:

- **Sparse search:** find two occurrences of `thirty (30) days`, halfway through
  the document and at its end. Consume all results and their context snippets.
- **Absent search:** search the same document for `thirty (31) days`, which does
  not occur. This requires reaching the end without finding a match.
- **Single edit:** replace the first sparse match with `sixty (60) days`, one
  character shorter. Each run starts from the same original document.
- **Dense search:** consume every result from a separate document with one match
  every 1,024 bytes. This produces 1,024–20,480 results as size increases.
- **Capped search:** search that dense document through `DocumentStore.search`
  with a limit of 50, as used by the API. It finds one extra match to confirm
  truncation, then stops. This includes the store's snapshot lock and response
  construction, but not HTTP or JSON serialization.

Each case has one warm-up and seven measured runs using `time.perf_counter`.
Fixture creation and correctness assertions are outside the timed sections.
Every result is checked: match positions/counts, absence, exact edited text with
its second occurrence preserved, or the result cap and truncation flag.
The script reports median, minimum, and maximum elapsed times. ASCII makes byte
and character counts equal; the benchmark is not representative of all Unicode text.

## Recorded local run

Measured September 27, 2026, with CPython 3.12.4 on macOS/Darwin 24.5.0,
arm64 architecture. Each MiB is 1,048,576 bytes. Table values are medians in
milliseconds; rerun the script to see ranges on your machine.

| Size | Sparse search | Absent search | Single edit | Dense, all matches | Dense, limit 50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 MiB | 0.167 | 0.145 | 0.061 | 2.819 | 0.127 |
| 5 MiB | 0.765 | 0.742 | 0.726 | 15.888 | 0.132 |
| 10 MiB | 1.598 | 1.590 | 1.847 | 37.325 | 0.129 |
| 20 MiB | 3.180 | 3.063 | 3.478 | 72.438 | 0.124 |

From 10 to 20 MiB, sparse search grew about 1.99x, absent search 1.93x, edit
1.88x, and uncapped dense search 1.94x. This is consistent with roughly linear
growth over that interval for these inputs, not a proof of universal complexity.
Other intervals vary: the 1 MiB edit is especially fast relative to larger edits.
Allocation, cache effects, garbage collection, and system load can affect timings;
this benchmark does not isolate their individual contributions.

Dense searches take longer because they construct many result objects and
snippets. The capped search stays around 0.12–0.13 ms because it reaches its 51st
match early and stops, regardless of the remaining document length. This does
not make every capped search constant-time: absent or late matches still require
scanning much more text.

These are observations from one local session, not latency guarantees. They do
not measure peak memory, simultaneous users, multiple-document workloads,
HTTP/JSON serialization, browser rendering, or AI latency. Timing thresholds are
not test assertions; correctness failures stop the script, slow timings do not.

## Performance considerations

Search uses Python's `str.find` without an index. The core iterator yields one
match at a time, allowing the API to stop at its result limit. Fully consuming
all matches, as the dense benchmark does, increases both time and result memory.

Editing creates a new string using slices and concatenation. Copying the document
takes time proportional to its length, and temporary strings increase memory
use. The benchmark also retains expected results and fixtures for validation,
so its process memory would not directly represent a single editing request.
The API returns complete edited text, adding serialization and transfer costs
outside these measurements.

Scanning is straightforward for this prototype. An index could help repeated
searches over a larger collection, but must be updated after edits; conventional
word indexes do not directly preserve arbitrary exact substring semantics.
Streaming requires handling matches spanning chunk boundaries and preserving
context and offsets. Neither is implemented here.
