# Slide Creater - Magic Layers

画像をレイヤーに分解し、編集可能なPPTXを生成するAIシステム

## 概要

画像をClaude Vision APIで解析し、各要素（テキスト、図形、アイコン等）を個別の編集可能なレイヤーとして分解します。分解されたレイヤーからPowerPointを生成でき、Google Slideで開いて編集することができます。

## 機能

- ✨ **Magic Layers**: 画像を編集可能なレイヤーに自動分解
- 📝 テキスト要素 → 編集可能なテキストボックス
- 🔷 図形（四角、線など）→ PowerPointネイティブシェイプ
- 🎨 画像/アイコン → 透過PNG画像として配置
- 📤 ワンクリックでPPTXダウンロード & Google Driveを開く

## セットアップ

### 必要条件
- Python 3.10+
- Node.js 18+
- Anthropic API Key (Claude)

### バックエンド

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 環境変数の設定

`.env`ファイルを作成:

```bash
ANTHROPIC_API_KEY=your_api_key_here
```

### フロントエンド

```bash
cd frontend
npm install
```

## 起動

### 開発モード

```bash
# バックエンド（別ターミナル）
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# フロントエンド（別ターミナル）
cd frontend
npm run dev
```

ブラウザで http://localhost:5173 にアクセス

### 一括起動スクリプト

```bash
./start.sh
```

## API仕様

### エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| POST | `/api/upload` | 画像アップロード |
| POST | `/api/decompose/{file_id}` | 画像をレイヤーに分解 |
| GET | `/api/layers/{file_id}` | 分解済みレイヤー情報取得 |
| DELETE | `/api/layers/{file_id}` | レイヤーデータ削除 |
| POST | `/api/layers/{file_id}/pptx` | レイヤーからPPTX生成 |
| GET | `/api/layers/{file_id}/download` | PPTXダウンロード |

## プロジェクト構造

```
slide_creater/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI アプリケーション
│   │   └── services/
│   │       └── layer_decomposer.py # Claude Vision APIによるレイヤー分解
│   ├── uploads/                 # アップロード画像
│   ├── outputs/                 # 生成PPTX・レイヤー画像
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # メインアプリケーション
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 技術スタック

- **バックエンド**: FastAPI, Python 3.10+
- **フロントエンド**: React, TypeScript, Vite
- **AI**: Claude Vision API (Anthropic)
- **PPTX生成**: python-pptx
- **画像処理**: OpenCV, Pillow

## ライセンス

MIT License
