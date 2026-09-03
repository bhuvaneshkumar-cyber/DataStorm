FROM python:3.12-slim

# tesseract-ocr is the system half of pytesseract; without the binary the OCR
# fallback for scanned statement PDFs cannot run. Everything else ships as wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ml_service/requirements.txt ml_service/requirements-ingestion.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ingestion.txt

COPY ml_service/ .

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
