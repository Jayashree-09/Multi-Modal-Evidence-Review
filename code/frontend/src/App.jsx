import { useState, useEffect, useRef } from 'react';
import './App.css';

const API_BASE = window.location.origin === 'http://localhost:5173' ? 'http://localhost:8000' : '';

function App() {
  const [activeTab, setActiveTab] = useState('verify');
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'light');
  const [apiKey, setApiKey] = useState(localStorage.getItem('gemini_api_key') || '');
  
  // Claim Form State
  const [userId, setUserId] = useState('');
  const [claimObject, setClaimObject] = useState('car');
  const [userClaim, setUserClaim] = useState('');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState(null);
  
  // Data lists
  const [history, setHistory] = useState([]);
  const [users, setUsers] = useState({});
  const [evidenceRules, setEvidenceRules] = useState([]);
  const [userSearch, setUserSearch] = useState('');
  
  // Batch states
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [batchResult, setBatchResult] = useState(null);
  
  // Evaluation states
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evalScores, setEvalScores] = useState(null);

  // File input ref
  const fileInputRef = useRef(null);

  // Sync theme
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Fetch initial data
  useEffect(() => {
    fetchHistory();
    fetchUsers();
    fetchRules();
  }, []);

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/history`);
      if (res.ok) {
        const data = await res.json();
        setHistory(data);
      }
    } catch (e) {
      console.error('Failed to fetch history:', e);
    }
  };

  const fetchUsers = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/user-history`);
      if (res.ok) {
        const data = await res.json();
        setUsers(data);
      }
    } catch (e) {
      console.error('Failed to fetch user history:', e);
    }
  };

  const fetchRules = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/evidence-requirements`);
      if (res.ok) {
        const data = await res.json();
        setEvidenceRules(data);
      }
    } catch (e) {
      console.error('Failed to fetch evidence rules:', e);
    }
  };

  const handleThemeToggle = () => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  };

  const handleApiKeyChange = (e) => {
    const key = e.target.value;
    setApiKey(key);
    localStorage.setItem('gemini_api_key', key);
  };

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    setSelectedFiles((prev) => [...prev, ...files]);
    
    const filePreviews = files.map((file) => URL.createObjectURL(file));
    setPreviews((prev) => [...prev, ...filePreviews]);
  };

  const handleRemoveFile = (index) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviews((prev) => {
      // Revoke the object URL to avoid memory leaks
      URL.revokeObjectURL(prev[index]);
      return prev.filter((_, i) => i !== index);
    });
  };

  const handleSubmitClaim = async (e) => {
    e.preventDefault();
    if (!userId.trim()) return alert('Please enter a User ID');
    if (!userClaim.trim()) return alert('Please describe the claim');
    if (selectedFiles.length === 0) return alert('Please upload at least one image');

    setIsVerifying(true);
    setVerificationResult(null);

    const formData = new FormData();
    formData.append('user_id', userId.trim());
    formData.append('claim_object', claimObject);
    formData.append('user_claim', userClaim.trim());
    selectedFiles.forEach((file) => {
      formData.append('images', file);
    });

    const headers = {};
    if (apiKey) {
      headers['X-Gemini-API-Key'] = apiKey;
    }

    try {
      const res = await fetch(`${API_BASE}/api/verify`, {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to verify claim');
      }

      const result = await res.json();
      setVerificationResult(result);
      // Reset form
      setUserId('');
      setUserClaim('');
      setSelectedFiles([]);
      setPreviews([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
      
      // Refresh history & users list
      fetchHistory();
      fetchUsers();
    } catch (err) {
      alert(err.message);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleRunBatch = async () => {
    setIsBatchRunning(true);
    setBatchResult(null);
    
    const headers = {};
    if (apiKey) {
      headers['X-Gemini-API-Key'] = apiKey;
    }

    try {
      const res = await fetch(`${API_BASE}/api/batch-verify`, {
        method: 'POST',
        headers,
      });

      if (!res.ok) {
        throw new Error('Batch verification failed');
      }

      const data = await res.json();
      setBatchResult(data);
      fetchHistory();
    } catch (e) {
      alert(e.message);
    } finally {
      setIsBatchRunning(false);
    }
  };

  const handleRunEvaluation = async () => {
    setIsEvaluating(true);
    setEvalScores(null);

    const headers = {};
    if (apiKey) {
      headers['X-Gemini-API-Key'] = apiKey;
    }

    try {
      const res = await fetch(`${API_BASE}/api/evaluate`, {
        method: 'POST',
        headers,
      });

      if (!res.ok) {
        throw new Error('Evaluation pipeline execution failed');
      }

      const data = await res.json();
      setEvalScores(data.scores || data);
    } catch (e) {
      alert(e.message);
    } finally {
      setIsEvaluating(false);
    }
  };

  // Filter users based on search
  const filteredUsers = Object.entries(users).filter(([id]) => 
    id.toLowerCase().includes(userSearch.toLowerCase())
  );

  return (
    <div className="app-container">
      {/* Dynamic Glassmorphic Navbar */}
      <header className="navbar glass">
        <div className="nav-logo">
          <svg className="logo-icon animate-pulse" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            <path d="M9 11l2 2 4-4"/>
          </svg>
          <span className="logo-text">VerifiClaim <span className="logo-accent">AI</span></span>
        </div>
        <div className="nav-actions">
          {/* Gemini API Key input */}
          <div className="api-key-input">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            <input 
              type="password" 
              placeholder="Enter Gemini API Key (Optional)..." 
              value={apiKey} 
              onChange={handleApiKeyChange}
              title="Leave empty to use local fallback heuristics"
            />
          </div>
          
          <button className="btn-icon theme-toggle" onClick={handleThemeToggle} title="Toggle Theme">
            {theme === 'light' ? (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
            )}
          </button>
          
          <div className="nav-profile">
            <span className="role-badge badge badge-primary">Admin / Evaluator</span>
          </div>
        </div>
      </header>

      {/* Main Tab bar */}
      <div className="tabs-container">
        <button className={`tab-btn ${activeTab === 'verify' ? 'active' : ''}`} onClick={() => setActiveTab('verify')}>
          Verify Claims
        </button>
        <button className={`tab-btn ${activeTab === 'batch' ? 'active' : ''}`} onClick={() => setActiveTab('batch')}>
          Batch Verification
        </button>
        <button className={`tab-btn ${activeTab === 'evaluate' ? 'active' : ''}`} onClick={() => setActiveTab('evaluate')}>
          Model Evaluation
        </button>
        <button className={`tab-btn ${activeTab === 'users' ? 'active' : ''}`} onClick={() => setActiveTab('users')}>
          User Profiles
        </button>
        <button className={`tab-btn ${activeTab === 'rules' ? 'active' : ''}`} onClick={() => setActiveTab('rules')}>
          Evidence Checklist
        </button>
      </div>

      {/* Tab Panels */}
      <main className="main-content animate-fade-in">
        {activeTab === 'verify' && (
          <div className="verify-grid">
            {/* Left Form Panel */}
            <section className="card form-card">
              <h2 className="section-title">Submit New Claim</h2>
              <form onSubmit={handleSubmitClaim} className="claim-form">
                
                <div className="input-group">
                  <label htmlFor="user-id">User ID</label>
                  <input
                    id="user-id"
                    type="text"
                    className="input"
                    placeholder="e.g., user_001"
                    value={userId}
                    onChange={(e) => setUserId(e.target.value)}
                    list="user-suggestions"
                    required
                  />
                  <datalist id="user-suggestions">
                    {Object.keys(users).map(id => (
                      <option key={id} value={id} />
                    ))}
                  </datalist>
                </div>

                <div className="input-group">
                  <label htmlFor="claim-object">Claim Object Type</label>
                  <select
                    id="claim-object"
                    className="select"
                    value={claimObject}
                    onChange={(e) => setClaimObject(e.target.value)}
                  >
                    <option value="car">Car</option>
                    <option value="laptop">Laptop</option>
                    <option value="package">Package</option>
                  </select>
                </div>

                <div className="input-group">
                  <label htmlFor="user-claim">Chat Conversation / Claim Details</label>
                  <textarea
                    id="user-claim"
                    className="textarea"
                    placeholder="Provide details or paste user chat history..."
                    value={userClaim}
                    onChange={(e) => setUserClaim(e.target.value)}
                    required
                  ></textarea>
                </div>

                <div className="input-group">
                  <label>Submitted Evidence (Images)</label>
                  <div 
                    className="upload-dropzone" 
                    onClick={() => fileInputRef.current && fileInputRef.current.click()}
                  >
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    <span>Click or drag files to upload claim images</span>
                    <input
                      type="file"
                      ref={fileInputRef}
                      style={{ display: 'none' }}
                      multiple
                      accept="image/*"
                      onChange={handleFileChange}
                    />
                  </div>
                  
                  {previews.length > 0 && (
                    <div className="previews-grid">
                      {previews.map((preview, index) => (
                        <div key={index} className="preview-item">
                          <img src={preview} alt={`upload preview ${index}`} />
                          <button 
                            type="button" 
                            className="remove-preview-btn" 
                            onClick={() => handleRemoveFile(index)}
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <button 
                  type="submit" 
                  className="btn btn-primary submit-btn" 
                  disabled={isVerifying}
                >
                  {isVerifying ? (
                    <>
                      <div className="spinner"></div>
                      <span>Verifying claim...</span>
                    </>
                  ) : 'Run Verification Review'}
                </button>
              </form>
            </section>

            {/* Right Display Panel */}
            <section className="card result-card">
              <h2 className="section-title">Analysis & Review Panel</h2>
              
              {/* Fresh Verification Result */}
              {verificationResult ? (
                <div className="result-display animate-slide-in">
                  <div className="result-header">
                    <span className={`status-pill badge ${
                      verificationResult.claim_status === 'supported' ? 'badge-success' :
                      verificationResult.claim_status === 'contradicted' ? 'badge-danger' : 'badge-warning'
                    }`}>
                      Claim {verificationResult.claim_status}
                    </span>
                    <span className="severity-pill badge badge-info">
                      Severity: {verificationResult.severity}
                    </span>
                  </div>

                  <div className="result-grid-metrics">
                    <div className="metric-box">
                      <label>Detected Object Part</label>
                      <span className="metric-value">{verificationResult.object_part}</span>
                    </div>
                    <div className="metric-box">
                      <label>Damage Issue Type</label>
                      <span className="metric-value">{verificationResult.issue_type}</span>
                    </div>
                    <div className="metric-box">
                      <label>Evidence Met</label>
                      <span className={`metric-value ${verificationResult.evidence_standard_met === 'true' ? 'text-success' : 'text-danger'}`}>
                        {verificationResult.evidence_standard_met === 'true' ? 'MET' : 'UNMET'}
                      </span>
                    </div>
                    <div className="metric-box">
                      <label>Image Usability</label>
                      <span className="metric-value">{verificationResult.valid_image === 'true' ? 'Usable' : 'Unusable'}</span>
                    </div>
                  </div>

                  <div className="result-section">
                    <h4>Evidence Standard Reason</h4>
                    <p>{verificationResult.evidence_standard_met_reason}</p>
                  </div>

                  <div className="result-section">
                    <h4>Claim Status Justification</h4>
                    <p className="justification-text">{verificationResult.claim_status_justification}</p>
                  </div>

                  <div className="result-section">
                    <h4>Active Risk Flags</h4>
                    <div className="risk-flags-container">
                      {verificationResult.risk_flags.split(';').map((flag) => (
                        <span 
                          key={flag} 
                          className={`badge ${flag === 'none' ? 'badge-primary' : 'badge-danger'}`}
                        >
                          {flag.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="result-section">
                    <h4>Supporting Evidence Image IDs</h4>
                    <code>{verificationResult.supporting_image_ids}</code>
                  </div>
                </div>
              ) : (
                <div className="no-result">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="16" x2="12" y2="12" />
                    <line x1="12" y1="8" x2="12.01" y2="8" />
                  </svg>
                  <p>Submit a claim on the left to begin automated multi-modal evidence review.</p>
                </div>
              )}
            </section>
          </div>
        )}

        {activeTab === 'batch' && (
          <div className="batch-container card">
            <h2 className="section-title">Batch Claims Processing Dashboard</h2>
            <p className="tab-description">
              Process all claims in `dataset/claims.csv` in batch mode, save predictions to `output.csv`, and review total counts.
            </p>

            <div className="batch-status-panel">
              <div className="batch-info-grid">
                <div className="info-box">
                  <span className="info-label">Input Target</span>
                  <span className="info-val">dataset/claims.csv</span>
                </div>
                <div className="info-box">
                  <span className="info-label">Output Target</span>
                  <span className="info-val">output.csv</span>
                </div>
                <div className="info-box">
                  <span className="info-label">Processing Mode</span>
                  <span className="info-val">{apiKey ? 'Google Gemini API' : 'Rule-Based Fallback (Offline)'}</span>
                </div>
              </div>

              {isBatchRunning ? (
                <div className="batch-progress">
                  <div className="spinner spinner-lg"></div>
                  <p>Verifying all damage claims batch... Please wait.</p>
                </div>
              ) : (
                <div className="batch-actions">
                  <button onClick={handleRunBatch} className="btn btn-primary btn-lg">
                    Execute Batch Verification Run
                  </button>
                </div>
              )}

              {batchResult && (
                <div className="batch-result-alert animate-fade-in">
                  <div className="alert-header">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    <h3>Batch Completed Successfully!</h3>
                  </div>
                  <p>Processed **{batchResult.rows_processed}** claims in total.</p>
                  <p>Results written directly to `output.csv` inside the repository workspace root.</p>
                </div>
              )}
            </div>

            {/* Batch History listing */}
            <div className="history-section">
              <h3>Latest Verified Claims History</h3>
              {history.length > 0 ? (
                <div className="history-table-container">
                  <table className="history-table">
                    <thead>
                      <tr>
                        <th>User ID</th>
                        <th>Object</th>
                        <th>Standard Met</th>
                        <th>Status</th>
                        <th>Detected Issue</th>
                        <th>Severity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.slice(0, 10).map((claim, idx) => (
                        <tr key={claim.id || idx}>
                          <td>{claim.user_id}</td>
                          <td><span className="badge badge-primary">{claim.claim_object}</span></td>
                          <td>
                            <span className={claim.evidence_standard_met === 'true' ? 'text-success' : 'text-danger'}>
                              {claim.evidence_standard_met === 'true' ? 'Yes' : 'No'}
                            </span>
                          </td>
                          <td>
                            <span className={`status-${claim.claim_status}`}>
                              {claim.claim_status}
                            </span>
                          </td>
                          <td>{claim.issue_type} ({claim.object_part})</td>
                          <td><span className="badge badge-info">{claim.severity}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="no-history">No claim records processed in this session yet.</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'evaluate' && (
          <div className="evaluate-container grid-two-col">
            <section className="card">
              <h2 className="section-title">Model Evaluation Pipeline</h2>
              <p className="tab-description">
                Evaluate system accuracy against labeled ground truth in `dataset/sample_claims.csv`.
              </p>

              {isEvaluating ? (
                <div className="evaluate-loading">
                  <div className="spinner spinner-lg"></div>
                  <p>Running pipeline and grading predictions... This will take a few seconds.</p>
                </div>
              ) : (
                <button onClick={handleRunEvaluation} className="btn btn-primary btn-lg evaluate-btn">
                  Execute Evaluation Suite
                </button>
              )}

              {evalScores && (
                <div className="scores-display animate-slide-in">
                  <h3>Accuracy Summary Metrics</h3>
                  <div className="overall-score">
                    <span className="overall-label">Overall Match Accuracy</span>
                    <span className="overall-val">{(evalScores.overall.accuracy * 100).toFixed(1)}%</span>
                  </div>

                  <div className="scores-bars">
                    {Object.entries(evalScores).map(([field, data]) => {
                      if (field === 'overall') return null;
                      return (
                        <div key={field} className="bar-group">
                          <div className="bar-labels">
                            <span className="field-name">{field.replace(/_/g, ' ')}</span>
                            <span className="field-acc">{(data.accuracy * 100).toFixed(1)}% ({data.correct}/{data.total})</span>
                          </div>
                          <div className="progress-bar-bg">
                            <div className="progress-bar-fill" style={{ width: `${data.accuracy * 100}%` }}></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </section>

            <section className="card report-card">
              <h2 className="section-title">Operational Analysis</h2>
              <div className="report-markdown-preview">
                <h3>VLM Evaluation & Operations Report</h3>
                <hr />
                <ul>
                  <li><strong>Models Checked:</strong> Google Gemini 1.5 Flash (vision + text model context)</li>
                  <li><strong>Image Count/Limit:</strong> Batches all claim images into a single model input call to minimize token and RPM costs.</li>
                  <li><strong>Throttling Strategy:</strong> Implements a 2-second delay between calls and exponential retry logic on rate limits (HTTP 429).</li>
                  <li><strong>Offline Integrity:</strong> Fully compatible with local rule fallback parsing to guarantee 100% service uptime.</li>
                </ul>
              </div>
            </section>
          </div>
        )}

        {activeTab === 'users' && (
          <div className="users-container card">
            <div className="users-header">
              <h2 className="section-title">User Claims Registry & Risk Patterns</h2>
              <input 
                type="text" 
                className="input user-search"
                placeholder="Search registry by User ID..."
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
              />
            </div>

            <div className="users-table-container">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>User ID</th>
                    <th>Past Claims</th>
                    <th>Accepted</th>
                    <th>Manual Review</th>
                    <th>Rejected</th>
                    <th>Last 90 Days</th>
                    <th>History Flags</th>
                    <th>Profile Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map(([id, info]) => (
                    <tr key={id} className={info.history_flags !== 'none' ? 'user-row-warning' : ''}>
                      <td><strong>{id}</strong></td>
                      <td>{info.past_claim_count}</td>
                      <td><span className="text-success">{info.accept_claim}</span></td>
                      <td><span className="text-warning">{info.manual_review_claim}</span></td>
                      <td><span className="text-danger">{info.rejected_claim}</span></td>
                      <td>{info.last_90_days_claim_count}</td>
                      <td>
                        <span className={`badge ${info.history_flags === 'none' ? 'badge-primary' : 'badge-danger'}`}>
                          {info.history_flags}
                        </span>
                      </td>
                      <td>{info.history_summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'rules' && (
          <div className="rules-container card">
            <h2 className="section-title">Visual Evidence Standards & Guidelines</h2>
            <p className="tab-description">
              Rules defined in `evidence_requirements.csv` detail the minimum required image standards needed to evaluate claims by object and issue family.
            </p>

            <div className="rules-table-container">
              <table className="rules-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Object Category</th>
                    <th>Applies To</th>
                    <th>Minimum Required Visual Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {evidenceRules.map((rule, idx) => (
                    <tr key={rule.requirement_id || idx}>
                      <td><code>{rule.requirement_id}</code></td>
                      <td><span className="badge badge-primary">{rule.claim_object}</span></td>
                      <td><strong>{rule.applies_to}</strong></td>
                      <td>{rule.minimum_image_evidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
