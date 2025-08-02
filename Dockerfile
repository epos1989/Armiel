FROM python:3.11-slim

# Systemabhängigkeiten und Tesseract
RUN apt-get update && \
    apt-get install -y --no-install-recommends tesseract-ocr libtesseract-dev libleptonica-dev pkg-config poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000

CMD ["python", "app.py"]
