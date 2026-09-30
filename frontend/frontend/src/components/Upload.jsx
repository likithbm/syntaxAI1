import React, { useRef, useState } from 'react';
import { Button, Card, ErrorBanner } from './ui.jsx';

export default function Upload({ image, onFile, onAnalyze, error, onDismissError, health }) {
  const inputRef = useRef(null);
  const [drag, setDrag] = useState(false);
  const notReady = health && health.ok && !health.bedrock_configured && !health.fixture_mode;
  return (
    <div>
      <ErrorBanner error={error} onRetry={image ? onAnalyze : null} onDismiss={onDismissError} />
      {health && !health.ok && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          The backend is not reachable. Start it with <code className="mono">python local_server.py</code> (see README).
        </div>
      )}
      {notReady && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          Bedrock is not configured on the backend, so image analysis will fail. Set <code className="mono">BEDROCK_MODEL_ID</code> and AWS credentials (see README).
        </div>
      )}
      {health && health.fixture_mode && (
        <div className="mb-4 rounded-lg border border-violet-300 bg-violet-50 p-3 text-sm text-violet-900">
          Offline fixture mode: the backend returns a canned analysis instead of calling Bedrock. Everything after analysis is real.
        </div>
      )}
      <Card title="Upload your architecture diagram" subtitle="PNG or JPG: architecture diagram, whiteboard photo or sketch. Nothing is generated until you have reviewed and confirmed the detected architecture.">
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files && e.dataTransfer.files[0]; if (f) onFile(f); }}
          onClick={() => inputRef.current && inputRef.current.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current && inputRef.current.click(); }}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${drag ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 hover:border-indigo-400 hover:bg-slate-50'}`}
        >
          <input ref={inputRef} type="file" accept="image/png,image/jpeg" className="hidden" data-testid="file-input"
            onChange={(e) => { const f = e.target.files && e.target.files[0]; if (f) onFile(f); e.target.value = ''; }} />
          {image ? (
            <>
              <img src={image.dataUrl} alt="Uploaded architecture diagram preview" className="max-h-72 rounded-lg border border-slate-200 object-contain" />
              <p className="mt-3 text-sm font-medium text-slate-700">{image.name}</p>
              <p className="text-xs text-slate-500">
                {image.width} x {image.height}px, {(image.bytes / 1024).toFixed(0)} KB{image.resized ? ' (resized in your browser to speed up analysis)' : ''} - click to choose a different image
              </p>
            </>
          ) : (
            <>
              <div className="text-4xl" aria-hidden="true">🗺️</div>
              <p className="mt-2 text-sm font-medium text-slate-700">Drop an image here, or click to browse</p>
              <p className="text-xs text-slate-500">PNG, JPG or JPEG</p>
            </>
          )}
        </div>
        <div className="mt-4 flex justify-end">
          <Button variant="primary" disabled={!image} onClick={onAnalyze}>Analyze architecture</Button>
        </div>
      </Card>
    </div>
  );
}
