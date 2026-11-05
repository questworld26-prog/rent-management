"""PDF text extraction utility with degradation resilience."""

import logging
from pathlib import Path

import pdfplumber
import pypdf

logger = logging.getLogger(__name__)


# [spec: INGEST-007]
class EncryptedPdfError(Exception):
    """Raised when a PDF is encrypted or password-protected."""

    pass


# [spec: INGEST-007]
class ScannedImagePdfError(Exception):
    """Raised when a PDF yields insufficient text characters (scanned image)."""

    pass


# [spec: INGEST-001]
# [spec: INGEST-007]
def extract_text_from_pdf(pdf_path: Path | str) -> str:
    """Extract plain text from PDF using pdfplumber with degradation guards."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    # Check for password encryption
    try:
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted:
            raise EncryptedPdfError(f"PDF file is password-protected or encrypted: {path.name}")
    except (pypdf.errors.FileNotDecryptedError, EncryptedPdfError):
        raise EncryptedPdfError(f"PDF file is password-protected or encrypted: {path.name}") from None
    except Exception as exc:
        logger.debug("Failed pre-flight pypdf reader check on %s: %s", path.name, exc)

    extracted_pages: list[str] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    extracted_pages.append(text)
    except Exception as exc:
        if "password" in str(exc).lower() or "encrypted" in str(exc).lower():
            raise EncryptedPdfError(f"PDF file is password-protected: {path.name}") from exc
        # Fallback to pypdf
        reader = pypdf.PdfReader(str(path))
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_pages.append(text)

    combined_text = "\n--- PAGE BREAK ---\n".join(extracted_pages).strip()

    # AC-INGEST-007.1: Check minimum character threshold for scanned/empty PDFs
    if len(combined_text) < 40:
        raise ScannedImagePdfError(
            f"PDF file '{path.name}' yielded fewer than 40 characters of extractable text (likely a scanned image). OCR or manual entry required."
        )

    return combined_text
