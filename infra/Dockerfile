FROM python:3.11-slim

# System dependencies for PyMuPDF, camelot, pdf2image
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    poppler-utils \
    ghostscript \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
