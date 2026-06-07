# Karynos Hypo API (backend-hypo)

就職診断のプロトタイプ用バックエンド。FastAPI + PostgreSQL + ChromaDB（ベクトル検索）+ OpenAI で構成。
診断回答から職業をマッチングし、結果ページ用の最終分析文を OpenAI で生成する。

## 構成

- **FastAPI** — API サーバー（`:8080`）
- **PostgreSQL 17** — dreamers / histories / dreamer_profiles などを永続化（`./data` ボリューム）
- **ChromaDB** — 職業のベクトル検索（`./chroma_db`）
- **OpenAI** — 性格分析文の生成（`gpt-4o-mini`）

## セットアップ

### 1. 環境変数

リポジトリ直下に `.env` を作成する（`.env` は Git 管理対象外）。

```env
DATABASE_URL=postgresql://hypo_user:hypo_pass@db/hypo_db
OPENAI_API_KEY=sk-proj-xxxxxxxx
```

`OPENAI_API_KEY` が無効／未設定の場合、分析文は OpenAI を使わず回答のプレーンテキストにフォールバックする。

### 2. 起動

```bash
docker compose up -d
```

- API: http://localhost:8080
- Swagger UI: http://localhost:8080/docs

ログ確認:

```bash
docker compose logs -f app
```

停止:

```bash
docker compose down
```

> **注意:** `.env` を変更したら `docker compose restart` ではなく **`docker compose up -d`（必要なら `--force-recreate`）** で再作成すること。`restart` では env_file が再読込されず、古い環境変数のまま起動する。

## 主なエンドポイント

| Method | Path | 説明 |
|---|---|---|
| POST | `/api/v1/dreamers` | ユーザー作成（dreamer_id を返す） |
| GET  | `/api/v1/questions` | 診断の質問一覧 |
| POST | `/api/v1/recommend/analyze` | 回答を解析し、職業ランキングと分析文を作成・保存 |
| GET  | `/api/v1/recommend/{dreamer_id}` | 次のおすすめ職業を 1 件返す |
| POST | `/api/v1/recommend/{dreamer_id}/good?history_id=...` | いいね |
| POST | `/api/v1/recommend/{dreamer_id}/bad?history_id=...` | よくない |
| GET  | `/api/v1/recommend/{dreamer_id}/result` | 診断結果（最終分析文・いいねした職業・適合度TOP5） |

`/result` の `personality_text` は、回答要約＋いいねした職業をもとに OpenAI が **HTML フラグメント** で生成する。

## 動作確認（curl 例）

```bash
BASE=http://localhost:8080

# 1. ユーザー作成
DID=$(curl -s -X POST $BASE/api/v1/dreamers \
  -H "Content-Type: application/json" \
  -d '{"name_family":"テスト","name_given":"太郎"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['dreamer_id'])")

# 2. 30問に回答して解析
ANSWERS=$(python3 -c "import json;print(json.dumps([{'question_id':f'q{i}','option_id':f'q{i}_o1'} for i in range(1,31)]))")
curl -s -X POST $BASE/api/v1/recommend/analyze \
  -H "Content-Type: application/json" \
  -d "{\"dreamer_id\":\"$DID\",\"answers\":$ANSWERS}"

# 3. おすすめを取得していいね
REC=$(curl -s $BASE/api/v1/recommend/$DID)
HID=$(echo "$REC" | python3 -c "import sys,json;print(json.load(sys.stdin)['recommendation']['history_id'])")
curl -s -X POST "$BASE/api/v1/recommend/$DID/good?history_id=$HID"

# 4. 結果（最終分析文）を取得
curl -s $BASE/api/v1/recommend/$DID/result
```

## フロントエンド

UI は別リポジトリ [`karynos-web-hypo`](../karynos-web-hypo)（Next.js）。
`npm run dev` で起動し、デフォルトで `http://localhost:8080` の API を参照する。
