import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';

// 本番環境用API URL設定
const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const api = axios.create({
  baseURL: API_BASE_URL,
});

// アプリモードの型
type AppMode = 'pptx' | 'layers';

// レイヤー要素の型
interface LayerElement {
  layer_id: string;
  element_type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  z_index: number;
  description: string;
  content: string | null;
  color: string | null;
  image_url: string | null;
  confidence: number;
}

// レイヤー分解結果の型
interface DecomposeResult {
  file_id: string;
  success: boolean;
  message: string;
  original_size: {
    width: number;
    height: number;
  };
  background_color: string | null;
  layer_count: number;
  layers: LayerElement[];
  output_dir: string;
  metadata_url: string;
  pptx_url?: string;  // PPTX生成後に追加
}

// パイプラインステップの型
interface PipelineStep {
  step: number;
  name: string;
  status: 'waiting' | 'running' | 'completed' | 'failed';
  description?: string;
  result?: Record<string, unknown>;
  error?: string;
}

// イテレーション結果の型
interface IterationResult {
  iteration: number;
  steps: PipelineStep[];
  similarity_score: number;
  ssim_score?: number;
  status: string;
  pptx_url?: string;
  generated_image_url?: string;
  diff_image_url?: string;
  ai_analysis?: {
    quality_assessment: string;
    differences_count: number;
    corrections_count: number;
    confidence: number;
  };
  differences?: Array<{
    location: string;
    type: string;
    original: string;
    generated: string;
    severity: string;
  }>;
  corrections?: Array<{
    target: string;
    action: string;
  }>;
}

// フルパイプライン結果の型
interface PipelineResult {
  status: 'success' | 'incomplete' | 'error';
  message: string;
  final_similarity: number;
  iterations_count: number;
  best_version: number;
  iterations: IterationResult[];
  download_url: string;
}

type ConversionMode = 'faithful' | 'editable' | 'hybrid';
type SlideRatio = '16:9' | '4:3';

// ステップアイコンコンポーネント
const StepIcon = ({ status }: { status: string }) => {
  switch (status) {
    case 'completed':
      return <span style={{ color: '#22c55e' }}>✓</span>;
    case 'running':
      return <span className="spinner-small">⟳</span>;
    case 'failed':
      return <span style={{ color: '#ef4444' }}>✗</span>;
    default:
      return <span style={{ color: '#9ca3af' }}>○</span>;
  }
};

function App() {
  // アプリモード
  const [appMode, setAppMode] = useState<AppMode>('layers');
  
  const [file, setFile] = useState<File | null>(null);
  const [fileId, setFileId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pptxUrl, setPptxUrl] = useState<string | null>(null);
  const [originalImageUrl, setOriginalImageUrl] = useState<string | null>(null);
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null);
  const [currentStep, setCurrentStep] = useState<string>('');
  
  // Magic Layers用の状態
  const [decomposeResult, setDecomposeResult] = useState<DecomposeResult | null>(null);
  const [selectedLayer, setSelectedLayer] = useState<string | null>(null);
  
  // Settings
  const [mode, setMode] = useState<ConversionMode>('faithful');
  const [slideRatio, setSlideRatio] = useState<SlideRatio>('16:9');
  const [targetSimilarity, setTargetSimilarity] = useState(95);
  const [maxIterations, setMaxIterations] = useState(5);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
      setError(null);
      setPptxUrl(null);
      setPipelineResult(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'application/pdf': ['.pdf'],
    },
    maxFiles: 1,
  });

  const uploadFile = async () => {
    if (!file) return null;

    setUploading(true);
    setCurrentStep('ファイルをアップロード中...');
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      
      setFileId(response.data.file_id);
      setOriginalImageUrl(`/uploads/${response.data.filename}`);
      setUploading(false);
      
      return response.data.file_id;
    } catch (err: unknown) {
      let errorMessage = 'アップロードに失敗しました';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      setError(errorMessage);
      setUploading(false);
      return null;
    }
  };

  // フルパイプライン実行（95%達成まで自動ループ）
  const runFullPipeline = async () => {
    let currentFileId = fileId;

    if (!currentFileId) {
      currentFileId = await uploadFile();
      if (!currentFileId) return;
    }

    setProcessing(true);
    setCurrentStep('ダブルループ学習パイプライン開始...');
    setPipelineResult(null);
    setError(null);

    try {
      const response = await axios.post(
        `/api/full-pipeline/${currentFileId}?max_iterations=${maxIterations}&target_similarity=${targetSimilarity / 100}`
      );

      setPipelineResult(response.data);
      setPptxUrl(response.data.download_url);
      setCurrentStep('');
      
    } catch (err: unknown) {
      let errorMessage = '処理に失敗しました';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      console.error('Error:', err);
      setError(errorMessage);
    }
    
    setProcessing(false);
  };

  const downloadPptx = () => {
    if (pptxUrl) {
      window.open(pptxUrl, '_blank');
    }
  };

  const reset = () => {
    setFile(null);
    setFileId(null);
    setPptxUrl(null);
    setOriginalImageUrl(null);
    setPipelineResult(null);
    setDecomposeResult(null);
    setSelectedLayer(null);
    setCurrentStep('');
    setError(null);
  };

  // Magic Layers分解実行
  const runDecompose = async () => {
    let currentFileId = fileId;

    if (!currentFileId) {
      currentFileId = await uploadFile();
      if (!currentFileId) return;
    }

    setProcessing(true);
    setCurrentStep('画像をレイヤーに分解中...');
    setDecomposeResult(null);
    setError(null);

    try {
      // Step 1: レイヤー分解
      const response = await axios.post<DecomposeResult>(
        `/api/decompose/${currentFileId}`
      );

      const result = response.data;
      
      // Step 2: PPTX自動生成
      setCurrentStep('PPTXを生成中...');
      try {
        const pptxResponse = await axios.post<{ download_url: string }>(
          `/api/layers/${currentFileId}/pptx`
        );
        result.pptx_url = pptxResponse.data.download_url;
        
        // Step 3: 自動ダウンロード
        if (result.pptx_url) {
          setCurrentStep('PPTXをダウンロード中...');
          const link = document.createElement('a');
          link.href = result.pptx_url;
          link.download = `${currentFileId}_layers.pptx`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          
          // Step 4: Google Driveを開く（少し待ってから）
          setTimeout(() => {
            window.open('https://drive.google.com/drive/my-drive', '_blank');
          }, 1500);
        }
      } catch (pptxErr) {
        console.warn('PPTX生成エラー（レイヤー分解は成功）:', pptxErr);
      }

      setDecomposeResult(result);
      setCurrentStep('');
      
    } catch (err: unknown) {
      let errorMessage = 'レイヤー分解に失敗しました';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      console.error('Error:', err);
      setError(errorMessage);
    }
    
    setProcessing(false);
  };

  const isProcessing = uploading || processing;

  return (
    <div className="app">
      <header className="header">
        <h1>🎯 Slide Creater</h1>
        <p>画像忠実再現型 PowerPoint再構成AIシステム（ダブルループ学習搭載）</p>
      </header>

      {/* Mode Switcher */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        gap: '0.5rem', 
        padding: '1rem',
        background: 'var(--bg-secondary)',
        borderRadius: '12px',
        maxWidth: '300px',
        margin: '0 auto 1.5rem'
      }}>
        <button
          onClick={() => { setAppMode('layers'); reset(); }}
          style={{
            flex: 1,
            padding: '0.75rem 1.5rem',
            border: 'none',
            borderRadius: '8px',
            cursor: 'pointer',
            fontWeight: 'bold',
            fontSize: '1rem',
            transition: 'all 0.2s',
            background: 'linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%)',
            color: 'white'
          }}
        >
          ✨ Magic Layers
        </button>
      </div>

      <main className="main-content">
        {/* Magic Layers Mode */}
        {appMode === 'layers' && (
          <>
            {/* Upload Section for Layers */}
            <div className="card">
              <h2 className="card-title">✨ Magic Layers - 画像をレイヤーに分解</h2>
              <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
                画像をドロップすると、各要素（テキスト、図形、アイコン等）を個別の編集可能なレイヤーとして分解します
              </p>
              <div style={{ 
                background: 'rgba(168, 85, 247, 0.1)', 
                padding: '0.75rem 1rem', 
                borderRadius: '8px',
                marginBottom: '1rem',
                fontSize: '0.9rem'
              }}>
                📁 <strong>保存先:</strong> <code style={{ background: 'rgba(0,0,0,0.2)', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>backend/outputs/&#123;file_id&#125;_layers/</code>
                <br />
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                  各レイヤーは透過PNG形式、座標情報は layers_metadata.json に保存されます
                </span>
              </div>
              
              <div
                {...getRootProps()}
                className={`dropzone ${isDragActive ? 'active' : ''}`}
                style={{ 
                  borderColor: isDragActive ? '#a855f7' : undefined,
                  background: isDragActive ? 'rgba(168, 85, 247, 0.1)' : undefined
                }}
              >
                <input {...getInputProps()} />
                <div className="dropzone-icon">🎨</div>
                {file ? (
                  <p className="dropzone-text">
                    <strong>{file.name}</strong> ({(file.size / 1024 / 1024).toFixed(2)} MB)
                  </p>
                ) : (
                  <p className="dropzone-text">
                    ドラッグ＆ドロップ、または<strong>クリックしてファイルを選択</strong>
                    <br />
                    対応形式: PNG, JPG
                  </p>
                )}
              </div>

              {file && !decomposeResult && (
                <button
                  className="btn btn-primary btn-lg"
                  onClick={runDecompose}
                  disabled={isProcessing}
                  style={{ 
                    marginTop: '1rem', 
                    width: '100%',
                    background: 'linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%)'
                  }}
                >
                  {isProcessing ? (
                    <>
                      <span className="spinner" />
                      {currentStep || '処理中...'}
                    </>
                  ) : (
                    <>✨ レイヤーに分解する</>
                  )}
                </button>
              )}
            </div>

            {/* Decompose Results */}
            {decomposeResult && (
              <>
                {/* Summary */}
                <div className="card" style={{ 
                  background: 'linear-gradient(135deg, #581c87 0%, #7c3aed 100%)',
                  textAlign: 'center'
                }}>
                  <h2 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>
                    ✨ {decomposeResult.layer_count}個のレイヤーを検出
                  </h2>
                  <p style={{ opacity: 0.9 }}>{decomposeResult.message}</p>
                  <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', opacity: 0.7 }}>
                    元画像サイズ: {decomposeResult.original_size.width} × {decomposeResult.original_size.height}px
                  </p>
                  <div style={{ 
                    background: 'rgba(0,0,0,0.2)', 
                    padding: '0.75rem', 
                    borderRadius: '8px',
                    marginTop: '1rem',
                    fontSize: '0.85rem'
                  }}>
                    📁 保存先: <code style={{ background: 'rgba(255,255,255,0.1)', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                      {decomposeResult.output_dir}
                    </code>
                  </div>
                </div>

                {/* Google Slide Instructions */}
                <div className="card" style={{ 
                  background: 'linear-gradient(135deg, #1a73e8 0%, #4285f4 100%)',
                  textAlign: 'center'
                }}>
                  <h3 style={{ fontSize: '1.2rem', marginBottom: '0.75rem' }}>
                    📤 Google Slideで開く
                  </h3>
                  <p style={{ opacity: 0.9, marginBottom: '1rem' }}>
                    ダウンロードしたPPTXファイルをGoogle Driveにドラッグ＆ドロップしてください
                  </p>
                  <button
                    className="btn"
                    onClick={() => window.open('https://drive.google.com/drive/my-drive', '_blank')}
                    style={{ 
                      background: 'white',
                      color: '#1a73e8',
                      fontWeight: 'bold'
                    }}
                  >
                    Google Driveを開く
                  </button>
                </div>

                {/* Layer Preview Grid */}
                <div className="card">
                  <h2 className="card-title">🎨 分解されたレイヤー</h2>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                    gap: '1rem'
                  }}>
                    {decomposeResult.layers.map((layer) => (
                      <div
                        key={layer.layer_id}
                        onClick={() => setSelectedLayer(selectedLayer === layer.layer_id ? null : layer.layer_id)}
                        style={{
                          background: selectedLayer === layer.layer_id 
                            ? 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)'
                            : 'var(--bg-secondary)',
                          borderRadius: '12px',
                          padding: '1rem',
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                          border: selectedLayer === layer.layer_id 
                            ? '2px solid #a855f7' 
                            : '2px solid transparent'
                        }}
                      >
                        {/* Layer Preview Image */}
                        <div style={{
                          background: decomposeResult.background_color || '#ffffff',
                          borderRadius: '8px',
                          padding: '0.5rem',
                          marginBottom: '0.75rem',
                          minHeight: '100px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}>
                          {layer.image_url ? (
                            <img 
                              src={layer.image_url} 
                              alt={layer.description}
                              style={{ 
                                maxWidth: '100%', 
                                maxHeight: '120px',
                                objectFit: 'contain'
                              }}
                            />
                          ) : (
                            <span style={{ color: '#666' }}>No preview</span>
                          )}
                        </div>

                        {/* Layer Info */}
                        <div style={{ fontSize: '0.85rem' }}>
                          <div style={{ 
                            display: 'inline-block',
                            background: 'rgba(168, 85, 247, 0.3)',
                            padding: '0.2rem 0.5rem',
                            borderRadius: '4px',
                            marginBottom: '0.5rem',
                            fontWeight: 'bold'
                          }}>
                            {layer.element_type}
                          </div>
                          <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                            {layer.description || 'No description'}
                          </div>
                          {layer.content && (
                            <div style={{ 
                              marginTop: '0.3rem',
                              fontStyle: 'italic',
                              color: 'var(--text-secondary)',
                              fontSize: '0.75rem',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap'
                            }}>
                              "{layer.content}"
                            </div>
                          )}
                        </div>

                        {/* Position Badge */}
                        <div style={{ 
                          marginTop: '0.5rem',
                          fontSize: '0.7rem',
                          color: 'var(--text-secondary)',
                          display: 'flex',
                          justifyContent: 'space-between'
                        }}>
                          <span>z: {layer.z_index}</span>
                          <span>{layer.width}×{layer.height}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Selected Layer Details */}
                {selectedLayer && (
                  <div className="card">
                    <h2 className="card-title">📋 レイヤー詳細</h2>
                    {(() => {
                      const layer = decomposeResult.layers.find(l => l.layer_id === selectedLayer);
                      if (!layer) return null;
                      return (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                          <div>
                            <h3 style={{ marginBottom: '0.5rem' }}>位置情報</h3>
                            <table style={{ width: '100%', fontSize: '0.9rem' }}>
                              <tbody>
                                <tr><td style={{ color: 'var(--text-secondary)' }}>X座標:</td><td>{layer.x}px</td></tr>
                                <tr><td style={{ color: 'var(--text-secondary)' }}>Y座標:</td><td>{layer.y}px</td></tr>
                                <tr><td style={{ color: 'var(--text-secondary)' }}>幅:</td><td>{layer.width}px</td></tr>
                                <tr><td style={{ color: 'var(--text-secondary)' }}>高さ:</td><td>{layer.height}px</td></tr>
                                <tr><td style={{ color: 'var(--text-secondary)' }}>Z-Index:</td><td>{layer.z_index}</td></tr>
                              </tbody>
                            </table>
                          </div>
                          <div>
                            <h3 style={{ marginBottom: '0.5rem' }}>属性</h3>
                            <table style={{ width: '100%', fontSize: '0.9rem' }}>
                              <tbody>
                                <tr><td style={{ color: 'var(--text-secondary)' }}>タイプ:</td><td>{layer.element_type}</td></tr>
                                <tr><td style={{ color: 'var(--text-secondary)' }}>信頼度:</td><td>{(layer.confidence * 100).toFixed(0)}%</td></tr>
                                {layer.color && (
                                  <tr>
                                    <td style={{ color: 'var(--text-secondary)' }}>色:</td>
                                    <td style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                      <span style={{ 
                                        width: '16px', 
                                        height: '16px', 
                                        background: layer.color,
                                        borderRadius: '4px',
                                        border: '1px solid #666'
                                      }}></span>
                                      {layer.color}
                                    </td>
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                          {layer.image_url && (
                            <div style={{ gridColumn: '1 / -1' }}>
                              <a 
                                href={layer.image_url} 
                                download 
                                className="btn btn-outline"
                                style={{ marginTop: '0.5rem' }}
                              >
                                📥 このレイヤーをダウンロード (PNG)
                              </a>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                )}

                {/* PPTX Download - Primary Action */}
                {decomposeResult.pptx_url && (
                  <div className="card" style={{ 
                    textAlign: 'center',
                    background: 'linear-gradient(135deg, #065f46 0%, #047857 100%)'
                  }}>
                    <h2 style={{ marginBottom: '0.5rem' }}>🎉 PPTXが準備できました！</h2>
                    <p style={{ opacity: 0.9, marginBottom: '1rem' }}>
                      各レイヤーを個別のオブジェクトとして配置済み
                    </p>
                    <a 
                      href={decomposeResult.pptx_url}
                      className="btn"
                      style={{ 
                        background: 'white', 
                        color: '#047857',
                        padding: '1rem 2rem',
                        fontSize: '1.2rem',
                        fontWeight: 'bold',
                        display: 'inline-block',
                        textDecoration: 'none',
                        borderRadius: '8px'
                      }}
                    >
                      📥 PPTXをダウンロード
                    </a>
                  </div>
                )}

                {/* Other Downloads */}
                <div className="card" style={{ textAlign: 'center' }}>
                  <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
                    <button className="btn btn-outline" onClick={reset}>
                      🔄 別の画像を分解
                    </button>
                    <a 
                      href={decomposeResult.metadata_url} 
                      download 
                      className="btn btn-outline"
                    >
                      📋 メタデータ (JSON)
                    </a>
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* PPTX Mode */}
        {appMode === 'pptx' && (
          <>
        {/* Upload Section */}
        <div className="card">
          <h2 className="card-title">📤 Step 1: 画像をアップロード</h2>
          
          <div
            {...getRootProps()}
            className={`dropzone ${isDragActive ? 'active' : ''}`}
          >
            <input {...getInputProps()} />
            <div className="dropzone-icon">📁</div>
            {file ? (
              <p className="dropzone-text">
                <strong>{file.name}</strong> ({(file.size / 1024 / 1024).toFixed(2)} MB)
              </p>
            ) : (
              <p className="dropzone-text">
                ドラッグ＆ドロップ、または<strong>クリックしてファイルを選択</strong>
                <br />
                対応形式: PNG, JPG, PDF
              </p>
            )}
          </div>

          {file && !pipelineResult && (
            <div style={{ marginTop: '1rem' }}>
              <div className="form-group">
                <label className="form-label">変換モード</label>
                <select
                  className="form-select"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as ConversionMode)}
                >
                  <option value="faithful">忠実再現モード - 元画像の再現を最優先</option>
                  <option value="editable">編集優先モード - 編集可能性を重視</option>
                  <option value="hybrid">ハイブリッドモード - バランス重視</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">スライドサイズ</label>
                <select
                  className="form-select"
                  value={slideRatio}
                  onChange={(e) => setSlideRatio(e.target.value as SlideRatio)}
                >
                  <option value="16:9">16:9 (ワイド)</option>
                  <option value="4:3">4:3 (標準)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">🎯 目標類似度: <strong>{targetSimilarity}%</strong></label>
                <input
                  type="range"
                  min="70"
                  max="99"
                  value={targetSimilarity}
                  onChange={(e) => setTargetSimilarity(Number(e.target.value))}
                  style={{ width: '100%' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  <span>70%</span>
                  <span>95%（推奨）</span>
                  <span>99%</span>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">🔄 最大イテレーション回数: <strong>{maxIterations}</strong></label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(Number(e.target.value))}
                  style={{ width: '100%' }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Processing Status */}
        {isProcessing && (
          <div className="card" style={{ background: 'linear-gradient(135deg, #1e3a5f 0%, #2d4a6f 100%)' }}>
            <h2 className="card-title" style={{ color: '#60a5fa' }}>
              🔄 ダブルループ学習実行中...
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1rem 0' }}>
              <div className="spinner" style={{ width: '24px', height: '24px' }}></div>
              <span style={{ color: '#93c5fd' }}>{currentStep}</span>
            </div>
            <div style={{ 
              padding: '1rem', 
              background: 'rgba(0,0,0,0.2)', 
              borderRadius: '8px',
              marginTop: '1rem'
            }}>
              <h3 style={{ color: '#60a5fa', marginBottom: '0.5rem' }}>📊 実行中のプロセス</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '0.5rem', textAlign: 'center' }}>
                <div style={{ padding: '0.5rem', background: 'rgba(34,197,94,0.2)', borderRadius: '4px' }}>
                  <div>1️⃣</div>
                  <div style={{ fontSize: '0.8rem' }}>PPTX生成</div>
                </div>
                <div style={{ padding: '0.5rem', background: 'rgba(59,130,246,0.2)', borderRadius: '4px' }}>
                  <div>2️⃣</div>
                  <div style={{ fontSize: '0.8rem' }}>画像変換</div>
                </div>
                <div style={{ padding: '0.5rem', background: 'rgba(168,85,247,0.2)', borderRadius: '4px' }}>
                  <div>3️⃣</div>
                  <div style={{ fontSize: '0.8rem' }}>比較検証</div>
                </div>
                <div style={{ padding: '0.5rem', background: 'rgba(236,72,153,0.2)', borderRadius: '4px' }}>
                  <div>4️⃣</div>
                  <div style={{ fontSize: '0.8rem' }}>Claude分析</div>
                </div>
                <div style={{ padding: '0.5rem', background: 'rgba(245,158,11,0.2)', borderRadius: '4px' }}>
                  <div>5️⃣</div>
                  <div style={{ fontSize: '0.8rem' }}>学習・修正</div>
                </div>
              </div>
              <p style={{ color: '#9ca3af', fontSize: '0.9rem', marginTop: '1rem', textAlign: 'center' }}>
                類似度が <strong style={{ color: '#22c55e' }}>{targetSimilarity}%</strong> に達するまで自動で繰り返します
              </p>
            </div>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="status-error">
            ⚠️ {error}
          </div>
        )}

        {/* Pipeline Results */}
        {pipelineResult && (
          <>
            {/* Final Result Banner */}
            <div className="card" style={{ 
              background: pipelineResult.status === 'success' 
                ? 'linear-gradient(135deg, #065f46 0%, #047857 100%)' 
                : 'linear-gradient(135deg, #7c2d12 0%, #9a3412 100%)',
              textAlign: 'center'
            }}>
              <h2 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>
                {pipelineResult.status === 'success' ? '🎉' : '📊'} 
                最終類似度: {(pipelineResult.final_similarity * 100).toFixed(1)}%
              </h2>
              <p style={{ fontSize: '1.1rem', opacity: 0.9 }}>
                {pipelineResult.message}
              </p>
              <p style={{ fontSize: '0.9rem', marginTop: '0.5rem', opacity: 0.7 }}>
                {pipelineResult.iterations_count}回のイテレーションを実行
              </p>
            </div>

            {/* Iteration Timeline */}
            <div className="card">
              <h2 className="card-title">📈 イテレーション履歴（検証→再編集ループ）</h2>
              
              <div style={{ position: 'relative' }}>
                {pipelineResult.iterations.map((iteration, idx) => (
                  <div 
                    key={idx} 
                    style={{ 
                      marginBottom: '1.5rem',
                      paddingLeft: '2rem',
                      borderLeft: '3px solid',
                      borderColor: iteration.status === 'target_achieved' ? '#22c55e' : 
                                   iteration.status === 'completed' ? '#3b82f6' : 
                                   iteration.status === 'failed' ? '#ef4444' : '#6b7280'
                    }}
                  >
                    {/* Iteration Header */}
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '1rem',
                      marginBottom: '0.5rem',
                      flexWrap: 'wrap'
                    }}>
                      <span style={{ 
                        background: iteration.status === 'target_achieved' ? '#22c55e' : '#3b82f6',
                        color: 'white',
                        padding: '0.25rem 0.75rem',
                        borderRadius: '999px',
                        fontWeight: 'bold'
                      }}>
                        🔁 イテレーション {iteration.iteration}
                      </span>
                      <span style={{ 
                        fontSize: '1.5rem', 
                        fontWeight: 'bold',
                        color: iteration.similarity_score >= 0.95 ? '#22c55e' : 
                               iteration.similarity_score >= 0.80 ? '#f59e0b' : '#ef4444'
                      }}>
                        類似度: {(iteration.similarity_score * 100).toFixed(1)}%
                      </span>
                      {iteration.status === 'target_achieved' && (
                        <span style={{ 
                          background: '#22c55e', 
                          color: 'white',
                          padding: '0.25rem 0.5rem',
                          borderRadius: '4px',
                          fontWeight: 'bold'
                        }}>🎯 目標達成!</span>
                      )}
                    </div>

                    {/* Steps Visualization */}
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center',
                      gap: '0.25rem',
                      marginTop: '0.5rem',
                      flexWrap: 'wrap'
                    }}>
                      {iteration.steps.map((step, stepIdx) => (
                        <div key={stepIdx} style={{ display: 'flex', alignItems: 'center' }}>
                          <div 
                            style={{
                              background: step.status === 'completed' ? '#22c55e' : 
                                         step.status === 'running' ? '#3b82f6' :
                                         step.status === 'failed' ? '#ef4444' : '#374151',
                              color: 'white',
                              padding: '0.4rem 0.75rem',
                              borderRadius: '4px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.3rem',
                              fontSize: '0.8rem',
                              whiteSpace: 'nowrap'
                            }}
                          >
                            <StepIcon status={step.status} />
                            <span>{step.name}</span>
                          </div>
                          {stepIdx < iteration.steps.length - 1 && (
                            <span style={{ margin: '0 0.25rem', color: '#6b7280' }}>→</span>
                          )}
                        </div>
                      ))}
                    </div>

                    {/* AI Analysis Summary */}
                    {iteration.ai_analysis && (
                      <div style={{ 
                        marginTop: '0.75rem', 
                        padding: '0.75rem',
                        background: 'rgba(59, 130, 246, 0.1)',
                        borderRadius: '6px',
                        fontSize: '0.85rem'
                      }}>
                        <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
                          <span>
                            🔍 検出差分: <strong>{iteration.ai_analysis.differences_count}</strong>件
                          </span>
                          <span>
                            💡 修正提案: <strong>{iteration.ai_analysis.corrections_count}</strong>件
                          </span>
                          <span>
                            🎯 AI信頼度: <strong>{(iteration.ai_analysis.confidence * 100).toFixed(0)}%</strong>
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Differences Detail (collapsible) */}
                    {iteration.differences && iteration.differences.length > 0 && (
                      <details style={{ marginTop: '0.5rem' }}>
                        <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                          📋 Claude API検出の差分を表示 ({iteration.differences.length}件)
                        </summary>
                        <div style={{ marginTop: '0.5rem', maxHeight: '200px', overflowY: 'auto' }}>
                          {iteration.differences.map((diff, diffIdx) => (
                            <div 
                              key={diffIdx}
                              style={{
                                padding: '0.5rem',
                                marginBottom: '0.25rem',
                                background: 'var(--bg-secondary)',
                                borderRadius: '4px',
                                borderLeft: `3px solid ${
                                  diff.severity === 'high' ? '#ef4444' : 
                                  diff.severity === 'medium' ? '#f59e0b' : '#22c55e'
                                }`,
                                fontSize: '0.8rem'
                              }}
                            >
                              <div><strong>{diff.type}</strong> @ {diff.location}</div>
                              <div style={{ color: 'var(--text-secondary)' }}>
                                元: {diff.original} → 生成: {diff.generated}
                              </div>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}

                    {/* Corrections Applied */}
                    {iteration.corrections && iteration.corrections.length > 0 && (
                      <details style={{ marginTop: '0.25rem' }}>
                        <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                          🔧 適用した修正 ({iteration.corrections.length}件)
                        </summary>
                        <div style={{ marginTop: '0.5rem' }}>
                          {iteration.corrections.map((corr, corrIdx) => (
                            <div 
                              key={corrIdx}
                              style={{
                                padding: '0.4rem 0.5rem',
                                marginBottom: '0.25rem',
                                background: 'rgba(34,197,94,0.1)',
                                borderRadius: '4px',
                                fontSize: '0.8rem'
                              }}
                            >
                              ✓ {corr.action}: {corr.target}
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Image Comparison */}
            {originalImageUrl && pipelineResult.iterations.length > 0 && (
              <div className="card">
                <h2 className="card-title">🖼️ 元画像 vs 最終生成結果</h2>
                <div className="preview-container">
                  <div className="preview-panel">
                    <div className="preview-header">元画像（入力）</div>
                    <img
                      src={originalImageUrl}
                      alt="Original"
                      className="preview-image"
                    />
                  </div>
                  <div className="preview-panel">
                    <div className="preview-header">
                      PPTX生成結果 (v{pipelineResult.best_version}) - {(pipelineResult.final_similarity * 100).toFixed(1)}%
                    </div>
                    {pipelineResult.iterations[pipelineResult.iterations.length - 1]?.generated_image_url ? (
                      <img
                        src={pipelineResult.iterations[pipelineResult.iterations.length - 1].generated_image_url}
                        alt="Generated"
                        className="preview-image"
                      />
                    ) : (
                      <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        プレビュー画像がありません
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Download Section */}
            <div className="card" style={{ textAlign: 'center', background: 'linear-gradient(135deg, #1e40af 0%, #3b82f6 100%)' }}>
              <h2 className="card-title">📥 ダウンロード</h2>
              <p style={{ marginBottom: '1rem', opacity: 0.9 }}>
                最終バージョン (v{pipelineResult.best_version}) - 類似度 {(pipelineResult.final_similarity * 100).toFixed(1)}%
              </p>
              <button 
                className="btn btn-lg" 
                onClick={downloadPptx}
                style={{ background: '#22c55e', color: 'white', padding: '1rem 2rem', fontSize: '1.2rem' }}
              >
                📥 PPTXをダウンロード
              </button>
            </div>
          </>
        )}

        {/* Actions - PPTX Mode */}
        <div className="actions-bar">
          {file && !pipelineResult && appMode === 'pptx' && (
            <button
              className="btn btn-primary btn-lg"
              onClick={runFullPipeline}
              disabled={isProcessing}
              style={{ padding: '1rem 2rem', fontSize: '1.1rem' }}
            >
              {isProcessing ? (
                <>
                  <span className="spinner" />
                  処理中...
                </>
              ) : (
                <>🚀 ダブルループ学習で生成開始（目標: {targetSimilarity}%）</>
              )}
            </button>
          )}
          
          {pipelineResult && appMode === 'pptx' && (
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', justifyContent: 'center' }}>
              <button className="btn btn-outline" onClick={reset}>
                🔄 新しい画像を変換
              </button>
              <button className="btn btn-success" onClick={downloadPptx}>
                📥 PPTXをダウンロード
              </button>
              <button 
                className="btn btn-primary"
                onClick={runFullPipeline}
                disabled={isProcessing}
              >
                🔁 さらに品質向上を試行
              </button>
            </div>
          )}
        </div>
          </>
        )}
      </main>

      {/* Footer */}
      <footer style={{ 
        textAlign: 'center', 
        padding: '2rem', 
        color: 'var(--text-secondary)',
        fontSize: '0.85rem'
      }}>
        <p><strong>ダブルループ学習システム</strong> - Claude API による自動品質検証・修正</p>
        <p style={{ marginTop: '0.5rem' }}>
          生成 → 画像変換 → 比較検証 → AI分析 → 学習・再編集 を自動で繰り返し、高品質なPPTXを生成します
        </p>
      </footer>

      <style>{`
        .spinner-small {
          display: inline-block;
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .btn-lg {
          padding: 1rem 2rem !important;
          font-size: 1.1rem !important;
        }
      `}</style>
    </div>
  );
}

export default App;
