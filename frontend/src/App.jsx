import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { ShieldCheck, ServerCrash, Cpu, Activity, GitBranch } from 'lucide-react';
import './index.css';

function App() {
  const [url, setUrl] = useState('');
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState('IDLE'); // IDLE, PENDING, IN_PROGRESS, COMPLETED, FAILED
  const [report, setReport] = useState('');

  const startScan = async () => {
    if (!url) return;
    setStatus('PENDING');
    try {
      const res = await fetch('http://localhost:8000/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: url })
      });
      const data = await res.json();
      setJobId(data.job_id);
    } catch (e) {
      console.error(e);
      setStatus('FAILED');
    }
  };

  useEffect(() => {
    if (!jobId || status === 'COMPLETED' || status === 'FAILED') return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/status/${jobId}`);
        const data = await res.json();
        
        setStatus(data.status);

        if (data.status === 'COMPLETED') {
          const reportRes = await fetch(`http://localhost:8000/api/report/${jobId}`);
          if (!reportRes.ok) {
              setStatus('FAILED');
              return;
          }
          const reportData = await reportRes.json();
          setReport(reportData.report || 'No report generated.');
        }
      } catch (e) {
        console.error(e);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [jobId, status]);

  return (
    <div style={{ padding: '4rem 2rem', maxWidth: '1000px', margin: '0 auto', textAlign: 'center', width: '100%' }}>
      <ShieldCheck size={64} color="#58a6ff" style={{ margin: '0 auto 1rem' }} />
      <h1>SQA-MAS Engine</h1>
      <p style={{ fontSize: '1.2rem', color: '#8b949e', marginBottom: '3rem' }}>
        Automated AI Quality Assurance Team. Paste a GitHub repository below to unleash 5 parallel LLM agents.
      </p>

      {status === 'IDLE' && (
        <div className="glass-panel" style={{ padding: '2rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <GitBranch size={24} color="#8b949e" />
          <input
            className="glass-input"
            style={{ flex: 1 }}
            placeholder="https://github.com/username/repository.git"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button className="primary-button" onClick={startScan} disabled={!url}>
            Scan Repository
          </button>
        </div>
      )}

      {(status === 'PENDING' || status === 'IN_PROGRESS') && (
        <div className="glass-panel" style={{ padding: '4rem 2rem', marginTop: '2rem' }}>
          <div className="spinner" style={{ marginBottom: '1rem', width: '48px', height: '48px' }}></div>
          <h2 className="animate-pulse">Agents are analyzing code...</h2>
          <p style={{ color: '#8b949e' }}>
            Spinning up Docker containers, executing unit tests, and running LLM diagnostics via Groq.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '2rem', marginTop: '2rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: '#58a6ff' }}>
               <Activity size={32} />
               <small>Code Analysis</small>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: '#2ea043' }}>
               <ShieldCheck size={32} />
               <small>Regression</small>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: '#d29922' }}>
               <ServerCrash size={32} />
               <small>Sanity Check</small>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: '#f85149' }}>
               <Cpu size={32} />
               <small>Logic Validation</small>
            </div>
          </div>
        </div>
      )}

      {status === 'FAILED' && (
        <div className="glass-panel" style={{ padding: '2rem', marginTop: '2rem', border: '1px solid #f85149' }}>
          <h2 style={{ color: '#f85149' }}>Pipeline Failed</h2>
          <p>The orchestrator encountered a fatal error.</p>
          <button className="primary-button" onClick={() => setStatus('IDLE')} style={{ marginTop: '1rem' }}>Try Again</button>
        </div>
      )}

      {status === 'COMPLETED' && report && (
        <div className="glass-panel markdown-body" style={{ marginTop: '2rem' }}>
          <ReactMarkdown>{report}</ReactMarkdown>
          <div style={{ textAlign: 'center', marginTop: '2rem' }}>
            <button className="primary-button" onClick={() => { setStatus('IDLE'); setUrl(''); setReport(''); }}>
              Scan Another Repository
            </button>
          </div>
        </div>
      )}

    </div>
  );
}

export default App;
