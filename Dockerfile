FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Sentence-BERTモデルをビルド時にダウンロード
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sonoisa/sentence-bert-base-ja-mean-tokens')"
