"""Single-process, in-memory storage with atomic per-document edits."""

from collections.abc import Iterable
from threading import Lock

from app.core import DocumentError, iter_matches, replace_target
from app.models import (
    MAX_CONTEXT_CHARS,
    MAX_QUERY_LENGTH,
    MAX_RESULTS,
    Document,
    DocumentSummary,
    EditRequest,
    SearchMatch,
    SearchResponse,
)


class DocumentStore:
    def __init__(self, documents: Iterable[Document]):
        self._documents: dict[str, Document] = {}
        self._locks: dict[str, Lock] = {}
        for document in documents:
            if document.id in self._documents:
                raise ValueError("Document IDs must be unique.")
            self._documents[document.id] = document
            # The lock survives snapshot replacement; documents cannot be added/deleted.
            self._locks[document.id] = Lock()

    def _lock_for(self, document_id: str) -> Lock:
        try:
            return self._locks[document_id]
        except KeyError:
            raise DocumentError("Document not found.", 404) from None

    def get(self, document_id: str) -> Document:
        with self._lock_for(document_id):
            return self._documents[document_id]

    def list_documents(self) -> list[DocumentSummary]:
        summaries = []
        for document_id in self._documents:
            document = self.get(document_id)
            summaries.append(
                DocumentSummary(id=document.id, title=document.title, version=document.version)
            )
        return summaries

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        limit: int = 50,
        context_chars: int = 60,
    ) -> SearchResponse:
        if not 1 <= len(query) <= MAX_QUERY_LENGTH:
            raise DocumentError(f"Query must contain 1–{MAX_QUERY_LENGTH} characters.", 422)
        if not 1 <= limit <= MAX_RESULTS:
            raise DocumentError(f"Limit must be between 1 and {MAX_RESULTS}.", 422)
        if not 0 <= context_chars <= MAX_CONTEXT_CHARS:
            raise DocumentError(f"Context must be between 0 and {MAX_CONTEXT_CHARS} characters.", 422)

        ids = [document_id] if document_id is not None else self._documents
        matches: list[SearchMatch] = []
        for current_id in ids:
            snapshot = self.get(current_id)
            # Search outside the lock: immutable snapshots remain valid during a save.
            for match in iter_matches(snapshot, query, context_chars=context_chars):
                if len(matches) == limit:
                    return SearchResponse(matches=matches, truncated=True)
                matches.append(match)
        return SearchResponse(matches=matches, truncated=False)

    def edit(self, document_id: str, request: EditRequest) -> Document:
        with self._lock_for(document_id):
            current = self._documents[document_id]
            # Check version before validations that depend on the current content.
            if request.expected_version != current.version:
                raise DocumentError("Document version has changed. Search again before saving.", 409)
            updated_text = replace_target(current.text, request.target, request.replacement)
            updated = Document(
                id=current.id,
                title=current.title,
                text=updated_text,
                version=current.version + 1,
            )
            self._documents[document_id] = updated
            return updated
