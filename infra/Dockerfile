FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────────────────────
# PyMuPDF, pdfplumber, Pillow, LibreOffice (for PPTX/DOCX → PDF conversion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PDF rendering
    libmupdf-dev \
    poppler-utils \
    ghostscript \
    # Image processing
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgl1 \
    # LibreOffice (ColPali PPTX/DOCX page rendering)
    libreoffice \
    # Utilities
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ────────────────────────────────────────────────────────
# Copy requirements first so this layer is cached unless requirements change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ───────────────────────────────────────────────────────────
COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]