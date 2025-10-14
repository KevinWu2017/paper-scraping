from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from .database import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    arxiv_id = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(500), nullable=False)
    authors = Column(Text, nullable=False)
    author_affiliations = Column(Text, nullable=True)
    abstract = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    summary_model = Column(String(100), nullable=True)
    summary_language = Column(String(32), nullable=True)
    categories = Column(String(150), nullable=False)
    link = Column(String(500), nullable=False)
    pdf_url = Column(String(500), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_summarized_at = Column(DateTime(timezone=True), nullable=True)

    def category_list(self) -> list[str]:
        return [item.strip() for item in self.categories.split(",") if item.strip()]

    def author_list(self) -> list[str]:
        return [item.strip() for item in self.authors.split(";") if item.strip()]

    def affiliation_list(self) -> list[str]:
        value = self.author_affiliations or ""
        return [item.strip() for item in value.split(";") if item.strip()]

    def mark_summarized(self, summary: str, model: str, language: str | None = None) -> None:
        self.summary = summary
        self.summary_model = model
        self.summary_language = language
        self.last_summarized_at = datetime.now(timezone.utc)
