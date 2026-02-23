import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
    HiOutlineShieldCheck,
    HiOutlineDocumentReport,
} from 'react-icons/hi';
import {
    FiSend,
    FiLogOut,
    FiChevronDown,
    FiAlertTriangle,
    FiCpu,
    FiZap,
    FiChevronUp,
    FiDownload,
    FiActivity,
    FiTrash2,
    FiMoreVertical,
} from 'react-icons/fi';
import { RiRobotLine, RiUserLine } from 'react-icons/ri';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import './Dashboard.css';

const API_BASE = window.location.origin.includes('localhost')
    ? 'http://localhost:8000'
    : window.location.origin;

const QUERY_SUGGESTIONS = [
    'Scan for emerging drug safety signals',
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

const ROUTE_LABELS = {
    full_scan: { label: '🔍 Full Scan', color: 'var(--accent-primary)' },
    investigate: { label: '🔬 Investigation', color: 'var(--accent-tertiary)' },
    report: { label: '📝 Report', color: 'var(--accent-secondary)' },
    data_query: { label: '📊 Data Query', color: '#38bdf8' },
    general: { label: '📚 Knowledge', color: '#34d399' },
    out_of_scope: { label: '🔒 Out of Scope', color: '#fb923c' },
};

function getAgentColor(agent) {
    switch (agent) {
        case 'master_orchestrator': return 'var(--accent-tertiary)';
        case 'signal_scanner': return 'var(--accent-primary)';
        case 'case_investigator': return 'var(--accent-warning)';
        case 'safety_reporter': return 'var(--accent-secondary)';
        case 'data_query': return '#38bdf8';
        default: return 'var(--text-muted)';
    }
}

function getStepIcon(step) {
    switch (step.step_type) {
        case 'thinking': return '💭';
        case 'tool_call': return '🔧';
        case 'tool_result': return '📊';
        case 'conclusion': return '✅';
        default: return '📌';
    }
}

function getPriorityClass(priority) {
    switch ((priority || '').toUpperCase()) {
        case 'CRITICAL': return 'badge-critical';
        case 'HIGH': return 'badge-high';
        case 'MEDIUM': return 'badge-medium';
        case 'LOW': return 'badge-low';
        default: return 'badge-info';
    }
}

/* ─── Reasoning Steps (collapsible) ─────────────────────────────── */
function ReasoningSection({ steps, isActive }) {
    const [collapsed, setCollapsed] = useState(false);
    if (steps.length === 0 && !isActive) return null;

    return (
        <div className="chat-reasoning-section">
            <button className="chat-reasoning-toggle" onClick={() => setCollapsed(c => !c)}>
                <FiCpu style={{ color: 'var(--accent-primary)', fontSize: '0.8rem' }} />
                <span>Agent Reasoning</span>
                <span className="reasoning-count-badge">{steps.length} steps</span>
                {isActive && <span className="reasoning-live-dot" />}
                {collapsed ? <FiChevronDown /> : <FiChevronUp />}
            </button>
            {!collapsed && (
                <div className="chat-reasoning-body">
                    {steps.map((step, i) => (
                        <div
                            key={i}
                            className="chat-reasoning-step step-reveal"
                            style={{ borderLeftColor: getAgentColor(step.agent) }}
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
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{step.content}</ReactMarkdown>
                            </div>
                            {step.tool_name && (
                                <div className="step-tool font-mono text-xs">🛠️ {step.tool_name}</div>
                            )}
                            {step.tool_query && (
                                <pre className="step-query font-mono text-xs">{step.tool_query}</pre>
                            )}
                        </div>
                    ))}
                    {isActive && (
                        <div className="chat-thinking-row">
                            <span className="typing-dots lg"><span /><span /><span /></span>
                            <span className="text-xs text-muted">Agents are thinking...</span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/* ─── Signal Card ────────────────────────────────────────────────── */
function SignalCard({ sig }) {
    return (
        <div className={`chat-signal-card priority-${(sig.priority || 'low').toLowerCase()}`}>
            <div className="signal-header">
                <span className="signal-drug-name">{sig.drug_name}</span>
                <span className={`badge ${getPriorityClass(sig.priority)}`}>{sig.priority}</span>
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
                    <span className="signal-stat-value stat-neutral">{sig.case_count?.toLocaleString()}</span>
                </div>
                <div className="signal-stat">
                    <span className="signal-stat-label">Spike</span>
                    <span className={`signal-stat-value ${sig.spike_ratio > 3 ? 'stat-danger' : 'stat-neutral'}`}>
                        {sig.spike_ratio?.toFixed(1)}×
                    </span>
                </div>
            </div>
        </div>
    );
}

/* ─── Report Card ────────────────────────────────────────────────── */
function ReportCard({ rpt, index }) {
    const [open, setOpen] = useState(false);

    const handleDownloadPdf = async () => {
        const element = document.getElementById(`report-pdf-${index}`);
        if (!element) return;
        try {
            const canvas = await html2canvas(element, {
                scale: 2, useCORS: true, backgroundColor: '#09090b', windowWidth: 800,
            });
            const imgData = canvas.toDataURL('image/png');
            const pdf = new jsPDF('p', 'mm', 'a4');
            const pdfWidth = pdf.internal.pageSize.getWidth();
            const pdfHeight = (canvas.height * pdfWidth) / canvas.width;
            pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
            pdf.save(`${rpt.drug_name}_Safety_Report.pdf`);
        } catch (e) { console.error(e); }
    };

    return (
        <div className={`chat-report-card ${open ? 'open' : ''}`}>
            <button className="chat-report-header" onClick={() => setOpen(o => !o)}>
                <div className="chat-report-meta">
                    <HiOutlineDocumentReport style={{ color: 'var(--accent-secondary)', fontSize: '1rem' }} />
                    <span className="chat-report-drug">{rpt.drug_name}</span>
                    <span className={`badge ${getPriorityClass(rpt.risk_level)}`}>{rpt.risk_level}</span>
                </div>
                <div className="chat-report-subtitle">{rpt.reaction_term}</div>
                <FiChevronDown className={`chat-report-chevron ${open ? 'rotated' : ''}`} />
            </button>
            {open && rpt.report_markdown && (
                <div className="chat-report-body">
                    <div className="chat-report-actions">
                        <span className="badge badge-info text-xs">Safety Report</span>
                        <button className="btn btn-sm btn-secondary" onClick={handleDownloadPdf}>
                            <FiDownload /> Download PDF
                        </button>
                    </div>
                    <div id={`report-pdf-${index}`} className="report-markdown-formatted">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{rpt.report_markdown}</ReactMarkdown>
                    </div>
                </div>
            )}
        </div>
    );
}

/* ─── Chat Message ───────────────────────────────────────────────── */
function ChatMessage({ msg }) {
    if (msg.role === 'user') {
        return (
            <div className="chat-message chat-message-user">
                <div className="chat-bubble chat-bubble-user">
                    <p>{msg.content}</p>
                </div>
                <div className="chat-avatar chat-avatar-user">
                    <RiUserLine />
                </div>
            </div>
        );
    }

    return (
        <div className="chat-message chat-message-ai">
            <div className="chat-avatar chat-avatar-ai">
                <RiRobotLine />
            </div>
            <div className="chat-ai-content">
                {msg.route && ROUTE_LABELS[msg.route] && (
                    <div className="chat-route-badge" style={{ color: ROUTE_LABELS[msg.route].color }}>
                        {ROUTE_LABELS[msg.route].label}
                    </div>
                )}

                <ReasoningSection steps={msg.reasoningSteps || []} isActive={msg.isStreaming} />

                {/* Only render once there is actual text streaming in */}
                {msg.streamedResponse && (
                    <div className="chat-response-body">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.streamedResponse}</ReactMarkdown>
                        {msg.isTyping && <span className="stream-cursor">|</span>}
                    </div>
                )}

                {msg.signals?.length > 0 && (
                    <div className="chat-results-section">
                        <div className="chat-results-label">
                            <FiAlertTriangle style={{ color: 'var(--accent-warning)' }} />
                            <span>{msg.signals.length} Safety Signal{msg.signals.length > 1 ? 's' : ''} Detected</span>
                        </div>
                        <div className="chat-signals-grid">
                            {msg.signals.map((sig, i) => <SignalCard key={i} sig={sig} />)}
                        </div>
                    </div>
                )}

                {msg.reports?.length > 0 && (
                    <div className="chat-results-section">
                        <div className="chat-results-label">
                            <HiOutlineDocumentReport style={{ color: 'var(--accent-secondary)' }} />
                            <span>{msg.reports.length} Safety Report{msg.reports.length > 1 ? 's' : ''} Generated</span>
                        </div>
                        <div className="chat-reports-list">
                            {msg.reports.map((rpt, i) => (
                                <ReportCard key={i} rpt={rpt} index={`${msg.id}-${i}`} />
                            ))}
                        </div>
                    </div>
                )}

                {msg.error && (
                    <div className="chat-error-card">⚠️ Something went wrong. Please try again.</div>
                )}

                {msg.timestamp && (
                    <div className="chat-timestamp">{msg.timestamp}</div>
                )}
            </div>
        </div>
    );
}

/* ─── Typing indicator (while waiting for first WS data) ─────────── */
function TypingMessage({ statusMessage }) {
    return (
        <div className="chat-message chat-message-ai">
            <div className="chat-avatar chat-avatar-ai"><RiRobotLine /></div>
            <div className="chat-ai-content">
                <div className="chat-typing-card glass-card-static">
                    <span className="typing-dots lg"><span /><span /><span /></span>
                    <span className="text-xs text-muted" style={{ fontStyle: 'italic' }}>
                        {statusMessage.icon} {statusMessage.text}
                    </span>
                </div>
            </div>
        </div>
    );
}

/* ─── Main Dashboard ─────────────────────────────────────────────── */
export default function Dashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const [input, setInput] = useState('');
    const [messages, setMessages] = useState([]);
    const [health, setHealth] = useState(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const [showUserMenu, setShowUserMenu] = useState(false);
    const [statusMessage, setStatusMessage] = useState(STATUS_MESSAGES[0]);

    const wsRef = useRef(null);
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);
    const userMenuRef = useRef(null);          // ← ref for outside-click detection
    const currentMsgIdRef = useRef(null);
    const stepQueueRef = useRef([]);
    const revealTimerRef = useRef(null);
    const queuedCountRef = useRef(0);
    const streamTimerRef = useRef(null);
    const fullResponseRef = useRef('');
    const statusIntervalRef = useRef(null);

    // Fetch health
    useEffect(() => {
        fetch(`${API_BASE}/api/health`)
            .then(r => r.json())
            .then(setHealth)
            .catch(() => setHealth({ status: 'offline' }));
    }, []);

    // Close user menu when clicking outside
    useEffect(() => {
        if (!showUserMenu) return;
        const handler = (e) => {
            if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
                setShowUserMenu(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [showUserMenu]);

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Cycle status messages while processing
    useEffect(() => {
        if (isProcessing) {
            let idx = 0;
            statusIntervalRef.current = setInterval(() => {
                idx = (idx + 1) % STATUS_MESSAGES.length;
                setStatusMessage(STATUS_MESSAGES[idx]);
            }, 3000);
        } else {
            clearInterval(statusIntervalRef.current);
        }
        return () => clearInterval(statusIntervalRef.current);
    }, [isProcessing]);

    const updateCurrentMessage = useCallback((updater) => {
        const id = currentMsgIdRef.current;
        if (!id) return;
        setMessages(prev => prev.map(m => m.id === id ? { ...m, ...updater(m) } : m));
    }, []);

    const drainReasoningQueue = useCallback(() => {
        if (revealTimerRef.current) return;
        const revealNext = () => {
            if (stepQueueRef.current.length === 0) {
                revealTimerRef.current = null;
                return;
            }
            const next = stepQueueRef.current.shift();
            const id = currentMsgIdRef.current;
            setMessages(prev => prev.map(m => {
                if (m.id !== id) return m;
                const exists = (m.reasoningSteps || []).some(
                    p => p.content === next.content && p.timestamp === next.timestamp
                );
                if (exists) return m;
                return { ...m, reasoningSteps: [...(m.reasoningSteps || []), next] };
            }));
            revealTimerRef.current = setTimeout(revealNext, 350);
        };
        revealTimerRef.current = setTimeout(revealNext, 350);
    }, []);

    const startStreaming = useCallback((text) => {
        if (text === fullResponseRef.current) return;
        fullResponseRef.current = text;
        if (streamTimerRef.current) clearInterval(streamTimerRef.current);

        const words = text.split(/( )/);
        let index = 0;

        updateCurrentMessage(m => ({ ...m, streamedResponse: '', isTyping: true }));

        streamTimerRef.current = setInterval(() => {
            const chunk = words.slice(index, index + 4).join('');
            index += 4;
            const id = currentMsgIdRef.current;
            setMessages(prev => prev.map(m => {
                if (m.id !== id) return m;
                return { ...m, streamedResponse: (m.streamedResponse || '') + chunk };
            }));
            if (index >= words.length) {
                clearInterval(streamTimerRef.current);
                streamTimerRef.current = null;
                setMessages(prev => prev.map(m =>
                    m.id === id ? { ...m, streamedResponse: text, isTyping: false } : m
                ));
            }
        }, 18);
    }, [updateCurrentMessage]);

    const connectWebSocket = useCallback((investigationId) => {
        if (wsRef.current) wsRef.current.close();

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.origin.includes('localhost') ? 'localhost:8000' : window.location.host;
        const ws = new WebSocket(`${wsProtocol}//${wsHost}/ws/progress/${investigationId}`);
        wsRef.current = ws;

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);

            if (msg.type === 'current_state') {
                const d = msg.data;
                if (d.reasoning_trace?.length) {
                    stepQueueRef.current.push(...d.reasoning_trace);
                    drainReasoningQueue();
                }
            }

            if (msg.type === 'progress') {
                const d = msg.data;

                if (d.type === 'reasoning' && d.steps) {
                    stepQueueRef.current.push(...d.steps);
                    drainReasoningQueue();
                    return;
                }

                if (d.route) {
                    updateCurrentMessage(m => ({ ...m, route: d.route }));
                }

                if (d.direct_response) {
                    startStreaming(d.direct_response);
                }

                if (d.status === 'complete' || d.status === 'error') {
                    fetch(`${API_BASE}/api/investigations/${investigationId}`)
                        .then(r => r.json())
                        .then(inv => {
                            const id = currentMsgIdRef.current;
                            setMessages(prev => prev.map(m => {
                                if (m.id !== id) return m;
                                return {
                                    ...m,
                                    signals: inv.signals || [],
                                    reports: inv.reports || [],
                                    streamedResponse: inv.direct_response || m.streamedResponse || '',
                                    isStreaming: false,
                                    isTyping: false,
                                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                                };
                            }));
                            setIsProcessing(false);
                            currentMsgIdRef.current = null;
                            setTimeout(() => inputRef.current?.focus(), 100);
                        })
                        .catch(() => {
                            setIsProcessing(false);
                            updateCurrentMessage(m => ({ ...m, error: true, isStreaming: false }));
                        });
                }
            }
        };

        ws.onerror = () => {
            setIsProcessing(false);
            updateCurrentMessage(m => ({ ...m, error: true, isStreaming: false }));
        };
    }, [drainReasoningQueue, startStreaming, updateCurrentMessage]);

    const handleSend = async () => {
        const q = input.trim();
        if (!q || isProcessing) return;

        setInput('');

        // Reset queues
        stepQueueRef.current = [];
        queuedCountRef.current = 0;
        fullResponseRef.current = '';
        if (revealTimerRef.current) { clearTimeout(revealTimerRef.current); revealTimerRef.current = null; }
        if (streamTimerRef.current) { clearInterval(streamTimerRef.current); streamTimerRef.current = null; }

        const userMsgId = Date.now() + '-user';
        setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: q }]);

        const aiMsgId = Date.now() + '-ai';
        currentMsgIdRef.current = aiMsgId;
        setMessages(prev => [...prev, {
            id: aiMsgId,
            role: 'ai',
            reasoningSteps: [],
            streamedResponse: '',
            signals: [],
            reports: [],
            route: '',
            isStreaming: true,
            isTyping: false,
            error: false,
        }]);

        setIsProcessing(true);
        setStatusMessage(STATUS_MESSAGES[0]);

        try {
            const res = await fetch(`${API_BASE}/api/investigate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: q }),
            });
            const data = await res.json();
            connectWebSocket(data.investigation_id);
        } catch (err) {
            setIsProcessing(false);
            updateCurrentMessage(m => ({ ...m, error: true, isStreaming: false }));
        }
    };

    const handleClearChat = () => {
        setMessages([]);
        if (wsRef.current) wsRef.current.close();
        setIsProcessing(false);
    };

    const handleLogout = () => {
        logout();
        navigate('/');
    };

    const isHealthy = health?.status === 'healthy';

    // Show typing indicator only while waiting before the AI placeholder appears with reasoning
    const showTypingIndicator = isProcessing && messages.length > 0 && messages[messages.length - 1]?.role === 'user';

    return (
        <div className="chatbot-layout">
            <div className="app-bg" />

            {/* ── Sidebar ──────────────────────────────────────── */}
            <aside className="chat-sidebar glass-card-static">
                <div className="sidebar-brand">
                    <div className="nav-logo">
                        <HiOutlineShieldCheck />
                    </div>
                    <div>
                        <span className="nav-title">PharmaVigil</span>
                        <span className="nav-badge">AI</span>
                    </div>
                </div>

                <div className="sidebar-divider" />

                <button className="sidebar-new-chat" onClick={handleClearChat}>
                    <FiTrash2 />
                    <span>Clear Chat</span>
                </button>

                <div className="sidebar-section-label">Quick Queries</div>
                <div className="sidebar-suggestions">
                    {QUERY_SUGGESTIONS.map((s, i) => (
                        <button
                            key={i}
                            className="sidebar-suggestion-item"
                            onClick={() => { setInput(s); inputRef.current?.focus(); }}
                        >
                            {s}
                        </button>
                    ))}
                </div>

                <div className="sidebar-footer">
                    <div className="sidebar-health">
                        <FiActivity style={{ color: isHealthy ? 'var(--accent-secondary)' : 'var(--accent-warning)' }} />
                        <span className="text-xs" style={{ color: isHealthy ? 'var(--accent-secondary)' : 'var(--accent-warning)' }}>
                            {health ? health.status : 'Checking...'}
                        </span>
                        <span className={`health-dot ${isHealthy ? 'healthy' : 'offline'}`} />
                    </div>

                    <div className="sidebar-user-info-row">
                        <div className="user-avatar">{user?.avatar || '?'}</div>
                        <div className="sidebar-user-text">
                            <span className="text-sm" style={{ fontWeight: 600 }}>{user?.name}</span>
                            <span className="text-xs text-muted">{user?.email}</span>
                        </div>
                        <button
                            className="sidebar-logout-btn"
                            onClick={handleLogout}
                            title="Logout"
                        >
                            <FiLogOut />
                        </button>
                    </div>
                </div>
            </aside>

            {/* ── Chat Area ──────────────────────────────────── */}
            <div className="chat-area">

                {/* Header */}
                <header className="chat-header glass-card-static">
                    <div className="chat-header-title">
                        <HiOutlineShieldCheck style={{ color: 'var(--accent-primary)' }} />
                        <span className="heading-sm">Drug Safety Investigation</span>
                    </div>
                    <div className="chat-header-actions">
                        <div className="health-indicator" style={{ color: isHealthy ? 'var(--accent-secondary)' : 'var(--accent-warning)' }}>
                            <FiActivity />
                            <span className="text-xs">{health ? health.status : '...'}</span>
                        </div>
                        <button className="btn btn-ghost btn-sm" onClick={handleClearChat}>
                            <FiTrash2 /> Clear
                        </button>
                        {/* User menu — ref attached here for outside-click detection */}
                        <div className="user-menu-wrapper" ref={userMenuRef}>
                            <button
                                className="user-menu-btn"
                                onClick={() => setShowUserMenu(s => !s)}
                            >
                                <div className="user-avatar">{user?.avatar || '?'}</div>
                                <span className="text-sm hide-mobile">{user?.name}</span>
                                <FiChevronDown />
                            </button>
                            {showUserMenu && (
                                <div className="user-dropdown glass-card anim-fade-in">
                                    <div className="dropdown-header">
                                        <div className="user-avatar" style={{ width: 36, height: 36 }}>
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
                </header>

                {/* Messages */}
                <div className="chat-messages-area">
                    {messages.length === 0 && (
                        <div className="chat-welcome anim-fade-in-up">
                            <div className="chat-welcome-icon anim-float">
                                <HiOutlineShieldCheck />
                            </div>
                            <h2 className="heading-md" style={{ color: 'var(--text-bright)' }}>
                                Welcome to <span className="gradient-text">PharmaVigil AI</span>
                            </h2>
                            <p className="text-secondary" style={{ maxWidth: 460, textAlign: 'center', lineHeight: 1.7 }}>
                                Ask me to scan for drug safety signals, investigate specific drugs,
                                query adverse event data, or generate regulatory-ready reports.
                            </p>
                            <div className="chat-welcome-chips">
                                {QUERY_SUGGESTIONS.slice(0, 4).map((s, i) => (
                                    <button
                                        key={i}
                                        className="chat-welcome-chip glass-card"
                                        onClick={() => { setInput(s); inputRef.current?.focus(); }}
                                    >
                                        <span className="text-sm">{s}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {messages.map(msg => <ChatMessage key={msg.id} msg={msg} />)}

                    {showTypingIndicator && <TypingMessage statusMessage={statusMessage} />}

                    <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div className="chat-input-area">
                    <div className="chat-input-bar glass-card-static">
                        <textarea
                            ref={inputRef}
                            className="chat-textarea"
                            placeholder="Ask about drug safety signals, investigate a drug, or query data..."
                            value={input}
                            rows={1}
                            onChange={e => {
                                setInput(e.target.value);
                                e.target.style.height = 'auto';
                                e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px';
                            }}
                            onKeyDown={e => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    handleSend();
                                }
                            }}
                            disabled={isProcessing}
                        />
                        <button
                            className={`chat-send-btn ${input.trim() && !isProcessing ? 'active' : ''}`}
                            onClick={handleSend}
                            disabled={!input.trim() || isProcessing}
                        >
                            {isProcessing
                                ? <span className="spinner spinner-sm" />
                                : <FiSend />}
                        </button>
                    </div>
                    <p className="chat-input-hint">
                        <FiZap style={{ color: 'var(--accent-primary)', fontSize: '0.7rem' }} />
                        Powered by Elastic Agent Builder · LangGraph · Groq &nbsp;·&nbsp;
                        Press <kbd>Enter</kbd> to send, <kbd>Shift+Enter</kbd> for new line
                    </p>
                </div>

            </div>
        </div>
    );
}
