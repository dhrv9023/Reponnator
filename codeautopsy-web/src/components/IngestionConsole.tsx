import { useEffect, useState, useRef } from 'react';
import { apiClient } from '../api/client';
import { useJobPoller } from '../hooks/useJobPoller';

interface IngestionConsoleProps {
  repoUrl: string;
  onComplete: (repoKey: string) => void;
  onCancel?: () => void;
}

export default function IngestionConsole({ repoUrl, onComplete, onCancel }: IngestionConsoleProps) {
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState('Initializing pipeline...');
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const { pollJobStatus, stopPolling } = useJobPoller();

  // Helper to add timestamped console logs
  const addLog = (text: string) => {
    setLogs(prev => [...prev, text]);
  };

  useEffect(() => {
    const runPipeline = async () => {
      try {
        setError(null);
        setLogs([]);
        setProgress(0);
        setPhase('Connecting to server...');
        
        addLog(`🚀 Connecting to CodeAutopsy REST Gateway...`);
        
        // 1. Ingest Repo
        addLog(`📦 Phase 1: Creating ingestion job for: ${repoUrl}`);
        const ingestJob = await apiClient.ingestRepo(repoUrl);
        addLog(`⚡ Job queued successfully! Ingestion Job ID: ${ingestJob.job_id}`);
        const repoKey = await pollJobStatus(
          ingestJob.job_id,
          'ingest',
          (step) => { addLog(`[INGEST] ${step}`); setPhase(step); },
          setProgress
        );
        addLog(`✅ Ingestion completed! Local repository folder: data/repos/${repoKey}`);
        setProgress(30);
 
        // 2. Parse Repo
        addLog(`⚙️ Phase 2: Starting Abstract Syntax Tree (AST) parsing...`);
        const parseJob = await apiClient.parseRepo(repoKey);
        addLog(`⚡ Parse job queued! Job ID: ${parseJob.job_id}`);
        await pollJobStatus(
          parseJob.job_id,
          'parse',
          (step) => { addLog(`[PARSE] ${step}`); setPhase(step); },
          setProgress
        );
        addLog(`✅ Syntactic parsing complete! Call graph mappings saved.`);
        setProgress(55);
 
        // 3. Chunk & Embed Repo
        addLog(`🧠 Phase 3: Slicing code modules & vectorizing semantic tokens...`);
        const chunkJob = await apiClient.chunkRepo(repoKey);
        addLog(`⚡ Embedding job queued! Job ID: ${chunkJob.job_id}`);
        await pollJobStatus(
          chunkJob.job_id,
          'chunk',
          (step) => { addLog(`[CHUNK] ${step}`); setPhase(step); },
          setProgress
        );
        addLog(`✅ Semantic chunk index compiled inside local ChromaDB vector store.`);
        setProgress(80);
 
        // 4. Diagram & Narrative Story generation in parallel
        addLog(`🎨 Phase 6 & 7: Generating interactive diagram & architectural story...`);
        setPhase('Compiling visualization assets...');
        const [diagramJob, storyJob] = await Promise.all([
          apiClient.generateDiagram(repoKey),
          apiClient.generateStory(repoKey)
        ]);
 
        await Promise.all([
          pollJobStatus(
            diagramJob.job_id,
            'diagram',
            (step) => { addLog(`[DIAGRAM] ${step}`); setPhase(step); },
            setProgress
          ),
          pollJobStatus(
            storyJob.job_id,
            'story',
            (step) => { addLog(`[STORY] ${step}`); setPhase(step); },
            setProgress
          )
        ]);
        
        addLog(`🎉 Pipeline completed perfectly! Loading Workspace panel...`);
        setProgress(100);
        setPhase('Loading Workspace...');
 
        setTimeout(() => {
          onComplete(repoKey);
        }, 1200);
 
      } catch (err: any) {
        console.error(err);
        const errMsg = err.message || "An unexpected error occurred in the pipeline.";
        setError(errMsg);
        addLog(`❌ PIPELINE EXCEPTION: ${errMsg}`);
        setPhase('Pipeline failed');
      }
    };
 
    runPipeline();
 
    return () => {
      stopPolling();
    };
  }, [repoUrl, retryCount]);

  // Auto-scroll log console to bottom
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div
      className="glass shadow-xl fade-in"
      style={{
        width: '100%',
        maxWidth: '700px',
        background: 'var(--terminal-bg)',
        borderRadius: '16px',
        padding: '24px',
        color: 'var(--terminal-text)',
        fontFamily: 'var(--font-mono)',
        zIndex: 10,
        position: 'relative',
      }}
    >
      {/* Header bar */}
      <div
        style={{
          display:        'flex',
          alignItems:     'center',
          justifyContent: 'space-between',
          borderBottom:   '1px solid rgba(255,255,255,0.08)',
          paddingBottom:  '16px',
          marginBottom:   '20px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#ef4444' }} />
          <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#eab308' }} />
          <span style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: '#22c55e' }} />
          <span style={{ marginLeft: '12px', color: 'rgba(255,255,255,0.5)', fontSize: '14px', fontWeight: 500 }}>codeautopsy-terminal</span>
        </div>
        <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '12px', fontWeight: 500 }}>v1.0.0</span>
      </div>

      {/* Progress log stream */}
      <div
        ref={containerRef}
        className="custom-scrollbar"
        style={{
          height: '260px',
          overflowY: 'auto',
          fontSize: '13px',
          lineHeight: '1.7',
          marginBottom: '18px',
        }}
      >
        <div style={{ color: '#888', marginBottom: '10px', fontWeight: 500 }}>[INIT] Launching backend repository engine...</div>
        {logs.map((log, index) => (
          <div key={index} style={{ marginBottom: '6px', opacity: 0.95 }}>
            <span style={{ color: log.startsWith('❌') ? '#ef4444' : log.startsWith('✅') ? '#22c55e' : '#666', marginRight: '10px', fontWeight: 600 }}>&gt;</span>
            {log}
          </div>
        ))}
        {!error && <div className="cursor-blink" style={{ width: '8px', height: '16px', backgroundColor: 'var(--terminal-text)' }} />}
      </div>

      {/* Error state */}
      {error && (
        <div style={{ display: 'flex', gap: '12px', marginTop: '10px', marginBottom: '20px' }}>
          <button
            onClick={() => {
              setError(null);
              setLogs([]);
              setProgress(0);
              setPhase('Retrying pipeline...');
              setRetryCount(c => c + 1);
            }}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: '#ef4444',
              color: '#fff',
              border: 'none',
              fontWeight: 'bold',
              cursor: 'pointer',
              fontSize: '12px'
            }}
          >
            Retry Pipeline
          </button>
          {onCancel && (
            <button
              onClick={onCancel}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                backgroundColor: 'rgba(255,255,255,0.1)',
                color: 'var(--text-primary)',
                border: 'none',
                fontWeight: 'bold',
                cursor: 'pointer',
                fontSize: '12px'
              }}
            >
              Go Back
            </button>
          )}
        </div>
      )}

      {/* Progress indicator bar */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '18px' }}>
        <div
          style={{
            display:        'flex',
            justifyContent: 'space-between',
            alignItems:     'center',
            fontSize:       '13px',
            marginBottom:   '10px',
            color:          'rgba(255,255,255,0.7)',
            fontWeight:     500,
          }}
        >
          <span>{phase}</span>
          <span style={{ fontWeight: 600 }}>{progress}%</span>
        </div>
        <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '999px', overflow: 'hidden' }}>
          <div
            style={{
              width: `${progress}%`,
              height: '100%',
              background: error 
                ? 'linear-gradient(90deg, #ef4444, #b91c1c)' 
                : 'linear-gradient(90deg, var(--terminal-text), var(--accent-green))',
              transition: 'width 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
              borderRadius: '999px',
            }}
          />
        </div>
      </div>
    </div>
  );
}
