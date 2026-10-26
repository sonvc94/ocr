# PaddlePaddle only ships Linux wheels for x86_64, so on Apple Silicon this runs under Rosetta.
FROM --platform=linux/amd64 python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    OCR_MODEL_SIZE=server

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only the model module (no app imports) goes into the model-download layer, so code edits keep the cached weights.
COPY app/__init__.py app/
COPY app/ocr/__init__.py app/ocr/ppocr_model.py app/ocr/
COPY scripts/download_models.py scripts/
RUN python -m scripts.download_models

COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
