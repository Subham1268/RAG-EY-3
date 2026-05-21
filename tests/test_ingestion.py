"""
tests/test_ingestion.py
────────────────────────
Tests for the document parsing and chunking pipeline.
Uses the actual uploaded EY ME documents where available.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.chunker import DocumentChunker
from ingestion.parser import DocumentParser, ParsedDocument

UPLOADS_DIR = Path("/mnt/user-data/uploads")

# Resolve actual upload filenames
def find_upload(pattern: str) -> Path | None:
    if UPLOADS_DIR.exists():
        matches = list(UPLOADS_DIR.glob(f"*{pattern}*"))
        return matches[0] if matches else None
    return None


# ── Parser tests ──────────────────────────────────────────────────────────────

class TestDocumentParser:
    parser = DocumentParser()

    def test_parse_pdf_aml(self):
        path = find_upload("AML_Framework")
        if not path:
            pytest.skip("Upload not available")
        doc = self.parser.parse(path)
        assert doc.doc_type == "pdf"
        assert len(doc.text_chunks) > 0
        assert any("AML" in c.text or "compliance" in c.text.lower()
                   for c in doc.text_chunks)

    def test_parse_docx_erm(self):
        path = find_upload("ERM_Framework")
        if not path:
            pytest.skip("Upload not available")
        doc = self.parser.parse(path)
        assert doc.doc_type == "docx"
        assert len(doc.text_chunks) > 0
        # Should have heading-based sections
        assert any(c.section_title for c in doc.text_chunks)

    def test_parse_pptx_risk_dashboard(self):
        path = find_upload("Risk_Compliance_Dashboard")
        if not path:
            pytest.skip("Upload not available")
        doc = self.parser.parse(path)
        assert doc.doc_type == "pptx"
        assert len(doc.text_chunks) > 0

    def test_parse_xlsx_risk_register(self):
        path = find_upload("Risk_Register")
        if not path:
            pytest.skip("Upload not available")
        doc = self.parser.parse(path)
        assert doc.doc_type == "xlsx"
        assert len(doc.text_chunks) > 0
        assert len(doc.table_chunks) > 0

    def test_parsed_document_has_metadata(self):
        path = find_upload("AML_Framework")
        if not path:
            pytest.skip("Upload not available")
        doc = self.parser.parse(path)
        assert doc.source_file
        for chunk in doc.text_chunks:
            assert chunk.source_file
            assert chunk.doc_type == "pdf"

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            self.parser.parse(Path("report.csv"))


# ── Chunker tests ─────────────────────────────────────────────────────────────

class TestDocumentChunker:
    parser  = DocumentParser()
    chunker = DocumentChunker(
        chunk_size=800,
        chunk_overlap=150,
        project_metadata={
            "engagement_id": "ME-RC-2023-0089",
            "client":        "Test Bank",
            "country":       "UAE",
            "practice":      "Risk & Compliance",
            "year":          2023,
        },
    )

    def test_chunk_ids_are_deterministic(self):
        path = find_upload("AML_Framework")
        if not path:
            pytest.skip("Upload not available")
        doc     = self.parser.parse(path)
        chunks1 = self.chunker.chunk_document(doc)
        chunks2 = self.chunker.chunk_document(doc)
        ids1 = [c.chunk_id for c in chunks1]
        ids2 = [c.chunk_id for c in chunks2]
        assert ids1 == ids2

    def test_chunk_ids_are_unique(self):
        path = find_upload("AML_Framework")
        if not path:
            pytest.skip("Upload not available")
        doc    = self.parser.parse(path)
        chunks = self.chunker.chunk_document(doc)
        ids    = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"

    def test_project_metadata_attached(self):
        path = find_upload("AML_Framework")
        if not path:
            pytest.skip("Upload not available")
        doc    = self.parser.parse(path)
        chunks = self.chunker.chunk_document(doc)
        for chunk in chunks:
            assert chunk.metadata.get("engagement_id") == "ME-RC-2023-0089"
            assert chunk.metadata.get("country") == "UAE"

    def test_text_chunks_within_size_limit(self):
        path = find_upload("AML_Framework")
        if not path:
            pytest.skip("Upload not available")
        doc    = self.parser.parse(path)
        chunks = self.chunker.chunk_document(doc)
        text_chunks = [c for c in chunks if c.kind == "text"]
        for chunk in text_chunks:
            # Allow some overshoot from splitter edge cases
            assert len(chunk.content) <= 1200, (
                f"Chunk too large: {len(chunk.content)} chars"
            )

    def test_table_chunks_preserved(self):
        path = find_upload("Risk_Register")
        if not path:
            pytest.skip("Upload not available")
        doc    = self.parser.parse(path)
        chunks = self.chunker.chunk_document(doc)
        table_chunks = [c for c in chunks if c.kind == "table"]
        assert len(table_chunks) > 0
        for tc in table_chunks:
            assert "|" in tc.content   # Markdown table format
