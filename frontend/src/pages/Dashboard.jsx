import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
    HiOutlineShieldCheck,
    HiOutlineDocumentReport,
} from 'react-icons/hi';
import {
    FiSearch,
    FiActivity,
    FiSend,
    FiLogOut,
    FiChevronDown,
    FiAlertTriangle,
    FiCpu,
    FiZap,
} from 'react-icons/fi';
import './Dashboard.css';

const API_BASE = 'http://localhost:8000';

const QUERY_SUGGESTIONS = [
    'Scan for any emerging drug safety signals in the last 90 days',
    'Investigate Cardizol-X for cardiac safety signals',
    'How many adverse events for Neurofen-Plus?',
    'What is PRR in pharmacovigilance?',
    'Generate safety report for Arthrex-200',
    'Show top drugs by adverse event count',
];

export default function Dashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const [health, setHealth] = useState(null);
    const [investigation, setInvestigation] = useState(null);
    const [wsMessages, setWsMessages] = useState([]);
    const [reasoningSteps, setReasoningSteps] = useState([]);
    const [signals, setSignals] = useState([]);
    const [reports, setReports] = useState([]);
    const [directResponse, setDirectResponse] = useState('');
    const [route, setRoute] = useState('');
    const [status, setStatus] = useState('idle');
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [showUserMenu, setShowUserMenu] = useState(false);
    const [selectedReport, setSelectedReport] = useState(null);
    const wsRef = useRef(null);
    const messagesEndRef = useRef(null);

    // Fetch health on mount
    useEffect(() => {
        fetch(`${API_BASE}/api/health`)
            .then(r => r.json())
            .then(setHealth)
            .catch(() => setHealth({ status: 'offline' }));
    }, []);

    // Auto-scroll messages
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [wsMessages, reasoningSteps]);

    const connectWebSocket = useCallback((investigationId) => {
        if (wsRef.current) wsRef.current.close();

        const ws = new WebSocket(`ws://localhost:8000/ws/progress/${investigationId}`);
        wsRef.current = ws;

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);

            if (msg.type === 'current_state') {
                const d = msg.data;
                setStatus(d.status);
                if (d.reasoning_trace) setReasoningSteps(d.reasoning_trace);
            }

            if (msg.type === 'progress') {
                const d = msg.data;

                if (d.type === 'reasoning' && d.steps) {
                    setReasoningSteps(prev => [...prev, ...d.steps]);
                    return;
                }

                if (d.status) setStatus(d.status);
                if (d.route) setRoute(d.route);
                if (d.direct_response) setDirectResponse(d.direct_response);

                setWsMessages(prev => [...prev, d]);

                if (d.status === 'complete' || d.status === 'error') {
                    // Fetch final investigation data
                    fetch(`${API_BASE}/api/investigations/${investigationId}`)
                        .then(r => r.json())
                        .then(inv => {
                            if (inv.signals) setSignals(inv.signals);
                            if (inv.reports) setReports(inv.reports);
                            if (inv.direct_response) setDirectResponse(inv.direct_response);
                            if (inv.reasoning_trace) setReasoningSteps(inv.reasoning_trace);
                        })
                        .catch(console.error);
                }
            }
        };

        ws.onerror = () => setStatus('error');
    }, []);

    const handleInvestigate = async () => {
        if (!query.trim()) return;

        // Reset state
        setStatus('starting');
        setWsMessages([]);
        setReasoningSteps([]);
        setSignals([]);
        setReports([]);
        setDirectResponse('');
        setRoute('');
        setSelectedReport(null);
        setShowSuggestions(false);

        try {
            const res = await fetch(`${API_BASE}/api/investigate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query.trim() }),
            });
            const data = await res.json();
            setInvestigation(data);
            setStatus(data.status);
            connectWebSocket(data.investigation_id);
        } catch (err) {
            setStatus('error');
            setWsMessages([{ node: 'error', status: 'error', error: err.message }]);
        }
    };

    const handleLogout = () => {
        logout();
        navigate('/');
    };

    const getStatusColor = () => {
        if (!health) return 'var(--text-muted)';
        return health.status === 'healthy' ? 'var(--accent-secondary)' : 'var(--accent-warning)';
    };

    const getStepIcon = (step) => {
        switch (step.step_type) {
            case 'thinking': return '💭';
            case 'tool_call': return '🔧';
            case 'tool_result': return '📊';
            case 'conclusion': return '✅';
            default: return '📌';
        }
    };

    const getAgentColor = (agent) => {
        switch (agent) {
            case 'master_orchestrator': return 'var(--accent-tertiary)';
            case 'signal_scanner': return 'var(--accent-primary)';
            case 'case_investigator': return 'var(--accent-warning)';
            case 'safety_reporter': return 'var(--accent-secondary)';
            case 'data_query': return 'var(--accent-primary)';
            default: return 'var(--text-muted)';
        }
    };

    const getPriorityClass = (priority) => {
        switch ((priority || '').toUpperCase()) {
            case 'CRITICAL': return 'badge-critical';
            case 'HIGH': return 'badge-high';
            case 'MEDIUM': return 'badge-medium';
            case 'LOW': return 'badge-low';
            default: return 'badge-info';
        }
    };

    const isActive = status !== 'idle' && status !== 'complete' && status !== 'error';

    return (
        <div className="dashboard">
            <div className="app-bg" />

            {/* ── Top Nav ──────────────── */}
            <nav className="dash-nav glass-card-static">
                <div className="dash-nav-inner">
                    <div className="flex items-center gap-md">
                        <div className="nav-logo" style={{ width: 34, height: 34, fontSize: '1rem' }}>
                            <HiOutlineShieldCheck />
                        </div>
                        <span className="nav-title" style={{ fontSize: '1rem' }}>PharmaVigil</span>
                        <span className="nav-badge">AI</span>
                    </div>

                    <div className="flex items-center gap-lg">
                        {/* Health indicator */}
                        <div className="health-indicator" style={{ color: getStatusColor() }}>
                            <FiActivity />
                            <span className="text-xs">
                                {health ? health.status : 'Checking...'}
                            </span>
                        </div>

                        {/* User menu */}
                        <div className="user-menu-wrapper">
                            <button
                                className="user-menu-btn"
                                onClick={() => setShowUserMenu(!showUserMenu)}
                            >
                                <div className="user-avatar">{user?.avatar || '?'}</div>
                                <span className="text-sm hide-mobile">{user?.name}</span>
                                <FiChevronDown />
                            </button>
                            {showUserMenu && (
                                <div className="user-dropdown glass-card anim-fade-in">
                                    <div className="dropdown-header">
                                        <div className="user-avatar" style={{ width: 36, height: 36, fontSize: '0.9rem' }}>
                                            {user?.avatar}
                                        </div>
                                        <div>
                                            <div className="text-sm" style={{ fontWeight: 600 }}>{user?.name}</div>
                                            <div className="text-xs text-muted">{user?.email}</div>
                                        </div>
                                    </div>
                                    <hr style={{ border: 'none', borderTop: '1px solid var(--glass-border)', margin: '0.5rem 0' }} />
                                    <button className="dropdown-item" onClick={handleLogout}>
                                        <FiLogOut /> Logout
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </nav>

            {/* ── Main Content ────────── */}
            <main className="dash-main">
                {/* Query Input */}
                <section className="query-section anim-fade-in-down">
                    <div className="query-bar glass-card-static">
                        <FiSearch className="query-icon" />
                        <input
                            className="query-input"
                            type="text"
                            placeholder="Ask about drug safety signals, investigate a drug, or query data..."
                            value={query}
                            onChange={e => setQuery(e.target.value)}
                            onFocus={() => setShowSuggestions(true)}
                            onKeyDown={e => e.key === 'Enter' && handleInvestigate()}
                        />
                        <button
                            className="btn btn-primary btn-sm"
                            onClick={handleInvestigate}
                            disabled={!query.trim() || isActive}
                        >
                            {isActive ? <span className="spinner spinner-sm" /> : <><FiSend /> Investigate</>}
                        </button>
                    </div>

                    {showSuggestions && !isActive && (
                        <div className="suggestions-dropdown glass-card anim-fade-in">
                            {QUERY_SUGGESTIONS.map((s, i) => (
                                <button
                                    key={i}
                                    className="suggestion-item"
                                    onClick={() => { setQuery(s); setShowSuggestions(false); }}
                                >
                                    <FiZap style={{ color: 'var(--accent-primary)', flexShrink: 0 }} />
                                    {s}
                                </button>
                            ))}
                        </div>
                    )}
                </section>

                {/* Close suggestions on outside click */}
                {showSuggestions && (
                    <div className="suggestions-overlay" onClick={() => setShowSuggestions(false)} />
                )}

                {/* Dashboard Grid */}
                {status !== 'idle' && (
                    <div className="dash-grid anim-fade-in-up">
                        {/* Left Panel: Reasoning Trace */}
                        <div className="dash-panel reasoning-panel">
                            <div className="panel-header glass-card-static">
                                <FiCpu style={{ color: 'var(--accent-primary)' }} />
                                <span className="heading-sm">Agent Reasoning</span>
                                {isActive && <span className="spinner spinner-sm" />}
                            </div>
                            <div className="panel-body">
                                {/* Status indicator */}
                                {investigation && (
                                    <div className="investigation-status glass-card-static">
                                        <div className="flex items-center gap-md">
                                            <span className="font-mono text-xs text-accent">{investigation.investigation_id}</span>
                                            <span className={`badge ${status === 'complete' ? 'badge-low' : status === 'error' ? 'badge-critical' : 'badge-info'}`}>
                                                {status}
                                            </span>
                                        </div>
                                        {route && <span className="text-xs text-muted">Route: {route}</span>}
                                    </div>
                                )}

                                {/* Reasoning steps */}
                                <div className="reasoning-list">
                                    {reasoningSteps.map((step, i) => (
                                        <div key={i} className="reasoning-step anim-fade-in" style={{ borderLeftColor: getAgentColor(step.agent) }}>
                                            <div className="step-header">
                                                <span className="step-icon">{getStepIcon(step)}</span>
                                                <span className="step-agent" style={{ color: getAgentColor(step.agent) }}>
                                                    {(step.agent || '').replace(/_/g, ' ')}
                                                </span>
                                                <span className="step-type badge badge-info" style={{ fontSize: '0.6rem' }}>
                                                    {step.step_type}
                                                </span>
                                            </div>
                                            <div className="step-content">{step.content}</div>
                                            {step.tool_name && (
                                                <div className="step-tool font-mono text-xs">
                                                    🛠️ {step.tool_name}
                                                </div>
                                            )}
                                            {step.tool_query && (
                                                <pre className="step-query font-mono text-xs">{step.tool_query}</pre>
                                            )}
                                            {step.tool_result && (
                                                <div className="step-result text-xs">{step.tool_result}</div>
                                            )}
                                        </div>
                                    ))}
                                    <div ref={messagesEndRef} />
                                </div>

                                {/* Direct Response */}
                                {directResponse && (
                                    <div className="direct-response glass-card-static anim-fade-in-up">
                                        <h4 className="heading-sm" style={{ marginBottom: 'var(--space-sm)' }}>
                                            💡 Response
                                        </h4>
                                        <div className="response-body">{directResponse}</div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Right Panel: Signals & Reports */}
                        <div className="dash-panel results-panel">
                            {/* Signals */}
                            <div className="results-section">
                                <div className="panel-header glass-card-static">
                                    <FiAlertTriangle style={{ color: 'var(--accent-warning)' }} />
                                    <span className="heading-sm">Detected Signals</span>
                                    {signals.length > 0 && (
                                        <span className="badge badge-high">{signals.length}</span>
                                    )}
                                </div>
                                <div className="panel-body">
                                    {signals.length === 0 ? (
                                        <div className="empty-state text-center">
                                            <FiAlertTriangle style={{ fontSize: '2rem', color: 'var(--text-muted)', marginBottom: 'var(--space-sm)' }} />
                                            <p className="text-sm text-muted">
                                                {isActive ? 'Scanning for signals...' : 'No signals detected yet'}
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="signals-list">
                                            {signals.map((sig, i) => (
                                                <div key={i} className="signal-card glass-card">
                                                    <div className="signal-header">
                                                        <span className="font-mono" style={{ fontWeight: 600 }}>{sig.drug_name}</span>
                                                        <span className={`badge ${getPriorityClass(sig.priority)}`}>
                                                            {sig.priority}
                                                        </span>
                                                    </div>
                                                    <div className="signal-reaction text-sm">→ {sig.reaction_term}</div>
                                                    <div className="signal-stats">
                                                        <div className="signal-stat">
                                                            <span className="text-xs text-muted">PRR</span>
                                                            <span className="font-mono" style={{ color: sig.prr > 5 ? 'var(--accent-danger)' : 'var(--accent-warning)' }}>
                                                                {sig.prr > 100 ? '∞' : sig.prr?.toFixed(1)}
                                                            </span>
                                                        </div>
                                                        <div className="signal-stat">
                                                            <span className="text-xs text-muted">Cases</span>
                                                            <span className="font-mono">{sig.case_count}</span>
                                                        </div>
                                                        <div className="signal-stat">
                                                            <span className="text-xs text-muted">Spike</span>
                                                            <span className="font-mono" style={{ color: sig.spike_ratio > 3 ? 'var(--accent-danger)' : 'var(--text-primary)' }}>
                                                                {sig.spike_ratio?.toFixed(1)}x
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Reports */}
                            <div className="results-section">
                                <div className="panel-header glass-card-static">
                                    <HiOutlineDocumentReport style={{ color: 'var(--accent-secondary)' }} />
                                    <span className="heading-sm">Safety Reports</span>
                                    {reports.length > 0 && (
                                        <span className="badge badge-low">{reports.length}</span>
                                    )}
                                </div>
                                <div className="panel-body">
                                    {reports.length === 0 ? (
                                        <div className="empty-state text-center">
                                            <HiOutlineDocumentReport style={{ fontSize: '2rem', color: 'var(--text-muted)', marginBottom: 'var(--space-sm)' }} />
                                            <p className="text-sm text-muted">
                                                {isActive ? 'Generating reports...' : 'No reports generated yet'}
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="reports-list">
                                            {reports.map((rpt, i) => (
                                                <button
                                                    key={i}
                                                    className={`report-card glass-card ${selectedReport === i ? 'selected' : ''}`}
                                                    onClick={() => setSelectedReport(selectedReport === i ? null : i)}
                                                >
                                                    <div className="report-header">
                                                        <span style={{ fontWeight: 600 }}>{rpt.drug_name}</span>
                                                        <span className={`badge ${getPriorityClass(rpt.risk_level)}`}>
                                                            {rpt.risk_level}
                                                        </span>
                                                    </div>
                                                    <div className="text-sm text-secondary">{rpt.reaction_term}</div>
                                                    {selectedReport === i && rpt.report_markdown && (
                                                        <div className="report-content anim-fade-in">
                                                            <pre className="report-markdown">{rpt.report_markdown}</pre>
                                                        </div>
                                                    )}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Welcome state */}
                {status === 'idle' && (
                    <div className="welcome-state anim-fade-in-up">
                        <div className="welcome-content glass-card-static">
                            <div className="welcome-icon anim-float">
                                <HiOutlineShieldCheck />
                            </div>
                            <h2 className="heading-md">Welcome to PharmaVigil AI</h2>
                            <p className="text-secondary" style={{ maxWidth: 480, margin: '0 auto', lineHeight: 1.7 }}>
                                Start by typing a query above. You can scan for safety signals,
                                investigate specific drugs, ask data questions, or request safety reports.
                            </p>
                            <div className="welcome-suggestions">
                                {QUERY_SUGGESTIONS.slice(0, 3).map((s, i) => (
                                    <button
                                        key={i}
                                        className="welcome-suggestion glass-card"
                                        onClick={() => setQuery(s)}
                                    >
                                        <FiZap style={{ color: 'var(--accent-primary)' }} />
                                        <span className="text-sm">{s}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
