"""HTTP boundary: validate requests, delegate to the store, serialize responses."""

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core import DocumentError
from app.models import (
    MAX_CONTEXT_CHARS,
    MAX_QUERY_LENGTH,
    MAX_RESULTS,
    Document,
    DocumentSummary,
    EditRequest,
    ErrorResponse,
    SearchResponse,
)
from app.sample_data import sample_documents
from app.store import DocumentStore


def create_app(store: DocumentStore | None = None) -> FastAPI:
    # A factory gives every test its own state, without resetting global fixtures.
    documents = store if store is not None else DocumentStore(sample_documents())
    api = FastAPI(
        title="Margin",
        version="0.1.0",
        description="Search and precisely edit fictional contracts. Single-process prototype.",
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )

    @api.exception_handler(DocumentError)
    async def document_error(_request: Request, exc: DocumentError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc), "code": exc.status_code})

    @api.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not include Pydantic's raw input/body in the error response.
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        return JSONResponse(
            status_code=422,
            content={"error": f"Invalid request at {location}: {first['msg']}", "code": 422},
        )

    @api.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc.detail), "code": exc.status_code},
            headers=exc.headers,
        )

    @api.exception_handler(Exception)
    async def unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": "Internal server error.", "code": 500})

    @api.get("/documents", response_model=list[DocumentSummary])
    def list_documents() -> list[DocumentSummary]:
        return documents.list_documents()

    # Keep this static path above /documents/{document_id}.
    @api.get("/documents/search", response_model=SearchResponse)
    def search_documents(
        q: str = Query(min_length=1, max_length=MAX_QUERY_LENGTH),
        document_id: str | None = Query(default=None, min_length=1),
        limit: int = Query(default=50, ge=1, le=MAX_RESULTS),
        context_chars: int = Query(default=60, ge=0, le=MAX_CONTEXT_CHARS),
    ) -> SearchResponse:
        return documents.search(q, document_id=document_id, limit=limit, context_chars=context_chars)

    @api.get("/documents/{document_id}", response_model=Document)
    def get_document(document_id: str) -> Document:
        return documents.get(document_id)

    @api.patch("/documents/{document_id}", response_model=Document)
    def edit_document(document_id: str, request: EditRequest) -> Document:
        return documents.edit(document_id, request)

    return api


app = create_app()
