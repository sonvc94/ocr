# PaddleOCR-VL in its own container: it needs PaddlePaddle 3.3.x, which breaks PP-OCRv5 on CPU.
FROM --platform=linux/amd64 python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV VL_PIPELINE_VERSION=v1.5
COPY main.py .
# Bake the model weights into the image so the container starts without network access.
RUN python -c "import main; main.get_vl(); print('models ready')"

# Needs > 8GB of Docker memory: on CPU the bf16 weights are loaded as float32. With Docker Desktop's
# default limit, run the service natively instead (see README).
EXPOSE 8011
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8011"]
