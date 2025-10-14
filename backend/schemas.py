from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    arxiv_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    affiliations: List[str] = Field(
        default_factory=list,
        serialization_alias="affiliations",
        validation_alias="author_affiliations",
    )
    abstract: str
    summary: str | None = None
    summary_model: str | None = None
    summary_language: str | None = None
    categories: List[str] = Field(default_factory=list)
    link: str
    pdf_url: str | None = None
    published_at: datetime
    updated_at: datetime
    last_summarized_at: datetime | None = None

    @field_validator("authors", mode="before")
    @classmethod
    def _parse_authors(cls, value: List[str] | str | None) -> List[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [item.strip() for item in value.split(";") if item.strip()]

    @field_validator("categories", mode="before")
    @classmethod
    def _parse_categories(cls, value: List[str] | str | None) -> List[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("affiliations", mode="before")
    @classmethod
    def _parse_affiliations(cls, value: List[str] | str | None) -> List[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [item.strip() for item in value.split(";") if item.strip()]

    @field_serializer("authors")
    def _serialize_authors(self, authors: List[str]) -> List[str]:
        return authors

    @field_serializer("categories")
    def _serialize_categories(self, categories: List[str]) -> List[str]:
        return categories

    @field_serializer("affiliations")
    def _serialize_affiliations(self, affiliations: List[str]) -> List[str]:
        return affiliations


class PaginatedPapers(BaseModel):
    items: List[PaperOut]
    total: int


class RefreshResponse(BaseModel):
    fetched: int
    created: int
    summarized: int
