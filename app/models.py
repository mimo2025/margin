"""The JSON contracts shared by validation, storage, and API responses."""

from pydantic import BaseModel, ConfigDict, Field

MAX_QUERY_LENGTH = 1_000
MAX_REPLACEMENT_LENGTH = 10_000
MAX_RESULTS = 100
MAX_CONTEXT_CHARS = 200


class ApiModel(BaseModel):
    # Reject misspelled fields and coercions such as true -> 1 for an offset.
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class DocumentSummary(ApiModel):
    id: str
    title: str
    version: int = Field(default=1, ge=1)


class Document(DocumentSummary):
    text: str


class Target(ApiModel):
    """Python string indices: start inclusive, end exclusive."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)


class EditRequest(ApiModel):
    expected_version: int = Field(ge=1)
    target: Target
    replacement: str = Field(max_length=MAX_REPLACEMENT_LENGTH)


class SearchMatch(ApiModel):
    document_id: str
    title: str
    version: int
    target: Target
    context_before: str
    context_after: str


class SearchResponse(ApiModel):
    matches: list[SearchMatch]
    truncated: bool


class ErrorResponse(ApiModel):
    error: str
    code: int
