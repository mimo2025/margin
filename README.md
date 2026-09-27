# Margin📝

By: Mira Mohan · September 27, 2026

Search fictional contracts and edit one exact occurrence at a time. Write a
replacement yourself or ask AI for a suggestion, review it side by side with the original,
then save. Repeated text elsewhere in the document stays unchanged.

Built with Python, FastAPI, and plain HTML/CSS/JavaScript. Includes three sample
documents; no uploads or database setup required.

## Run locally

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). From the project root:

```bash
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [the app](http://127.0.0.1:8000/) or [interactive API docs](http://127.0.0.1:8000/docs).
Search for `thirty (30) days` to try the repeated-text example.

For AI suggestions, copy `.env.example` to `.env` if you do not already have one,
set `OPENAI_API_KEY` locally, then start the server with:

```bash
uv run --env-file .env uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The key needs API billing/access to the configured model, `gpt-6-luna` in
`app/suggestions.py`. Suggestions make paid OpenAI API calls. The key stays on
the server; never commit `.env`. Manual search and editing work without it.

## API examples

These examples assume a freshly started server, with documents at version 1.
Restarting resets all edits. For existing edits, search again and use the returned
`version` and `target` instead of the example values.

List documents and read one:

```bash
curl -sS http://127.0.0.1:8000/documents
curl -sS http://127.0.0.1:8000/documents/services
```

Find both occurrences in the services agreement. Omit `document_id` to search all documents:

```bash
curl -sS -G http://127.0.0.1:8000/documents/search \
  --data-urlencode 'q=thirty (30) days' \
  --data-urlencode 'document_id=services'
```

Each match includes the document ID, title, version, exact `target`, and context
before and after it. The first target is the payment term at offsets 271–287.

Optionally ask for wording; this does **not** save anything:

```bash
curl -sS http://127.0.0.1:8000/documents/services/suggest \
  -H 'Content-Type: application/json' \
  -d '{"expected_version":1,"target":{"start":271,"end":287,"text":"thirty (30) days"},"instruction":"Change this to sixty days, keeping the number format."}'
```

The response contains `replacement`. Review it, then send an explicit save request:

```bash
curl -sS -X PATCH http://127.0.0.1:8000/documents/services \
  -H 'Content-Type: application/json' \
  -d '{"expected_version":1,"target":{"start":271,"end":287,"text":"thirty (30) days"},"replacement":"sixty (60) days"}'
```

The response contains `id`, `title`, the full updated `text`, and `version: 2`.
Only the payment occurrence changes. Repeating this request returns `409` because
version 1 is stale. An empty replacement deletes the selected text.

## Design and behavior

- **Search:** literal, case-sensitive, non-overlapping matches. Empty queries are
  rejected; no matches returns `{"matches":[],"truncated":false}`. Results default
  to 50 (maximum 100 across documents), with 60 context characters per side
  (maximum 200). `truncated` indicates more matches exist.
- **Targeting:** ranges are start-inclusive, end-exclusive Python Unicode string
  indices, not byte offsets or JavaScript UTF-16 indices. The page sends the
  server's target back unchanged, including when an emoji precedes a match.
- **Saving:** `PATCH` applies a partial edit. The server checks the version,
  range, and original text under a per-document lock, then saves and increments
  the version once. Failed checks leave the document unchanged.
- **AI:** `POST /suggest` sends only the selected text and instruction. It returns
  validated wording, has a configured 15-second SDK timeout and no automatic
  retries, and never saves. No document lock is held during the call. Saving
  afterward checks the version again. Suggestions still need human review.
- **Limits:** queries, targets, and AI instructions are limited to 1,000 characters;
  replacements to 10,000. AI output also has a 512-token cap.

Errors use `{"error":"message","code":409}` with the matching HTTP status:
`404` missing document, `409` stale version or changed target, `422` invalid input,
`502` invalid/incomplete AI response, `503` AI unavailable/unconfigured, `504` AI
timeout, and `500` unexpected server error. Provider error bodies are not exposed.

`app/core.py` handles text operations, `store.py` owns documents and locks,
`main.py` defines routes, and `suggestions.py` handles the model call. The page in
`app/static/` uses the same API; there is no separate frontend build.

## Tests and performance

```bash
uv run pytest -q
uv run ruff check .
uv run python -m benchmarks.search_edit
```

Tests cover exact edits, deletion, boundaries, repeated text, Unicode, conflicts,
API errors, and a 10 MiB document. AI tests use mocks and need no key or network.
A live suggestion with fictional text was also verified manually.

On a local Python 3.12.4 / macOS arm64 run, a 10 MiB ASCII document with two matches
took a median **1.778 ms to search** and **1.998 ms to edit** over seven measured
runs. These measure core functions, excluding HTTP/JSON, rendering, and AI;
they are observations, not latency guarantees. See [benchmark details](benchmarks/README.md).

Search scans text with `str.find`; edits copy text into a new string, so larger
documents cost more time and memory. Returning the full document adds transfer
cost. No index or streaming is implemented. An index could help repeated searches
over a larger collection, but must track edits and support exact substrings.
Streaming would reduce memory needs but complicate matches and context spanning
chunk boundaries.

## Limitations

- **Single edits only:** bulk replacement is not implemented. Each save changes
  one occurrence in one document. A possible extension is to validate and save
  several selected replacements together, rejecting the whole batch if any
  target is invalid.
- **In-memory storage:** edits disappear on restart. Run one server worker;
  locks do not coordinate separate processes. Version numbers detect stale
  edits but do not provide revision history or undo.
- **Search and scale:** no index or streaming; documents are held in memory and
  scanned directly. Search results are capped without pagination. The benchmark
  covers a two-match synthetic workload, not production traffic, peak memory,
  or sustained concurrent load; it does not establish a general scaling guarantee.
- **Review scope:** the page compares the selected text with its replacement;
  it does not produce a full-document redline. AI output is checked for structure,
  not legal correctness or whether it fully follows the instruction.
- **Local demo:** three fictional documents, with no file import, authentication,
  or persistent storage. Production infrastructure is not implemented.
