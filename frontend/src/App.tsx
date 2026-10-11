import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Database,
  Gauge,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  Play,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  TriangleAlert,
  X,
} from "lucide-react";
import { api, Candidate, QueryRow, Run } from "./api";

type LoadState<T> = { data?: T; error?: string; loading: boolean };
function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<LoadState<T>>({ loading: true });
  const refresh = useCallback(() => {
    setState((current) => ({ ...current, loading: true, error: undefined }));
    load()
      .then((data) => setState({ data, loading: false }))
      .catch((error: Error) =>
        setState({ error: error.message, loading: false }),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    refresh();
  }, [refresh]);
  return { ...state, refresh };
}

const navItems = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/workload", label: "Query workload", icon: ListFilter },
  { to: "/analyze", label: "Analyze query", icon: Sparkles },
  { to: "/history", label: "Analysis history", icon: Clock3 },
  { to: "/benchmark", label: "Benchmark", icon: Gauge },
  { to: "/settings", label: "System status", icon: Settings2 },
];

function App() {
  const status = useLoad(() => api.status(), []);
  const ready = status.data?.status === "ready";
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link to="/" className="brand">
          <span className="brand-mark">
            <ShieldCheck size={24} />
          </span>
          <span>
            <b>Plan Proof</b>
            <small>QUERY ADVISOR</small>
          </span>
        </Link>
        <div className="workspace-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `nav-link ${isActive ? "active" : ""}`
              }
              aria-label={label}
              title={label}
            >
              <Icon size={20} strokeWidth={1.8} />
              <span>{label}</span>
              {label === "System status" && (
                <span className={`nav-dot ${ready ? "ok" : "warn"}`} />
              )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="safety-card">
            <span className="safety-icon">
              <ShieldCheck size={20} />
            </span>
            <div>
              <b>Read only by design</b>
              <p>Index proposals are tested in an isolated sandbox.</p>
            </div>
          </div>
          <div className="version-line">
            <span className="status-dot" /> API{" "}
            {status.loading
              ? "checking"
              : ready
                ? "connected"
                : "attention needed"}
            <button
              className="icon-button tiny"
              aria-label="Refresh system status"
              onClick={status.refresh}
            >
              <RefreshCw size={13} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Plan Proof</span>
            <ChevronRight size={14} />
            <Routes>
              <Route path="/" element={<b>Overview</b>} />
              <Route path="/workload" element={<b>Query workload</b>} />
              <Route path="/analyze" element={<b>Analyze query</b>} />
              <Route path="/history/*" element={<b>Analysis history</b>} />
              <Route path="/benchmark" element={<b>Benchmark</b>} />
              <Route path="/settings" element={<b>System status</b>} />
            </Routes>
          </div>
          <div className="topbar-right">
            <span className="env-pill">
              <span className="status-dot" /> DEVELOPMENT
            </span>
            <button className="avatar" aria-label="Plan Proof workspace">
              PP
            </button>
          </div>
        </header>
        <div className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/workload" element={<Workload />} />
            <Route path="/analyze" element={<Analyze />} />
            <Route path="/history" element={<History />} />
            <Route path="/history/:runId" element={<HistoryDetail />} />
            <Route path="/benchmark" element={<Benchmark />} />
            <Route path="/settings" element={<Settings />} />
            <Route
              path="*"
              element={
                <Empty
                  title="Page not found"
                  detail="Choose a section from the navigation."
                />
              }
            />
          </Routes>
        </div>
      </main>
    </div>
  );
}

function PageHeading({
  eyebrow,
  title,
  detail,
  action,
}: {
  eyebrow: string;
  title: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
      {action && <div className="heading-action">{action}</div>}
    </div>
  );
}
function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="notice error">
      <TriangleAlert size={17} />
      <span>{message}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
function Loading({ label = "Loading data" }: { label?: string }) {
  return (
    <div className="loading">
      <LoaderCircle size={18} className="spin" />
      {label}…
    </div>
  );
}
function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <CircleHelp size={20} />
      </span>
      <b>{title}</b>
      <p>{detail}</p>
    </div>
  );
}
function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  return (
    <span className={`badge ${normalized}`}>{value.replaceAll("_", " ")}</span>
  );
}
function formatMs(value?: number) {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return value < 1 ? `${value.toFixed(3)} ms` : `${value.toFixed(2)} ms`;
}
function formatCost(value?: number | null) {
  return value == null
    ? "—"
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
function ErrorPage({
  error,
  refresh,
}: {
  error?: string;
  refresh?: () => void;
}) {
  return error ? <ErrorBox message={error} retry={refresh} /> : null;
}

function Dashboard() {
  const history = useLoad(() => api.history(100), []);
  const workload = useLoad(() => api.workload(100), []);
  const runs = history.data?.runs ?? [];
  const candidates = runs.flatMap((run) =>
    run.queries.flatMap((query) => query.candidates),
  );
  const counts = {
    accept: candidates.filter((c) => c.decision === "accept").length,
    reject: candidates.filter((c) => c.decision === "reject").length,
    inconclusive: candidates.filter((c) => c.decision === "inconclusive")
      .length,
    unsupported:
      workload.data?.queries.filter((q) => !q.analyzable).length ?? 0,
  };
  const acceptedImprovements = candidates
    .filter((candidate) => candidate.decision === "accept")
    .map((candidate) => Number(candidate.details?.improvement_percent))
    .filter(Number.isFinite);
  const averageImprovement = acceptedImprovements.length
    ? acceptedImprovements.reduce((sum, value) => sum + value, 0) /
      acceptedImprovements.length
    : undefined;
  const recent = runs.slice(0, 5);
  return (
    <>
      <PageHeading
        eyebrow="DATABASE INTELLIGENCE"
        title="Overview"
        detail="Evidence from real query plans, with every recommendation checked against PostgreSQL."
        action={
          <Link className="button primary" to="/analyze">
            <Play size={15} /> Analyze a query
          </Link>
        }
      />
      {(history.error || workload.error) && (
        <ErrorPage
          error={history.error ?? workload.error}
          refresh={() => {
            history.refresh();
            workload.refresh();
          }}
        />
      )}
      {(history.loading || workload.loading) && !history.data && (
        <Loading label="Loading database activity" />
      )}
      <div className="stats-grid">
        <StatCard
          icon={<Activity size={17} />}
          label="Saved analysis runs"
          value={history.data?.total ?? "—"}
          hint="Persisted verification records"
          tone="blue"
        />
        <StatCard
          icon={<ShieldCheck size={17} />}
          label="Candidates verified"
          value={history.data ? candidates.length : "—"}
          hint="Recent 100 runs"
          tone="violet"
        />
        <StatCard
          icon={<Check size={17} />}
          label="Accepted"
          value={history.data ? counts.accept : "—"}
          hint="Met the 10% planner threshold"
          tone="green"
        />
        <StatCard
          icon={<ArrowDownRight size={17} />}
          label="Rejected"
          value={history.data ? counts.reject : "—"}
          hint="Not selected or not beneficial"
          tone="red"
        />
        <StatCard
          icon={<CircleHelp size={17} />}
          label="Inconclusive"
          value={history.data ? counts.inconclusive : "—"}
          hint="Could not support a decision"
          tone="amber"
        />
        <StatCard
          icon={<TriangleAlert size={17} />}
          label="Unsupported sample"
          value={workload.data ? counts.unsupported : "—"}
          hint="In the current workload sample"
          tone="slate"
        />
        <StatCard
          icon={<ArrowDownRight size={17} />}
          label="Avg. estimated improvement"
          value={
            averageImprovement === undefined
              ? "—"
              : `${averageImprovement.toFixed(1)}%`
          }
          hint="Accepted candidates in recent 100 runs"
          tone="green"
        />
      </div>
      <div className="dashboard-grid">
        <section className="panel recent-panel">
          <PanelTitle
            title="Recent analysis"
            detail="Latest saved verification activity"
            action={
              <Link to="/history" className="text-link">
                View history <ChevronRight size={14} />
              </Link>
            }
          />
          {history.error ? null : history.loading && !history.data ? (
            <Loading />
          ) : recent.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Query</th>
                    <th>Outcome</th>
                    <th>Checked</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((run) => {
                    const all = run.queries.flatMap((q) => q.candidates);
                    return (
                      <tr key={run.id}>
                        <td>
                          <span className="query-code">
                            {run.queries[0]?.sql ?? "Analysis run"}
                          </span>
                          <small className="cell-sub">
                            {run.queries.length} query · {all.length} proposal
                            {all.length === 1 ? "" : "s"}
                          </small>
                        </td>
                        <td>
                          <OutcomeSummary candidates={all} />
                        </td>
                        <td className="muted">
                          {new Date(run.created_at).toLocaleDateString()}
                        </td>
                        <td>
                          <Link
                            className="row-link"
                            to={`/history/${run.id}`}
                            aria-label="Open analysis"
                          >
                            <ChevronRight size={16} />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No saved analysis yet"
              detail="Analyze a query or run workload analysis to create your first record."
            />
          )}
        </section>
        <section className="panel">
          <PanelTitle
            title="How Plan Proof decides"
            detail="Every suggestion is checked in the sandbox."
          />
          <div className="decision-flow">
            <div className="flow-step">
              <span className="step-number">01</span>
              <div>
                <b>Capture the baseline</b>
                <p>Read only EXPLAIN from the target query workload.</p>
              </div>
            </div>
            <div className="flow-line" />
            <div className="flow-step">
              <span className="step-number">02</span>
              <div>
                <b>Test a hypothetical index</b>
                <p>
                  HypoPG lets PostgreSQL consider it in an isolated sandbox.
                </p>
              </div>
            </div>
            <div className="flow-line" />
            <div className="flow-step">
              <span className="step-number">03</span>
              <div>
                <b>Apply the evidence threshold</b>
                <p>
                  Accept only when selected and estimated cost improves by 10%
                  or more.
                </p>
              </div>
            </div>
          </div>
          <div className="callout">
            <TriangleAlert size={15} />
            <span>
              Planner cost is an estimate. It does not promise the same
              reduction in execution time.
            </span>
          </div>
        </section>
      </div>
      <div className="dashboard-footer">
        <span>
          <Database size={14} /> {workload.data?.count ?? 0} workload queries
          currently visible
        </span>
        <span>Latest records and live workload data</span>
        <Link to="/benchmark">
          See benchmark evaluation <ChevronRight size={13} />
        </Link>
      </div>
    </>
  );
}
function StatCard({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint: string;
  tone: string;
}) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${tone}`}>{icon}</div>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-hint">{hint}</div>
    </div>
  );
}
function PanelTitle({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel-title">
      <div>
        <h2>{title}</h2>
        {detail && <p>{detail}</p>}
      </div>
      {action}
    </div>
  );
}
function OutcomeSummary({ candidates }: { candidates: Candidate[] }) {
  if (!candidates.length) return <span className="muted">No candidates</span>;
  const best = candidates.find((c) => c.decision === "accept") ?? candidates[0];
  return <StatusBadge value={best.decision} />;
}

function Workload() {
  const { data, loading, error, refresh } = useLoad(
    () => api.workload(100),
    [],
  );
  const [filter, setFilter] = useState("");
  const rows = useMemo(
    () =>
      (data?.queries ?? []).filter(
        (q) =>
          q.sql.toLowerCase().includes(filter.toLowerCase()) ||
          String(q.queryid).includes(filter),
      ),
    [data, filter],
  );
  return (
    <>
      <PageHeading
        eyebrow="PG_STAT_STATEMENTS"
        title="Query workload"
        detail="Live query statistics collected from the configured read only target."
        action={
          <button className="button secondary" onClick={refresh}>
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />
      <div className="notice info">
        <Activity size={16} />
        <span>
          Execution statistics come directly from PostgreSQL. Parameterized
          query text is shown as collected and cannot be safely planned without
          bind values.
        </span>
      </div>
      <ErrorPage error={error} refresh={refresh} />
      <section className="panel table-panel">
        <div className="toolbar">
          <div className="search-box">
            <Search size={15} />
            <input
              aria-label="Search workload"
              placeholder="Search SQL or query ID"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <span className="muted small">
            {data?.count ?? 0} queries · ranked by total execution time
          </span>
        </div>
        {error ? null : loading && !data ? (
          <Loading />
        ) : rows.length ? (
          <div className="table-wrap">
            <table className="workload-table">
              <thead>
                <tr>
                  <th>QUERY</th>
                  <th>CALLS</th>
                  <th>TOTAL TIME</th>
                  <th>MEAN TIME</th>
                  <th>ROWS</th>
                  <th>STATUS</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((query) => (
                  <WorkloadRow key={query.queryid} query={query} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={filter ? "No matching queries" : "No workload data yet"}
            detail={
              filter
                ? "Try another query fragment or ID."
                : "Run representative SELECT queries against the target. pg_stat_statements must be enabled."
            }
          />
        )}
      </section>
      <div className="page-footnote">
        <ShieldCheck size={14} /> The target connection runs with default read
        only transactions; plan experiments run in the sandbox.
      </div>
    </>
  );
}
function WorkloadRow({ query }: { query: QueryRow }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  return (
    <>
      <tr className="click-row" onClick={() => setOpen(!open)}>
        <td>
          <code className="query-code">{query.sql}</code>
          <small className="cell-sub">Query ID {query.queryid}</small>
        </td>
        <td>{query.calls.toLocaleString()}</td>
        <td>{formatMs(query.total_exec_time_ms)}</td>
        <td>{formatMs(query.mean_exec_time_ms)}</td>
        <td>{query.rows.toLocaleString()}</td>
        <td>
          {query.analyzable ? (
            <span className="badge ready">Ready</span>
          ) : (
            <span className="badge unsupported">Unsupported</span>
          )}
        </td>
        <td>
          <button className="row-link" aria-label="Expand query">
            <ChevronRight size={15} className={open ? "rotate" : ""} />
          </button>
        </td>
      </tr>
      {open && (
        <tr className="expanded-row">
          <td colSpan={7}>
            <div className="expanded-content">
              <div>
                <b>Collected query</b>
                <pre>{query.sql}</pre>
                {query.reason && (
                  <p className="inline-warning">
                    <TriangleAlert size={14} />
                    {query.reason}
                  </p>
                )}
              </div>
              <button
                className="button secondary small-button"
                disabled={!query.analyzable}
                onClick={(event) => {
                  event.stopPropagation();
                  navigate("/analyze", { state: { sql: query.sql } });
                }}
              >
                <Sparkles size={14} /> Analyze query
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function Analyze() {
  const [sql, setSql] = useState("SELECT * FROM orders WHERE user_id = 12345");
  const [result, setResult] = useState<{
    status: string;
    reason: string | null;
    proposal_plan?: Record<string, unknown>;
    candidates: Candidate[];
    proposal_source?: string;
    proposal_status?: string;
    proposal_reason?: string | null;
  }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Candidate>();
  const location = useLocation();
  const locationState = (location.state ?? {}) as { sql?: string };
  useEffect(() => {
    if (locationState.sql) setSql(locationState.sql);
  }, [locationState.sql]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(undefined);
    setSelected(undefined);
    try {
      const value = await api.analyze(sql);
      setResult(value);
      setSelected(undefined);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="PLAN ANALYSIS"
        title="Analyze a query"
        detail="Generate bounded LLM or heuristic proposals, then verify each with PostgreSQL in the sandbox."
      />
      <div className="analyze-layout">
        <section className="panel editor-panel">
          <PanelTitle
            title="Query input"
            detail="One read only SELECT statement. Parameter values are never guessed."
          />
          <form onSubmit={submit}>
            <label htmlFor="query-editor" className="field-label">
              SQL query
            </label>
            <div className="editor">
              <div className="editor-toolbar">
                <span>
                  <span className="editor-dot" /> PostgreSQL
                </span>
                <span>SQL</span>
              </div>
              <textarea
                id="query-editor"
                spellCheck={false}
                value={sql}
                onChange={(e) => setSql(e.target.value)}
                placeholder="SELECT … FROM … WHERE …"
                required
              />
              <div className="editor-footer">
                <span>{sql.length} characters</span>
                <span>SELECT only · max 20,000 chars</span>
              </div>
            </div>
            {error && <ErrorBox message={error} />}
            <button
              className="button primary run-button"
              type="submit"
              disabled={busy || !sql.trim()}
            >
              {busy ? (
                <>
                  <LoaderCircle size={15} className="spin" /> Analyzing…
                </>
              ) : (
                <>
                  <Play size={14} fill="currentColor" /> Analyze query
                </>
              )}
            </button>
          </form>
          <div className="editor-safety">
            <ShieldCheck size={15} />
            <span>
              The target is read only. Hypothetical index checks run in a
              separate sandbox.
            </span>
          </div>
        </section>
        <section className="panel result-panel">
          <PanelTitle
            title="Analysis result"
            detail="Plan evidence and recommendation"
          />
          {busy ? (
            <div className="result-loading">
              <span className="pulse-ring">
                <LoaderCircle size={22} className="spin" />
              </span>
              <b>Checking the query plan</b>
              <p>Capturing baseline and comparing supported proposals.</p>
              <div className="progress-track">
                <span />
              </div>
            </div>
          ) : !result ? (
            <Empty
              title="Ready when you are"
              detail="Submit a SELECT query to inspect its plan and supported index candidates."
            />
          ) : (
            <>
              <div className="result-status">
                <StatusBadge value={result.status} />
                {result.reason && <span>{result.reason}</span>}
              </div>
              {result.proposal_source && (
                <div className="notice info proposal-notice">
                  <Sparkles size={15} />
                  <span>
                    Proposals came from <b>{result.proposal_source}</b>
                    {result.proposal_reason
                      ? ` — ${result.proposal_reason}`
                      : "."}
                    Each proposal is tested as a hypothetical index by HypoPG in
                    the sandbox; Plan Proof makes the final decision from that
                    verification.
                  </span>
                </div>
              )}
              {result.proposal_plan && (
                <PlanBlock
                  title="Target plan used to generate proposals"
                  plan={result.proposal_plan}
                />
              )}
              {result.candidates.length > 0 && (
                <section
                  className="index-proposals"
                  aria-labelledby="index-proposals-title"
                >
                  <div className="proposal-section-heading">
                    <h3 id="index-proposals-title">Index Proposals</h3>
                    <span>{result.candidates.length}</span>
                    <p>
                      The source proposes each index. HypoPG tests it in the
                      sandbox, then Plan Proof applies the verification policy.
                    </p>
                  </div>
                  <div className="candidate-list">
                    {result.candidates.map((candidate, i) => (
                      <CandidateCard
                        key={candidate.table + "-" + i}
                        candidate={candidate}
                        onSelect={() => setSelected(candidate)}
                      />
                    ))}
                  </div>
                </section>
              )}
              {result.candidates.length === 0 && (
                <div className="empty compact">
                  <b>
                    {result.status === "unsupported"
                      ? "No supported index proposals"
                      : "No index proposals returned"}
                  </b>
                  <p>
                    {result.reason ?? "The analysis returned no candidates."}
                  </p>
                </div>
              )}
            </>
          )}
        </section>
      </div>
      {selected && result && (
        <VerifyPanel
          sql={sql}
          candidate={selected}
          onClose={() => setSelected(undefined)}
        />
      )}
    </>
  );
}
function PlanBlock({
  title,
  plan,
}: {
  title: string;
  plan: Record<string, unknown>;
}) {
  return (
    <details className="plan-block">
      <summary>
        <TerminalSquare size={15} />
        {title}
        <ChevronRight size={14} />
      </summary>
      <pre>{JSON.stringify(plan, null, 2)}</pre>
    </details>
  );
}
function CandidateCard({
  candidate,
  onSelect,
}: {
  candidate: Candidate;
  onSelect: () => void;
}) {
  const rationale = candidate.proposal_rationale?.trim();
  const explanation =
    candidate.decision_explanation?.trim() || candidate.reason;
  const definition =
    "CREATE INDEX ON " +
    candidate.table +
    " (" +
    candidate.columns.join(", ") +
    ")";
  return (
    <article className="candidate-result">
      <section className="proposal-detail">
        <div className="candidate-head">
          <div className="candidate-index">
            <Database size={15} />
            <span>
              {candidate.table}
              <small>Proposed columns: {candidate.columns.join(", ")}</small>
            </span>
          </div>
          <span className="source-pill">
            {candidate.source?.toUpperCase() ?? "SOURCE NOT REPORTED"}
          </span>
        </div>
        <div className="proposal-definition">
          <span>PROPOSED INDEX DEFINITION · NOT EXECUTED</span>
          <code>{definition}</code>
        </div>
        <div className="proposal-rationale">
          <b>Proposal rationale</b>
          <p>{rationale || "No proposal rationale was returned."}</p>
        </div>
      </section>
      <section className="candidate-verification">
        <div className="verification-heading">
          <h4>HypoPG verification</h4>
          <StatusBadge value={candidate.comparison_status ?? "unknown"} />
        </div>
        <div className="verification-metrics">
          <span>
            Baseline estimated cost <b>{formatCost(candidate.baseline_cost)}</b>
          </span>
          <span>
            Candidate estimated cost{" "}
            <b>{formatCost(candidate.candidate_cost)}</b>
          </span>
          <span>
            Estimated improvement{" "}
            <b>
              {candidate.improvement_percent == null
                ? "—"
                : candidate.improvement_percent.toFixed(2) + "%"}
            </b>
          </span>
          <span>
            Exact hypothetical index selected{" "}
            <b>
              {candidate.candidate_index_used == null
                ? "Not reported"
                : candidate.candidate_index_used
                  ? "Yes"
                  : "No"}
            </b>
          </span>
        </div>
        {candidate.comparison_reason && (
          <p className="verification-reason">{candidate.comparison_reason}</p>
        )}
        <div className="final-decision">
          <div className="verification-heading">
            <b>Plan Proof decision</b>
            <StatusBadge value={candidate.decision ?? "unknown"} />
          </div>
          <p>{explanation || "No decision explanation was returned."}</p>
        </div>
        {candidate.baseline_plan && (
          <PlanBlock
            title="Verification baseline plan"
            plan={candidate.baseline_plan}
          />
        )}
        {candidate.candidate_plan && (
          <PlanBlock
            title="Verification candidate plan"
            plan={candidate.candidate_plan}
          />
        )}
        <button
          className="verify-link verify-again"
          type="button"
          onClick={onSelect}
        >
          Run verification again <ChevronRight size={13} />
        </button>
      </section>
    </article>
  );
}
function VerifyPanel({
  sql,
  candidate,
  onClose,
}: {
  sql: string;
  candidate: Candidate;
  onClose: () => void;
}) {
  const [response, setResponse] = useState<Record<string, any>>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [table, setTable] = useState(candidate.table);
  const [columns, setColumns] = useState(candidate.columns.join(", "));
  async function verify(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResponse(
        await api.verify({
          sql,
          table_name: table.trim(),
          columns: columns
            .split(",")
            .map((c) => c.trim())
            .filter(Boolean),
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="verify-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="verify-title"
      >
        <div className="modal-head">
          <div>
            <div className="eyebrow">CANDIDATE CHECK</div>
            <h2 id="verify-title">Verify index proposal</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <p className="muted">
          Submit a candidate for direct comparison against baseline and
          hypothetical plans.
        </p>
        <form onSubmit={verify}>
          <div className="two-fields">
            <label>
              Table name
              <input
                value={table}
                onChange={(e) => setTable(e.target.value)}
                required
                maxLength={63}
              />
            </label>
            <label>
              Index columns
              <input
                value={columns}
                onChange={(e) => setColumns(e.target.value)}
                required
              />
            </label>
          </div>
          <button className="button primary" disabled={busy}>
            {busy ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              <ShieldCheck size={14} />
            )}{" "}
            {busy ? "Verifying…" : "Run verification"}
          </button>
        </form>
        {error && <ErrorBox message={error} />}
        {response && (
          <div className="verify-response">
            <div className="verify-verdict">
              <StatusBadge value={response.decision.status} />
              <b>{response.decision.explanation}</b>
            </div>
            <div className="cost-compare">
              <span>
                Baseline <b>{formatCost(response.comparison.baseline_cost)}</b>
              </span>
              <ArrowUpRight size={16} />
              <span>
                Candidate{" "}
                <b>{formatCost(response.comparison.candidate_cost)}</b>
              </span>
            </div>
            <p className="muted small">
              Exact hypothetical index selected:{" "}
              <b>{response.comparison.candidate_index_used ? "Yes" : "No"}</b> ·
              Threshold: {response.decision.minimum_improvement_percent}%
            </p>
            <p className="callout">
              <TriangleAlert size={14} />
              Estimated planner costs are not measured execution times.
            </p>
            <PlanBlock
              title="Verification baseline plan"
              plan={response.comparison.baseline_plan ?? {}}
            />
            <PlanBlock
              title="Verification candidate plan"
              plan={response.comparison.candidate_plan ?? {}}
            />
          </div>
        )}
      </section>
    </div>
  );
}

function History() {
  const [offset, setOffset] = useState(0);
  const { data, loading, error, refresh } = useLoad(
    () => api.history(50, offset),
    [offset],
  );
  return (
    <>
      <PageHeading
        eyebrow="PERSISTED RESULTS"
        title="Analysis history"
        detail="Previously saved query plans and candidate decisions."
        action={
          <button className="button secondary" onClick={refresh}>
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />
      <ErrorPage error={error} refresh={refresh} />
      <section className="panel table-panel">
        {error ? null : loading && !data ? (
          <Loading />
        ) : data?.runs.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ANALYSIS</th>
                  <th>DATABASE</th>
                  <th>PROPOSALS</th>
                  <th>OUTCOME</th>
                  <th>DATE</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run) => {
                  const proposals = run.queries.flatMap((q) => q.candidates);
                  return (
                    <tr key={run.id}>
                      <td>
                        <code className="query-code">
                          {run.queries[0]?.sql ?? "Saved verification"}
                        </code>
                        <small className="cell-sub">{run.id.slice(0, 8)}</small>
                      </td>
                      <td>{run.target_database}</td>
                      <td>{proposals.length}</td>
                      <td>
                        <OutcomeSummary candidates={proposals} />
                      </td>
                      <td>{new Date(run.created_at).toLocaleString()}</td>
                      <td>
                        <Link
                          className="row-link"
                          to={`/history/${run.id}`}
                          aria-label="Open run details"
                        >
                          <ChevronRight size={16} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="No history yet"
            detail="Saved candidate verifications will appear here after analysis."
          />
        )}
      </section>
      <div className="history-pagination">
        <span>
          Showing {data?.total ? offset + 1 : 0}–
          {Math.min(offset + (data?.runs.length ?? 0), data?.total ?? 0)} of{" "}
          {data?.total ?? 0} saved runs
        </span>
        <div>
          <button
            className="button secondary"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous
          </button>
          <button
            className="button secondary"
            disabled={
              !data || offset + data.runs.length >= data.total || loading
            }
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </button>
        </div>
      </div>
    </>
  );
}
function HistoryDetail() {
  const { runId = "" } = useParams();
  const { data, loading, error, refresh } = useLoad(
    () => api.run(runId),
    [runId],
  );
  return (
    <>
      <PageHeading
        eyebrow="SAVED RUN"
        title="Analysis details"
        detail={
          data
            ? `${new Date(data.created_at).toLocaleString()} · ${data.target_database}`
            : "Persisted plan and verification records."
        }
        action={
          <Link className="button secondary" to="/history">
            ← History
          </Link>
        }
      />
      <ErrorPage error={error} refresh={refresh} />
      {error ? null : loading && !data ? (
        <Loading />
      ) : (
        data && (
          <div className="history-detail">
            {data.queries.map((query) => (
              <section className="panel" key={query.id}>
                <PanelTitle
                  title="Query"
                  detail={`${query.calls} calls · ${formatMs(query.mean_exec_time_ms)} mean · ${formatMs(query.total_exec_time_ms)} total`}
                />
                <pre className="sql-display">{query.sql}</pre>
                {query.plan && (
                  <PlanBlock title="Stored baseline plan" plan={query.plan} />
                )}
                {query.candidates.map((candidate) => (
                  <CandidateHistory key={candidate.id} candidate={candidate} />
                ))}
              </section>
            ))}
          </div>
        )
      )}
    </>
  );
}
function CandidateHistory({ candidate }: { candidate: Candidate }) {
  const details = candidate.details ?? {};
  const baselinePlan = details.baseline_plan as
    | Record<string, unknown>
    | undefined;
  const candidatePlan = details.candidate_plan as
    | Record<string, unknown>
    | undefined;
  return (
    <div className="history-candidate">
      <div className="candidate-head">
        <div className="candidate-index">
          <Database size={15} />
          <span>
            {candidate.proposal_sql ?? "Index proposal"}
            <small>Source: {candidate.source}</small>
          </span>
        </div>
        <StatusBadge value={candidate.decision} />
      </div>
      <p>{candidate.rationale}</p>
      <div className="metric-row">
        <span>
          Baseline cost <b>{formatCost(candidate.baseline_cost)}</b>
        </span>
        <span>
          Candidate cost <b>{formatCost(candidate.candidate_cost)}</b>
        </span>
        <span>{String(details.comparison_reason ?? "")}</span>
      </div>
      {baselinePlan && (
        <PlanBlock title="Verification baseline plan" plan={baselinePlan} />
      )}
      {Boolean(candidatePlan) && (
        <PlanBlock title="Candidate plan" plan={candidatePlan!} />
      )}
    </div>
  );
}

function Benchmark() {
  const { data, loading, error, refresh } = useLoad(() => api.benchmark(), []);
  const summary = data?.summary;
  return (
    <>
      <PageHeading
        eyebrow="DETERMINISTIC WORKLOAD"
        title="Benchmark evaluation"
        detail="A saved sandbox evaluation of the 40 query workload, reported as planner evidence."
        action={
          <button className="button secondary" onClick={refresh}>
            <RefreshCw size={15} /> Refresh report
          </button>
        }
      />
      <ErrorPage error={error} refresh={refresh} />
      {error ? null : loading && !data ? (
        <Loading />
      ) : summary ? (
        <>
          <div className="notice info">
            <Gauge size={16} />
            <span>
              Benchmark results are separate from production workload. Planner
              cost is estimated; this run did not measure execution latency.
            </span>
          </div>
          <div className="benchmark-summary">
            <div className="benchmark-primary">
              <span>CASES IN WORKLOAD</span>
              <strong>{summary.total_cases}</strong>
              <small>{summary.baseline_captured} baseline plans captured</small>
            </div>
            <div>
              <span>PROPOSALS COMPARED</span>
              <strong>{summary.candidate_comparisons}</strong>
              <small>Explicitly mapped proposals</small>
            </div>
            <div>
              <span>ACCEPTED</span>
              <strong className="green-text">{summary.accepted}</strong>
              <small>Index selected and threshold met</small>
            </div>
            <div>
              <span>REJECTED</span>
              <strong className="red-text">{summary.rejected}</strong>
              <small>Index was not selected</small>
            </div>
            <div>
              <span>INCONCLUSIVE</span>
              <strong className="amber-text">{summary.inconclusive}</strong>
              <small>Below threshold or unavailable</small>
            </div>
          </div>
          <section className="panel benchmark-panel">
            <PanelTitle
              title="Evaluation results"
              detail={`Generated ${data.generated_at_utc ? new Date(data.generated_at_utc).toLocaleString() : "date unavailable"} · ${data.database} database`}
            />
            <div
              className="benchmark-bar"
              role="img"
              aria-label={`${summary.accepted} accepted, ${summary.rejected} rejected, ${summary.inconclusive} inconclusive`}
            >
              <span
                style={{
                  width: `${(summary.accepted / Math.max(summary.candidate_comparisons, 1)) * 100}%`,
                }}
              />
              <span
                style={{
                  width: `${(summary.rejected / Math.max(summary.candidate_comparisons, 1)) * 100}%`,
                }}
              />
              <span
                style={{
                  width: `${(summary.inconclusive / Math.max(summary.candidate_comparisons, 1)) * 100}%`,
                }}
              />
            </div>
            <div className="legend">
              <span>
                <i className="green-bg" />
                Accepted {summary.accepted}
              </span>
              <span>
                <i className="red-bg" />
                Rejected {summary.rejected}
              </span>
              <span>
                <i className="amber-bg" />
                Inconclusive {summary.inconclusive}
              </span>
            </div>
            <div className="benchmark-notes">
              {(summary.notes ?? []).map((note: string) => (
                <div key={note}>
                  <Check size={14} />
                  {note}
                </div>
              ))}
            </div>
          </section>
          <details className="panel raw-report">
            <summary>
              Inspect individual benchmark cases <ChevronRight size={14} />
            </summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>CASE</th>
                    <th>CATEGORY</th>
                    <th>EXPECTED</th>
                    <th>RESULT</th>
                    <th>COST CHANGE</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.results ?? []).map((item: any) => (
                    <tr key={item.query_id}>
                      <td>{item.query_id}</td>
                      <td>{item.category}</td>
                      <td>{item.expected_action}</td>
                      <td>
                        <StatusBadge
                          value={
                            item.decision?.status ??
                            item.candidate?.status ??
                            item.baseline?.status ??
                            "unsupported"
                          }
                        />
                      </td>
                      <td>
                        {item.decision?.estimated_cost_improvement_percent !=
                        null
                          ? `${Number(item.decision.estimated_cost_improvement_percent).toFixed(2)}%`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <Empty
          title="No benchmark report"
          detail="The benchmark evaluation report is not available in this installation."
        />
      )}
    </>
  );
}

function Settings() {
  const { data, loading, error, refresh } = useLoad(() => api.status(), []);
  const checks: Record<string, { status: string; detail: string }> =
    data?.checks ?? {};
  return (
    <>
      <PageHeading
        eyebrow="ENVIRONMENT"
        title="System status"
        detail="Connection checks for the configured application services."
        action={
          <button className="button secondary" onClick={refresh}>
            <RefreshCw size={15} /> Check again
          </button>
        }
      />
      <ErrorPage error={error} refresh={refresh} />
      <div className="status-overview">
        <span
          className={`status-large ${data?.status === "ready" ? "ready" : "degraded"}`}
        >
          <span className="status-dot" />
          {loading
            ? "Checking services"
            : data?.status === "ready"
              ? "All services ready"
              : "Some services need attention"}
        </span>
        <span className="muted">
          Credentials and connection strings are never shown here.
        </span>
      </div>
      <div className="service-grid">
        {Object.entries(checks).map(([key, value]) => (
          <div className="panel service-card" key={key}>
            <div className={`service-icon ${value.status}`}>
              <Database size={17} />
            </div>
            <div>
              <b>{key.replaceAll("_", " ")}</b>
              <p>{value.detail}</p>
            </div>
            <StatusBadge value={value.status} />
          </div>
        ))}
      </div>
      <section className="panel llm-status-panel">
        <PanelTitle
          title="Candidate proposal provider"
          detail="The provider proposes indexes; PostgreSQL and HypoPG determine every outcome."
        />
        <div className="llm-status-row">
          <div>
            <b>{data?.llm_provider?.provider ?? "LLM"}</b>
            <p>
              {data?.llm_provider?.detail ?? "Provider status unavailable."}
            </p>
          </div>
          <code>{data?.llm_provider?.model ?? "—"}</code>
          <StatusBadge value={data?.llm_provider?.status ?? "unknown"} />
        </div>
        <p className="llm-config-note">
          Configure <code>LLM_PROVIDER</code>, <code>LLM_MODEL</code>, and the
          matching API key in the backend environment. Groq uses{" "}
          <code>GROQ_API_KEY</code>; compatible endpoints use{" "}
          <code>LLM_API_KEY</code>. Keys are never sent to the browser.
          Heuristic proposals remain active when the provider is unavailable.
        </p>
      </section>
      <section className="panel safety-panel">
        <PanelTitle
          title="Safety boundaries"
          detail="How the advisor interacts with your PostgreSQL services."
        />
        <div className="safety-list">
          <div>
            <ShieldCheck size={16} />
            <span>
              <b>Target database</b>
              <small>
                Read only connections and EXPLAIN plans. No writes or real index
                creation.
              </small>
            </span>
          </div>
          <div>
            <Database size={16} />
            <span>
              <b>Verification sandbox</b>
              <small>
                HypoPG hypothetical indexes are reset after each comparison.
              </small>
            </span>
          </div>
          <div>
            <TriangleAlert size={16} />
            <span>
              <b>Decision meaning</b>
              <small>
                Planner estimates guide the recommendation; measured runtime
                impact may differ.
              </small>
            </span>
          </div>
        </div>
      </section>
    </>
  );
}

export default App;
