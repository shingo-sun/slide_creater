#!/bin/bash
# Firebase + Cloud Run デプロイスクリプト

set -e

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-slide-creater}"
REGION="asia-northeast1"
SERVICE_NAME="slide-creater-api"

echo "=== Firebase + Cloud Run デプロイ ==="

# 前提条件チェック
if ! command -v gcloud &> /dev/null; then
    echo "エラー: gcloud CLI がインストールされていません"
    echo "https://cloud.google.com/sdk/docs/install からインストールしてください"
    exit 1
fi

if ! command -v firebase &> /dev/null; then
    echo "Firebase CLI をインストール中..."
    npm install -g firebase-tools
fi

# ログイン確認
echo ""
echo "1. Google Cloud 認証..."
gcloud auth login --quiet 2>/dev/null || true
gcloud config set project $PROJECT_ID

echo ""
echo "2. Cloud Run にバックエンドをデプロイ..."
cd backend
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d '=' -f2)" \
    --memory 1Gi \
    --timeout 300

# Cloud Run URL取得
BACKEND_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')
echo "バックエンドURL: $BACKEND_URL"

cd ..

echo ""
echo "3. フロントエンドをビルド..."
cd frontend
export VITE_API_URL=$BACKEND_URL
npm ci
npm run build
cd ..

echo ""
echo "4. Firebase Hosting にデプロイ..."
firebase login --interactive
firebase use $PROJECT_ID || firebase projects:add $PROJECT_ID
firebase deploy --only hosting

echo ""
echo "=== デプロイ完了 ==="
HOSTING_URL=$(firebase hosting:channel:list --json 2>/dev/null | grep -o 'https://[^"]*' | head -1 || echo "https://$PROJECT_ID.web.app")
echo "フロントエンド: https://$PROJECT_ID.web.app"
echo "バックエンドAPI: $BACKEND_URL"
