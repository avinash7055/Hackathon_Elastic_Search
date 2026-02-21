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
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import './Dashboard.css';

// Use the current origin in production, default to localhost for local dev
const API_BASE = window.location.origin.includes('localhost')
    ? 'http://localhost:8000'
    : window.location.origin;

const QUERY_SUGGESTIONS = [
    'Scan for any emerging drug safety signals in the last 90 days',
    'Investigate Cardizol-X for cardiac safety signals',
    'How many adverse events for Neurofen-Plus?',
    'What is PRR in pharmacovigilance?',
    'Generate safety report for Arthrex-200',
    'Show top drugs by adverse event count',
];

const STATUS_MESSAGES = [
    { icon: '🔍', text: 'Analyzing query...' },
    { icon: '🧠', text: 'Routing to specialized agent...' },
    { icon: '📡', text: 'Scanning Elasticsearch database...' },
    { icon: '⚡', text: 'Processing adverse event records...' },
    { icon: '📊', text: 'Computing statistical signals...' },
    { icon: '🔬', text: 'Investigating case patterns...' },
    { icon: '📝', text: 'Generating safety assessment...' },
    { icon: '✨', text: 'Compiling final report...' },
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
    const [displayedSteps, setDisplayedSteps] = useState([]);
    const [statusMessage, setStatusMessage] = useState(STATUS_MESSAGES[0]);
    const [streamedResponse, setStreamedResponse] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const wsRef = useRef(null);
    const messagesEndRef = useRef(null);
    const stepQueueRef = useRef([]);
    const revealTimerRef = useRef(null);
    const fullResponseRef = useRef('');
    const streamTimerRef = useRef(null);
    const userScrolledRef = useRef(false);
    const scrollContainerRef = useRef(null);
    const queuedCountRef = useRef(0);

    // Fetch health on mount
    useEffect(() => {
        fetch(`${API_BASE}/api/health`)
            .then(r => r.json())
            .then(setHealth)
            .catch(() => setHealth({ status: 'offline' }));
    }, []);

    // Track if user scrolled up manually
    useEffect(() => {
        const handleScroll = () => {
            const el = document.documentElement;
            const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
            // If user is more than 150px from bottom, they scrolled up manually
            userScrolledRef.current = distanceFromBottom > 150;
        };
        window.addEventListener('scroll', handleScroll, { passive: true });
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);

    // Smart auto-scroll: only scroll down if user hasn't scrolled up
    useEffect(() => {
        if (!userScrolledRef.current) {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [wsMessages, displayedSteps]);

    // Stream response word-by-word when directResponse arrives
    useEffect(() => {
        if (!directResponse || directResponse === fullResponseRef.current) return;

        // New response arrived — start streaming
        fullResponseRef.current = directResponse;
        setStreamedResponse('');
        setIsStreaming(true);

        // Clear any previous stream timer
        if (streamTimerRef.current) clearInterval(streamTimerRef.current);

        const words = directResponse.split(/( )/); // split keeping spaces
        let index = 0;

        streamTimerRef.current = setInterval(() => {
            // Reveal multiple chars at once for speed (chunk of ~3 words)
            const chunk = words.slice(index, index + 3).join('');
            index += 3;
            setStreamedResponse(prev => prev + chunk);

            if (index >= words.length) {
                clearInterval(streamTimerRef.current);
                streamTimerRef.current = null;
                setStreamedResponse(directResponse); // ensure full text
                setIsStreaming(false);
            }
        }, 20);

        return () => {
            if (streamTimerRef.current) clearInterval(streamTimerRef.current);
        };
    }, [directResponse]);

    // Drip-feed reasoning steps one-by-one
    useEffect(() => {
        if (reasoningSteps.length > queuedCountRef.current) {
            const newSteps = reasoningSteps.slice(queuedCountRef.current);
            stepQueueRef.current.push(...newSteps);
            queuedCountRef.current = reasoningSteps.length;

            if (!revealTimerRef.current) {
                const revealNext = () => {
                    if (stepQueueRef.current.length === 0) {
                        revealTimerRef.current = null;
                        return;
                    }
                    const next = stepQueueRef.current.shift();
                    setDisplayedSteps(prev => {
                        // Anti-duplicate safeguard
                        const exists = prev.some(p => p.content === next.content && p.timestamp === next.timestamp);
                        if (exists) return prev;
                        return [...prev, next];
                    });
                    revealTimerRef.current = setTimeout(revealNext, 400);
                };
                revealTimerRef.current = setTimeout(revealNext, 400);
            }
        }
    }, [reasoningSteps]);

    // Cycle status messages while active
    useEffect(() => {
        if (!isActiveStatus(status)) return;
        let idx = 0;
        const interval = setInterval(() => {
            idx = (idx + 1) % STATUS_MESSAGES.length;
            setStatusMessage(STATUS_MESSAGES[idx]);
        }, 3000);
        return () => clearInterval(interval);
    }, [status]);

    function isActiveStatus(s) {
        return s !== 'idle' && s !== 'complete' && s !== 'error';
    }

    const connectWebSocket = useCallback((investigationId) => {
        if (wsRef.current) wsRef.current.close();

        // Use wss:// in production natively when the page is https://
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.origin.includes('localhost') ? 'localhost:8000' : window.location.host;
        const ws = new WebSocket(`${wsProtocol}//${wsHost}/ws/progress/${investigationId}`);
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
        setDisplayedSteps([]);
        stepQueueRef.current = [];
        queuedCountRef.current = 0;
        if (revealTimerRef.current) { clearTimeout(revealTimerRef.current); revealTimerRef.current = null; }
        setSignals([]);
        setReports([]);
        setDirectResponse('');
        setStreamedResponse('');
        setIsStreaming(false);
        fullResponseRef.current = '';
        if (streamTimerRef.current) { clearInterval(streamTimerRef.current); streamTimerRef.current = null; }
        setRoute('');
        setSelectedReport(null);
        setShowSuggestions(false);
        setStatusMessage(STATUS_MESSAGES[0]);
        userScrolledRef.current = false;

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

    const handleDownloadPdf = async (report, index) => {
        const element = document.getElementById(`report-pdf-content-${index}`);
        if (!element) return;

        try {
            // Temporarily applying light theme or strict styling for PDF if needed
            // But we can stick to dark theme with high res scale
            const canvas = await html2canvas(element, {
                scale: 2,
                useCORS: true,
                backgroundColor: '#09090b', // match dark theme
                windowWidth: 800
            });
            const imgData = canvas.toDataURL('image/png');
            const pdf = new jsPDF('p', 'mm', 'a4');
            const pdfWidth = pdf.internal.pageSize.getWidth();
            const pdfHeight = (canvas.height * pdfWidth) / canvas.width;

            // If the content is longer than one page, jsPDF handles basic image stretching/scaling,
            // For a perfect multi-page, it's more complex, but for this hackathon, scrolling it into one scaled page or a long page is fine.
            pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
            pdf.save(`${report.drug_name}_Safety_Report.pdf`);
        } catch (error) {
            console.error("Error generating PDF", error);
        }
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

    const isActive = isActiveStatus(status);

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
                {/* Close suggestions on outside click */}
                {showSuggestions && (
                    <div className="suggestions-overlay" onClick={() => setShowSuggestions(false)} />
                )}

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
                            onKeyDown={e => {
                                if (e.key === 'Enter') { setShowSuggestions(false); handleInvestigate(); }
                                if (e.key === 'Escape') setShowSuggestions(false);
                            }}
                        />
                        <button
                            className="btn btn-primary btn-sm"
                            onClick={() => { setShowSuggestions(false); handleInvestigate(); }}
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

                {/* Dashboard Grid */}
                {status !== 'idle' && (
                    <div className="dash-grid anim-fade-in-up">
                        {/* Left Panel: Reasoning Trace */}
                        <div className="dash-panel reasoning-panel">
                            <div className="panel-header">
                                <FiCpu style={{ color: 'var(--accent-primary)' }} />
                                <span className="heading-sm">Agent Reasoning</span>
                                {isActive && <span className="spinner spinner-sm" />}
                                {displayedSteps.length > 0 && (
                                    <span className="badge badge-info" style={{ marginLeft: 'auto', fontSize: '0.65rem' }}>
                                        {displayedSteps.length} steps
                                    </span>
                                )}
                            </div>
                            <div className="panel-body">
                                {/* Status indicator */}
                                {investigation && (
                                    <div className="investigation-status">
                                        <div className="flex items-center gap-md">
                                            <span className="font-mono text-xs text-accent">
                                                {investigation.investigation_id?.slice(0, 8)}...
                                            </span>
                                            <span className={`badge ${status === 'complete' ? 'badge-low' : status === 'error' ? 'badge-critical' : 'badge-info'}`}>
                                                {status === 'complete' ? '✓ Complete' : status === 'error' ? '✗ Error' : '⟳ Processing'}
                                            </span>
                                        </div>
                                        {route && (
                                            <span className={`route-badge route-${route}`}>
                                                {{
                                                    full_scan: '🔍 Full Scan',
                                                    investigate: '🔬 Investigation',
                                                    report: '📝 Report',
                                                    data_query: '📊 Data Query',
                                                    general: '📚 Knowledge',
                                                    out_of_scope: '🔒 Out of Scope',
                                                }[route] || route}
                                            </span>
                                        )}
                                    </div>
                                )}

                                {/* Reasoning steps — revealed one by one */}
                                <div className="reasoning-list">
                                    {displayedSteps.map((step, i) => (
                                        <div
                                            key={i}
                                            className="reasoning-step step-reveal"
                                            style={{
                                                borderLeftColor: getAgentColor(step.agent),
                                                animationDelay: '0ms',
                                            }}
                                        >
                                            <div className="step-header">
                                                <span className="step-icon">{getStepIcon(step)}</span>
                                                <span className="step-agent" style={{ color: getAgentColor(step.agent) }}>
                                                    {(step.agent || '').replace(/_/g, ' ')}
                                                </span>
                                                <span className="step-type badge badge-info" style={{ fontSize: '0.6rem' }}>
                                                    {step.step_type}
                                                </span>
                                            </div>
                                            <div className="step-content">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                    {step.content}
                                                </ReactMarkdown>
                                            </div>
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

                                    {/* Typing indicator while agent is still working */}
                                    {isActive && (
                                        <div className="thinking-indicator glass-card-static anim-fade-in">
                                            <span className="typing-dots lg">
                                                <span /><span /><span />
                                            </span>
                                            <span className="text-xs text-muted">Agent is thinking...</span>
                                        </div>
                                    )}
                                    <div ref={messagesEndRef} />
                                </div>

                                {/* Direct Response */}
                                {(streamedResponse || directResponse) && (
                                    <div className="direct-response anim-fade-in-up">
                                        <div className="response-body">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {streamedResponse || directResponse}
                                            </ReactMarkdown>
                                            {isStreaming && <span className="stream-cursor">|</span>}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Right Panel: Signals & Reports */}
                        <div className="dash-panel results-panel">
                            {/* Detected Signals */}
                            <div className="results-section">
                                <div className="panel-header">
                                    <FiAlertTriangle style={{ color: 'var(--accent-warning)' }} />
                                    <span className="heading-sm">Detected Signals</span>
                                    {signals.length > 0 && (
                                        <span className="badge badge-high" style={{ marginLeft: 'auto' }}>{signals.length}</span>
                                    )}
                                </div>
                                <div className="panel-body">
                                    {signals.length === 0 ? (
                                        <div className="empty-state">
                                            <div className={`empty-state-icon signals-empty-icon ${isActive ? 'scanning-icon' : ''}`}>
                                                <FiAlertTriangle />
                                            </div>
                                            <div className="empty-state-title">
                                                {isActive ? 'Scanning for Signals...' : 'No Signals Detected'}
                                            </div>
                                            <div className="empty-state-desc">
                                                {isActive
                                                    ? 'Analyzing adverse event patterns across the FAERS database.'
                                                    : 'Run a full scan or drug investigation to detect safety signals.'}
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="signals-list">
                                            {signals.map((sig, i) => (
                                                <div
                                                    key={i}
                                                    className={`signal-card priority-${(sig.priority || 'low').toLowerCase()}`}
                                                >
                                                    <div className="signal-header">
                                                        <span className="signal-drug-name">{sig.drug_name}</span>
                                                        <span className={`badge ${getPriorityClass(sig.priority)}`}>
                                                            {sig.priority}
                                                        </span>
                                                    </div>
                                                    <div className="signal-reaction">
                                                        <span className="signal-reaction-arrow">→</span>
                                                        {sig.reaction_term}
                                                    </div>
                                                    <div className="signal-stats">
                                                        <div className="signal-stat">
                                                            <span className="signal-stat-label">PRR</span>
                                                            <span className={`signal-stat-value ${sig.prr > 5 ? 'stat-danger' : 'stat-warning'}`}>
                                                                {sig.prr > 100 ? '∞' : sig.prr?.toFixed(1)}
                                                            </span>
                                                        </div>
                                                        <div className="signal-stat">
                                                            <span className="signal-stat-label">Cases</span>
                                                            <span className="signal-stat-value stat-neutral">
                                                                {sig.case_count?.toLocaleString()}
                                                            </span>
                                                        </div>
                                                        <div className="signal-stat">
                                                            <span className="signal-stat-label">Spike</span>
                                                            <span className={`signal-stat-value ${sig.spike_ratio > 3 ? 'stat-danger' : 'stat-neutral'}`}>
                                                                {sig.spike_ratio?.toFixed(1)}×
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Safety Reports */}
                            <div className="results-section">
                                <div className="panel-header">
                                    <HiOutlineDocumentReport style={{ color: 'var(--accent-secondary)' }} />
                                    <span className="heading-sm">Safety Reports</span>
                                    {reports.length > 0 && (
                                        <span className="badge badge-low" style={{ marginLeft: 'auto' }}>{reports.length}</span>
                                    )}
                                </div>
                                <div className="panel-body">
                                    {reports.length === 0 ? (
                                        <div className="empty-state">
                                            <div className={`empty-state-icon reports-empty-icon ${isActive ? 'scanning-icon' : ''}`}>
                                                <HiOutlineDocumentReport />
                                            </div>
                                            <div className="empty-state-title">
                                                {isActive ? 'Generating Reports...' : 'No Reports Generated'}
                                            </div>
                                            <div className="empty-state-desc">
                                                {isActive
                                                    ? 'The Safety Reporter agent is compiling a structured assessment.'
                                                    : 'Signal detection pipeline will automatically generate MedWatch-style reports.'}
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="reports-list">
                                            {reports.map((rpt, i) => (
                                                <button
                                                    key={i}
                                                    className={`report-card ${selectedReport === i ? 'selected' : ''}`}
                                                    onClick={() => setSelectedReport(selectedReport === i ? null : i)}
                                                >
                                                    <div className="report-header">
                                                        <span style={{ fontWeight: 700 }}>{rpt.drug_name}</span>
                                                        <span className={`badge ${getPriorityClass(rpt.risk_level)}`}>
                                                            {rpt.risk_level}
                                                        </span>
                                                    </div>
                                                    <div className="text-sm text-secondary">{rpt.reaction_term}</div>
                                                    {selectedReport === i && rpt.report_markdown && (
                                                        <div className="report-content anim-fade-in" onClick={e => e.stopPropagation()}>
                                                            <div className="report-actions flex justify-between items-center" style={{ marginBottom: '1rem' }}>
                                                                <span className="badge badge-info text-xs">Formatted Markdown</span>
                                                                <button
                                                                    className="btn btn-sm btn-secondary"
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        handleDownloadPdf(rpt, i);
                                                                    }}
                                                                >
                                                                    Download PDF
                                                                </button>
                                                            </div>
                                                            <div id={`report-pdf-content-${i}`} className="report-markdown-formatted">
                                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                                    {rpt.report_markdown}
                                                                </ReactMarkdown>
                                                            </div>
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
