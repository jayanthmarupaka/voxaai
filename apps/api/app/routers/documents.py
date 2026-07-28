"""Document upload, listing, and deletion — all scoped to the caller's business."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select

from app.deps import CurrentBusiness, SessionDep
from app.models import Document
from app.schemas import DocumentOut, DocumentUploadResult
from app.services.rag import (
    ALLOWED_MIME_TYPES,
    MAX_UPLOAD_BYTES,
    DocumentProcessingError,
    extract_text,
    index_document,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
async def list_documents(business: CurrentBusiness, session: SessionDep) -> list[DocumentOut]:
    rows = await session.scalars(
        select(Document)
        .where(Document.business_id == business.id)
        .order_by(Document.created_at.desc())
    )
    return [DocumentOut.model_validate(row) for row in rows]


@router.post("", response_model=DocumentUploadResult, status_code=status.HTTP_201_CREATED)
async def upload_document(
    business: CurrentBusiness,
    session: SessionDep,
    file: UploadFile = File(...),
) -> DocumentUploadResult:
    mime_type = (file.content_type or "").split(";")[0].strip().lower()
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type {mime_type or 'unknown'}. Upload a PDF, .txt or .md.",
        )

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    filename = (file.filename or "document")[:512]

    try:
        text = extract_text(data, mime_type, filename)
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    document = Document(
        business_id=business.id,
        filename=filename,
        mime_type=mime_type,
        byte_size=len(data),
        raw_text=text,
        status="pending",
    )
    session.add(document)
    await session.flush()

    try:
        chunk_count = await index_document(session, document)
    except Exception as exc:
        logger.exception("Indexing failed for document %s", document.id)
        document.status = "failed"
        document.error = str(exc)[:500]
        await session.flush()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate embeddings. Check the Azure OpenAI configuration.",
        ) from exc

    return DocumentUploadResult(
        document=DocumentOut.model_validate(document), chunks_indexed=chunk_count
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, business: CurrentBusiness, session: SessionDep
) -> None:
    result = await session.execute(
        delete(Document).where(
            Document.id == document_id,
            # Scoping the DELETE itself means a wrong ID is a no-op, not a
            # cross-tenant deletion.
            Document.business_id == business.id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
