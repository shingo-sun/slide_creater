FROM python:3.11-slim

WORKDIR /app

# システム依存関係インストール（不要なものは削除済み）

# Python依存関係インストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコピー
COPY . .

# 出力ディレクトリ作成
RUN mkdir -p outputs uploads data/learning

# 環境変数
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
