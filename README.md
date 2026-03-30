# Slide Creater

画像忠実再現型 PowerPoint再構成AIシステム

## 概要

Google AI Studio等で生成されたスライド画像を、PowerPoint上で編集可能なオブジェクトとして高忠実度に再構成するシステムです。

## 機能

### MVP機能
- ✅ 画像1枚からPPTX1枚生成
- ✅ 日本語OCR対応（Google Cloud Vision API）
- ✅ 長方形、円、線、矢印の図形検出・再構成
- ✅ テキストボックス編集可能
- ✅ アイコン切出し独立配置
- ✅ 元画像との比較表示
- ✅ 忠実再現モード搭載

### 変換モード
1. **忠実再現モード**: 元画像の再現を最優先
2. **編集優先モード**: 編集可能性を重視
3. **ハイブリッドモード**: バランス重視

## セットアップ

### 必要条件
- Python 3.10+
- Node.js 18+
- (オプション) Google Cloud Vision API認証情報

### バックエンド

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### Google Cloud Vision APIの設定（オプション）

1. Google Cloud Consoleでプロジェクトを作成
2. Cloud Vision APIを有効化
3. サービスアカウントキーを作成してダウンロード
4. 環境変数を設定:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

※ Cloud Vision APIが設定されていない場合、フォールバックモード（テキスト領域検出のみ）で動作します。

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

ブラウザで http://localhost:3000 にアクセス

### 一括起動スクリプト

```bash
./start.sh
```

## API仕様

### エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| POST | `/api/upload` | 画像アップロード |
| POST | `/api/analyze/{file_id}` | 画像解析 |
| POST | `/api/generate/{file_id}` | PPTX生成 |
| GET | `/api/download/{file_id}` | PPTXダウンロード |
| GET | `/api/compare/{file_id}` | 比較情報取得 |
| DELETE | `/api/cleanup/{file_id}` | 一時ファイル削除 |

### パラメータ

**変換モード** (`mode`)
- `faithful`: 忠実再現モード
- `editable`: 編集優先モード
- `hybrid`: ハイブリッドモード

**スライドサイズ** (`slide_ratio`)
- `16:9`: ワイド
- `4:3`: 標準

## プロジェクト構造

```
slide_creater/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI アプリケーション
│   │   ├── models/
│   │   │   └── slide_objects.py # データモデル
│   │   └── services/
│   │       ├── image_analyzer.py  # 画像前処理
│   │       ├── ocr_service.py     # OCR処理
│   │       ├── shape_detector.py  # 図形検出
│   │       ├── layout_analyzer.py # レイアウト解析
│   │       └── pptx_generator.py  # PPTX生成
│   ├── uploads/                 # アップロード画像
│   ├── outputs/                 # 生成PPTX
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

## 品質目標

- 主要テキスト認識精度：90%以上
- 主要レイアウト一致率：90%以上
- 基本図形再現率：85%以上
- 編集可能オブジェクト率：80%以上
- 手動再作成工数削減率：70%以上

## ライセンス

MIT License
