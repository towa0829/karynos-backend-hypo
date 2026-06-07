FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Sentence-BERTモデルをビルド時にダウンロード
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sonoisa/sentence-bert-base-ja-mean-tokens')"
