import os
import re
import json
from typing import List, Dict
import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI

from config import settings
from questions_data import QUESTION_MAP

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "openai_precision_matching"


def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="sonoisa/sentence-bert-base-ja-mean-tokens"
    )
    return client.get_collection(name=COLLECTION_NAME, embedding_function=ef)


def build_profile_text(answers: List[Dict]) -> str:
    """Convert answers to a natural language profile for vector search."""
    lines = []
    for item in answers:
        qid = item["question_id"]
        oid = item["option_id"]
        qdata = QUESTION_MAP.get(qid)
        if not qdata:
            continue
        # option_id format: q1_o2 → index 1 (0-based)
        try:
            opt_idx = int(oid.split("_o")[-1]) - 1
            opt_text = qdata["opts"][opt_idx]
        except Exception:
            opt_text = oid
        lines.append(f"{qdata['q']}→{opt_text}")
    return "。".join(lines)


def generate_profile_with_openai(answers: List[Dict]) -> str:
    """Use OpenAI to generate a rich profile description from answers."""
    raw_text = build_profile_text(answers)
    if not settings.openai_api_key:
        return raw_text

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"""以下は就職診断の回答です。この回答から、この人物の性格・価値観・適性を200字程度で要約してください。

出力は HTML フラグメントで返してください（<html>や<body>タグは不要）。
使用してよいタグは <p>, <ul>, <li>, <strong>, <br> のみです。
強調したいキーワードは <strong> で囲み、複数の特性は <ul><li> で箇条書きにしてください。
コードブロックや ```html などのマークダウン記法は使わないでください。

回答: {raw_text}

要約（HTMLフラグメント）:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        content = response.choices[0].message.content.strip()
        # ```html ... ``` のようなコードフェンスが付いた場合は除去
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
            content = re.sub(r"\n?```$", "", content).strip()
        return content
    except Exception as e:
        print(f"[OpenAI] error: {e}")
        return raw_text


def _strip_code_fence(content: str) -> str:
    """```html ... ``` のようなコードフェンスを除去する。"""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content).strip()
    return content


def generate_result_analysis(profile_text: str, liked_jobs: List[Dict]) -> str:
    """診断回答の要約 + いいねした職業をもとに、最終的な分析文(HTML)を生成する。

    profile_text: analyze時にOpenAIが生成した回答要約（HTMLまたはプレーン）
    liked_jobs:   いいねした職業のリスト [{name, description}, ...]
    """
    # フォールバック: APIキーが無い場合は元の要約をそのまま返す
    if not settings.openai_api_key:
        return profile_text

    # 入力用に回答要約からHTMLタグを除去
    answer_summary = re.sub(r"<[^>]+>", " ", profile_text or "").strip()

    if liked_jobs:
        liked_lines = "\n".join(
            f"- {j.get('name', '')}: {(j.get('description') or '')[:80]}"
            for j in liked_jobs
        )
    else:
        liked_lines = "（いいねした職業はありませんでした）"

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"""あなたはキャリアアドバイザーです。
以下の「診断回答の要約」と「ユーザーがいいねした職業」をもとに、
この人物の性格・価値観・適性と、いいねした職業から読み取れる志向を踏まえた
最終的なパーソナル分析文を300字程度で作成してください。

出力は HTML フラグメントで返してください（<html>や<body>タグは不要）。
使用してよいタグは <p>, <ul>, <li>, <strong>, <br> のみです。
強調したいキーワードは <strong> で囲み、複数の特性は <ul><li> で箇条書きにしてください。
コードブロックや ```html などのマークダウン記法は使わないでください。

# 診断回答の要約
{answer_summary or "（情報なし）"}

# いいねした職業
{liked_lines}

最終分析文（HTMLフラグメント）:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return _strip_code_fence(response.choices[0].message.content)
    except Exception as e:
        print(f"[OpenAI] result analysis error: {e}")
        return profile_text


def search_jobs(profile_text: str, n_results: int = 30) -> List[Dict]:
    """Search ChromaDB and return ranked list of {job_id, score}."""
    collection = _get_collection()
    results = collection.query(
        query_texts=[profile_text],
        n_results=min(n_results, collection.count()),
    )
    job_scores = []
    ids = results["ids"][0]
    n = len(ids)
    for i, doc_id in enumerate(ids):
        try:
            job_id = int(doc_id)
        except ValueError:
            continue
        score = round(95 - (45 * i / max(n - 1, 1)), 1)
        job_scores.append({"job_id": job_id, "score": score})
    return job_scores
