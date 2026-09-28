import { type CSSProperties, useEffect, useState } from "react";
import { AgentEditor } from "./AgentEditor";
import { VoicePlayground } from "./VoicePlayground";

type Identity = { id: string; email: string; role: string; csrf_token: string };
type Page =
	| "overview"
	| "board"
	| "history"
	| "agents"
	| "numbers"
	| "logs"
	| "settings";
type Status = "pending" | "active" | "error" | "ended";
type Field = "agent" | "channel" | "duration" | "last_activity" | "version";
type View = {
	schema_version: 1;
	fields: Field[];
	group_order: Status[];
	show_ended: boolean;
	agent_filter: string | null;
};
type Config = {
	brand_name: string;
	accent_color: string;
	default_view: View;
	modules: Page[];
	outbound_test_available: boolean;
	outbound_test_destination_masked: string | null;
};
type Session = {
	id: string;
	agent_id: string;
	agent_name: string;
	version_id: string;
	version_number: number;
	channel: string;
	direction: string;
	destination_masked: string | null;
	provider_call_id: string | null;
	status: Status;
	created_at: string;
	connected_at: string | null;
	ended_at: string | null;
	last_activity_at: string;
	end_reason: string | null;
	error_code: string | null;
	metrics: Record<string, unknown>;
};
type SessionPage = { items: Session[]; next_cursor: string | null };
type Event = {
	id: string;
	kind: string;
	source: string;
	speaker: string | null;
	text: string | null;
	details: Record<string, unknown>;
	created_at: string;
};
type Diagnostic = {
	id: string;
	session_id: string;
	severity: string;
	component: string;
	code: string;
	message: string;
	created_at: string;
};
type DiagnosticPage = { items: Diagnostic[]; next_cursor: string | null };
type Overview = {
	counts: Record<Status, number>;
	database: string;
	worker: string;
	worker_note: string;
};
type Agent = { id: string; name: string };
type PhoneNumber = {
	id: string;
	e164_masked: string;
	provider: string;
	route_agent_id: string;
	status: "active" | "deprovisioning" | "retired";
	revision: number;
	livekit_configured: boolean;
	carrier_verified: boolean;
};

const titles: Record<Page, string> = {
	overview: "Overview",
	board: "Live board",
	history: "History",
	agents: "Agents",
	numbers: "Numbers",
	logs: "Logs",
	settings: "Settings",
};
const fieldNames: Record<Field, string> = {
	agent: "Agent",
	channel: "Channel",
	duration: "Duration",
	last_activity: "Last activity",
	version: "Pinned version",
};

async function api<T>(
	path: string,
	identity: Identity,
	method = "GET",
	body?: unknown,
): Promise<T> {
	const response = await fetch(path, {
		method,
		credentials: "same-origin",
		headers: {
			...(method === "GET" ? {} : { "X-CSRF-Token": identity.csrf_token }),
			...(body === undefined ? {} : { "Content-Type": "application/json" }),
		},
		...(body === undefined ? {} : { body: JSON.stringify(body) }),
	});
	if (!response.ok) {
		const data = (await response.json().catch(() => ({}))) as {
			detail?: unknown;
		};
		throw new Error(
			typeof data.detail === "string"
				? data.detail
				: `Request failed (${response.status})`,
		);
	}
	return (await response.json()) as T;
}

function duration(session: Session, now: number): string {
	const until = session.ended_at ? Date.parse(session.ended_at) : now;
	const seconds = Math.max(
		0,
		Math.floor((until - Date.parse(session.created_at)) / 1000),
	);
	return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

function localTime(value: string): string {
	return new Date(value).toLocaleString();
}

function validProviderLabel(value: string): boolean {
	return /^[a-z0-9_-]{2,32}$/.test(value);
}

function usageRows(value: unknown): Record<string, unknown>[] {
	return Array.isArray(value)
		? value.filter(
				(item): item is Record<string, unknown> =>
					typeof item === "object" && item !== null,
			)
		: [];
}

export function Console({
	identity,
	onSignOut,
}: {
	identity: Identity;
	onSignOut: () => Promise<void>;
}) {
	const [page, setPage] = useState<Page>("overview");
	const [config, setConfig] = useState<Config | null>(null);
	const [view, setView] = useState<View | null>(null);
	const [agents, setAgents] = useState<Agent[]>([]);
	const [overview, setOverview] = useState<Overview | null>(null);
	const [board, setBoard] = useState<Session[]>([]);
	const [history, setHistory] = useState<SessionPage>({
		items: [],
		next_cursor: null,
	});
	const [historyCursor, setHistoryCursor] = useState<string | null>(null);
	const [historyFilter, setHistoryFilter] = useState({
		session_id: "",
		agent_id: "",
		status: "",
		from_at: "",
		to_at: "",
	});
	const [logs, setLogs] = useState<DiagnosticPage>({
		items: [],
		next_cursor: null,
	});
	const [logFilter, setLogFilter] = useState({
		session_id: "",
		severity: "",
		component: "",
		since: "",
	});
	const [logCursor, setLogCursor] = useState<string | null>(null);
	const [selected, setSelected] = useState<Session | null>(null);
	const [detailTab, setDetailTab] = useState<
		"conversation" | "events" | "logs" | "metrics"
	>("conversation");
	const [events, setEvents] = useState<Event[]>([]);
	const [detailLogs, setDetailLogs] = useState<Diagnostic[]>([]);
	const [now, setNow] = useState(Date.now());
	const [error, setError] = useState("");
	const [message, setMessage] = useState("");
	const [callAgentId, setCallAgentId] = useState("");
	const [callBusy, setCallBusy] = useState(false);
	const [numbers, setNumbers] = useState<PhoneNumber[]>([]);
	const [providerDrafts, setProviderDrafts] = useState<Record<string, string>>(
		{},
	);
	const [newNumber, setNewNumber] = useState("");
	const [newProvider, setNewProvider] = useState("");
	const [newRoute, setNewRoute] = useState("");
	const [numberBusy, setNumberBusy] = useState(false);
	const selectedId = selected?.id;

	useEffect(() => {
		void Promise.all([
			api<Config>("/api/console/config", identity),
			api<View>("/api/console/view", identity),
			api<Agent[]>("/api/agents", identity),
		])
			.then(([loadedConfig, loadedView, loadedAgents]) => {
				setConfig(loadedConfig);
				setView(loadedView);
				setAgents(loadedAgents);
			})
			.catch((reason: unknown) => setError(String(reason)));
	}, [identity]);

	useEffect(() => {
		if (page !== "numbers" || identity.role !== "admin") return;
		void api<PhoneNumber[]>("/api/phone-numbers", identity)
			.then(setNumbers)
			.catch((reason: unknown) => setError(String(reason)));
	}, [identity, page]);

	useEffect(() => {
		const timer = window.setInterval(() => setNow(Date.now()), 1000);
		return () => window.clearInterval(timer);
	}, []);

	useEffect(() => {
		if (page !== "overview" && page !== "board") return;
		const refresh = () => {
			void api<Overview>("/api/console/overview", identity)
				.then(setOverview)
				.catch((reason: unknown) => setError(String(reason)));
			const query = new URLSearchParams({ scope: "board", limit: "100" });
			if (view?.agent_filter) query.set("agent_id", view.agent_filter);
			void api<SessionPage>(`/api/console/sessions?${query}`, identity)
				.then((result) =>
					setBoard(
						result.items.filter(
							(item) => view?.show_ended !== false || item.status !== "ended",
						),
					),
				)
				.catch((reason: unknown) => setError(String(reason)));
		};
		refresh();
		const timer = window.setInterval(refresh, 2000);
		return () => window.clearInterval(timer);
	}, [identity, page, view?.agent_filter, view?.show_ended]);

	useEffect(() => {
		if (!selectedId) return;
		const refresh = () => {
			void Promise.all([
				api<Session>(`/api/sessions/${selectedId}`, identity),
				api<Event[]>(`/api/sessions/${selectedId}/events`, identity),
				api<DiagnosticPage>(
					`/api/console/logs?session_id=${selectedId}&limit=100`,
					identity,
				),
			])
				.then(([session, transcript, diagnostics]) => {
					setSelected((previous) =>
						previous?.id === session.id
							? { ...previous, ...session }
							: previous,
					);
					setEvents(transcript);
					setDetailLogs(diagnostics.items);
				})
				.catch((reason: unknown) => setError(String(reason)));
		};
		refresh();
		const timer = window.setInterval(refresh, 2000);
		return () => window.clearInterval(timer);
	}, [identity, selectedId]);

	useEffect(() => {
		if (page !== "history") return;
		const query = new URLSearchParams({ scope: "history", limit: "30" });
		for (const [key, value] of Object.entries(historyFilter)) {
			if (value)
				query.set(
					key,
					key.endsWith("_at") ? new Date(value).toISOString() : value,
				);
		}
		if (historyCursor) query.set("cursor", historyCursor);
		void api<SessionPage>(`/api/console/sessions?${query}`, identity)
			.then(setHistory)
			.catch((reason: unknown) => setError(String(reason)));
	}, [identity, page, historyFilter, historyCursor]);

	useEffect(() => {
		if (page !== "logs") return;
		const query = new URLSearchParams({ limit: "30" });
		for (const [key, value] of Object.entries(logFilter)) {
			if (value)
				query.set(key, key === "since" ? new Date(value).toISOString() : value);
		}
		if (logCursor) query.set("cursor", logCursor);
		void api<DiagnosticPage>(`/api/console/logs?${query}`, identity)
			.then(setLogs)
			.catch((reason: unknown) => setError(String(reason)));
	}, [identity, page, logFilter, logCursor]);

	function openSession(session: Session) {
		setSelected(session);
		setDetailTab("conversation");
	}

	async function openLogSession(sessionId: string) {
		try {
			const session = await api<Session>(
				`/api/sessions/${sessionId}`,
				identity,
			);
			openSession(session);
		} catch (reason) {
			setError(String(reason));
		}
	}

	async function saveView() {
		if (!view) return;
		try {
			setView(await api<View>("/api/console/view", identity, "PUT", view));
			setMessage("Your board view was saved.");
		} catch (reason) {
			setError(String(reason));
		}
	}

	async function callTestPhone() {
		if (!callAgentId || !config?.outbound_test_available || callBusy) return;
		setCallBusy(true);
		setError("");
		try {
			const session = await api<Session>(
				`/api/agents/${callAgentId}/outbound-test`,
				identity,
				"POST",
			);
			setMessage(`Call answered. Session ${session.id} is on the live board.`);
			setPage("board");
		} catch (reason) {
			setError(String(reason));
		} finally {
			setCallBusy(false);
		}
	}

	async function addNumber() {
		if (!newNumber || !newProvider || !newRoute || numberBusy) return;
		setNumberBusy(true);
		setError("");
		try {
			const number = await api<PhoneNumber>(
				"/api/phone-numbers",
				identity,
				"POST",
				{ e164: newNumber, provider: newProvider, route_agent_id: newRoute },
			);
			setNumbers((previous) => [...previous, number]);
			setNewNumber("");
			setMessage(
				"LiveKit inbound route created. Carrier delivery still needs a real call test.",
			);
		} catch (reason) {
			setError(String(reason));
		} finally {
			setNumberBusy(false);
		}
	}

	async function changeNumberRoute(number: PhoneNumber, routeAgentId: string) {
		if (routeAgentId === number.route_agent_id) return;
		setError("");
		try {
			const updated = await api<PhoneNumber>(
				`/api/phone-numbers/${number.id}/route`,
				identity,
				"PUT",
				{ route_agent_id: routeAgentId, expected_revision: number.revision },
			);
			setNumbers((previous) =>
				previous.map((item) => (item.id === number.id ? updated : item)),
			);
		} catch (reason) {
			setError(String(reason));
		}
	}

	async function changeNumberState(number: PhoneNumber) {
		const action = number.status === "retired" ? "reactivate" : "deactivate";
		if (
			action === "deactivate" &&
			number.status === "active" &&
			!window.confirm(`Deactivate inbound routing for ${number.e164_masked}?`)
		)
			return;
		setNumberBusy(true);
		setError("");
		try {
			const updated = await api<PhoneNumber>(
				`/api/phone-numbers/${number.id}/${action}`,
				identity,
				"POST",
				action === "reactivate"
					? {
							expected_revision: number.revision,
							provider: providerDrafts[number.id] ?? number.provider,
						}
					: { expected_revision: number.revision },
			);
			setNumbers((previous) =>
				previous.map((item) => (item.id === number.id ? updated : item)),
			);
			setProviderDrafts((previous) => {
				const next = { ...previous };
				delete next[number.id];
				return next;
			});
			setMessage(
				action === "deactivate"
					? "Inbound routing deactivated. Existing session history remains."
					: "LiveKit route recreated. Confirm carrier delivery with a real call.",
			);
		} catch (reason) {
			setError(String(reason));
			void api<PhoneNumber[]>("/api/phone-numbers", identity)
				.then(setNumbers)
				.catch(() => undefined);
		} finally {
			setNumberBusy(false);
		}
	}

	const accent = {
		"--accent": config?.accent_color ?? "#0b5960",
	} as CSSProperties;
	return (
		<section className="console" aria-label="Dashboard" style={accent}>
			<aside className="sidebar">
				<p className="eyebrow">{config?.brand_name ?? "Voice Fleet"}</p>
				<strong>Operator console</strong>
				<nav aria-label="Primary navigation">
					{(config?.modules ?? ["overview"]).map((item) => (
						<button
							type="button"
							key={item}
							aria-current={page === item ? "page" : undefined}
							onClick={() => {
								setPage(item);
								setError("");
							}}
						>
							{titles[item]}
						</button>
					))}
				</nav>
				<p className="subtle">Only configured numbers appear in inventory.</p>
				<div className="account">
					<span>
						{identity.email}
						<br />
						{identity.role}
					</span>
					<button type="button" onClick={() => void onSignOut()}>
						Sign out
					</button>
				</div>
			</aside>
			<div className="workspace">
				<header className="workspace-header">
					<div>
						<p className="eyebrow">Conversations</p>
						<h1>{titles[page]}</h1>
					</div>
					<span className="subtle">Live session data</span>
				</header>
				{error && (
					<p role="alert" className="notice">
						{error}
					</p>
				)}
				{message && (
					<p role="status" className="notice">
						{message}
					</p>
				)}
				{page === "overview" && (
					<>
						<div className="stat-grid">
							{(["pending", "active", "error", "ended"] as Status[]).map(
								(status) => (
									<div className="stat" key={status}>
										<span>{status}</span>
										<strong>{overview?.counts[status] ?? "—"}</strong>
									</div>
								),
							)}
						</div>
						<section className="panel">
							<h2>Service readiness</h2>
							<p>API and database: {overview?.database ?? "checking"}</p>
							<p>Voice worker: {overview?.worker ?? "checking"}</p>
							<p className="subtle">
								{overview?.worker_note ?? "Waiting for service state."}
							</p>
						</section>
						<section className="panel">
							<h2>Recent live sessions</h2>
							<p>{board.length} visible sessions</p>
							{config?.modules.includes("board") && (
								<button type="button" onClick={() => setPage("board")}>
									Open live board
								</button>
							)}
						</section>
					</>
				)}
				{page === "board" && (
					<>
						<div className="board-toolbar">
							<div>
								<strong>Conversations</strong>
								<span>{board.length} visible · Refreshes every 2 seconds</span>
							</div>
						</div>
						<details className="call-launcher">
							<summary>Start a browser conversation</summary>
							<VoicePlayground identity={identity} />
						</details>
						<div className="board">
							{(
								view?.group_order ?? ["pending", "active", "error", "ended"]
							).map((status) => (
								<section
									className="board-group"
									key={status}
									data-status={status}
									aria-label={`${status} sessions`}
								>
									<h2>
										<span className="board-status">{status}</span>
										<span className="board-count">
											{board.filter((item) => item.status === status).length}
										</span>
									</h2>
									{board
										.filter((item) => item.status === status)
										.map((item) => (
											<button
												type="button"
												className="session-card"
												key={item.id}
												onClick={() => openSession(item)}
											>
												<span className="card-heading">
													<strong>
														{(view?.fields ?? []).includes("agent")
															? item.agent_name
															: "Session"}
													</strong>
													{(view?.fields ?? []).includes("channel") && (
														<span className="card-channel">{item.channel}</span>
													)}
												</span>
												<small className="card-id">{item.id}</small>
												{item.destination_masked && (
													<small className="card-destination">
														{item.direction === "inbound" ? "From" : "To"}{" "}
														{item.destination_masked}
													</small>
												)}
												{((view?.fields ?? []).includes("duration") ||
													(view?.fields ?? []).includes("version")) && (
													<span className="card-facts">
														{(view?.fields ?? []).includes("duration") && (
															<span>{duration(item, now)}</span>
														)}
														{(view?.fields ?? []).includes("version") && (
															<span>Version {item.version_number}</span>
														)}
													</span>
												)}
												{(view?.fields ?? []).includes("last_activity") && (
													<small className="card-activity">
														Updated {localTime(item.last_activity_at)}
													</small>
												)}
												{item.error_code && <em>{item.error_code}</em>}
											</button>
										))}
									{!board.some((item) => item.status === status) && (
										<p className="board-empty">No sessions</p>
									)}
								</section>
							))}
						</div>
					</>
				)}
				{page === "history" && (
					<section className="panel">
						<h2>Completed conversations</h2>
						<div className="filters">
							<input
								aria-label="Session ID"
								placeholder="Session ID"
								value={historyFilter.session_id}
								onChange={(event) => {
									setHistoryCursor(null);
									setHistoryFilter({
										...historyFilter,
										session_id: event.target.value,
									});
								}}
							/>
							<select
								aria-label="Agent filter"
								value={historyFilter.agent_id}
								onChange={(event) => {
									setHistoryCursor(null);
									setHistoryFilter({
										...historyFilter,
										agent_id: event.target.value,
									});
								}}
							>
								<option value="">All agents</option>
								{agents.map((agent) => (
									<option key={agent.id} value={agent.id}>
										{agent.name}
									</option>
								))}
							</select>
							<select
								aria-label="Status filter"
								value={historyFilter.status}
								onChange={(event) => {
									setHistoryCursor(null);
									setHistoryFilter({
										...historyFilter,
										status: event.target.value,
									});
								}}
							>
								<option value="">All statuses</option>
								<option value="ended">Ended</option>
								<option value="error">Error</option>
							</select>
							<label>
								From
								<input
									type="datetime-local"
									value={historyFilter.from_at}
									onChange={(event) => {
										setHistoryCursor(null);
										setHistoryFilter({
											...historyFilter,
											from_at: event.target.value,
										});
									}}
								/>
							</label>
							<label>
								To
								<input
									type="datetime-local"
									value={historyFilter.to_at}
									onChange={(event) => {
										setHistoryCursor(null);
										setHistoryFilter({
											...historyFilter,
											to_at: event.target.value,
										});
									}}
								/>
							</label>
						</div>
						<p className="subtle">
							Browser sessions and configured phone tests appear here.
						</p>
						<div className="row-list">
							{history.items.map((item) => (
								<button
									type="button"
									key={item.id}
									onClick={() => openSession(item)}
								>
									<strong>{item.agent_name}</strong>
									<span>{item.id}</span>
									<span>
										{item.status} · {localTime(item.created_at)}
									</span>
								</button>
							))}
						</div>
						{history.items.length === 0 && <p>No matching sessions.</p>}
						<button
							type="button"
							disabled={!history.next_cursor}
							onClick={() => setHistoryCursor(history.next_cursor)}
						>
							Next page
						</button>
						{historyCursor && (
							<button type="button" onClick={() => setHistoryCursor(null)}>
								First page
							</button>
						)}
					</section>
				)}
				{page === "agents" && (
					<>
						{identity.role === "admin" && (
							<section className="panel">
								<h2>Outbound phone test</h2>
								<p className="subtle">
									{config?.outbound_test_available
										? `Calls only the configured number ${config.outbound_test_destination_masked}. Carrier and voice usage may be billed.`
										: "Configure a LiveKit outbound SIP trunk and test destination to enable a real call."}
								</p>
								<select
									aria-label="Agent for phone test"
									value={callAgentId}
									onChange={(event) => setCallAgentId(event.target.value)}
								>
									<option value="">Choose agent</option>
									{agents.map((agent) => (
										<option key={agent.id} value={agent.id}>
											{agent.name}
										</option>
									))}
								</select>
								<button
									type="button"
									disabled={
										!config?.outbound_test_available || !callAgentId || callBusy
									}
									onClick={() => void callTestPhone()}
								>
									{callBusy ? "Calling…" : "Call test phone"}
								</button>
							</section>
						)}
						<AgentEditor identity={identity} />
					</>
				)}
				{page === "numbers" && (
					<section className="panel">
						<h2>Inbound numbers</h2>
						<p className="subtle">
							Add a number only after obtaining it from a carrier. Creating a
							LiveKit route does not verify carrier delivery.
						</p>
						{identity.role === "admin" && (
							<div className="filters">
								<input
									aria-label="Owned phone number"
									placeholder="+15551234567"
									value={newNumber}
									onChange={(event) => setNewNumber(event.target.value)}
								/>
								<input
									aria-label="Carrier name"
									placeholder="Carrier"
									value={newProvider}
									onChange={(event) => setNewProvider(event.target.value)}
								/>
								<select
									aria-label="Route new number to agent"
									value={newRoute}
									onChange={(event) => setNewRoute(event.target.value)}
								>
									<option value="">Choose active agent</option>
									{agents.map((agent) => (
										<option key={agent.id} value={agent.id}>
											{agent.name}
										</option>
									))}
								</select>
								<button
									type="button"
									disabled={
										numberBusy || !newNumber || !newProvider || !newRoute
									}
									onClick={() => void addNumber()}
								>
									{numberBusy ? "Configuring…" : "Create inbound route"}
								</button>
							</div>
						)}
						{numbers.length === 0 && <p>No numbers configured.</p>}
						<div className="row-list">
							{numbers.map((number) => (
								<div key={number.id}>
									<strong>{number.e164_masked}</strong> · {number.provider}
									<p className="subtle">
										{number.status === "active"
											? "LiveKit route active · Carrier delivery unverified"
											: number.status === "deprovisioning"
												? "Route blocked · LiveKit cleanup needs retry"
												: "Route inactive · Session history retained"}
									</p>
									<select
										aria-label={`Route ${number.e164_masked} to agent`}
										value={number.route_agent_id}
										onChange={(event) =>
											void changeNumberRoute(number, event.target.value)
										}
										disabled={
											identity.role !== "admin" ||
											number.status === "deprovisioning"
										}
									>
										{agents.map((agent) => (
											<option key={agent.id} value={agent.id}>
												{agent.name}
											</option>
										))}
									</select>
									{identity.role === "admin" && number.status === "retired" && (
										<>
											<input
												aria-label={`Carrier label for ${number.e164_masked}`}
												value={providerDrafts[number.id] ?? number.provider}
												onChange={(event) =>
													setProviderDrafts((previous) => ({
														...previous,
														[number.id]: event.target.value,
													}))
												}
												disabled={numberBusy}
											/>
											<small className="subtle">
												Use 2–32 lowercase letters, numbers, _ or -. Update
												carrier SIP addresses in the server environment if it
												changed.
											</small>
										</>
									)}
									{identity.role === "admin" && (
										<button
											type="button"
											disabled={
												numberBusy ||
												(number.status === "retired" &&
													!validProviderLabel(
														providerDrafts[number.id] ?? number.provider,
													))
											}
											onClick={() => void changeNumberState(number)}
										>
											{number.status === "retired"
												? "Reactivate route"
												: number.status === "deprovisioning"
													? "Retry cleanup"
													: "Deactivate route"}
										</button>
									)}
								</div>
							))}
						</div>
					</section>
				)}
				{page === "logs" && (
					<section className="panel">
						<h2>Session diagnostics</h2>
						<p className="subtle">
							Sanitized product diagnostics only; full structured stdout needs a
							configured log sink.
						</p>
						<div className="filters">
							<input
								aria-label="Log session ID"
								placeholder="Session ID"
								value={logFilter.session_id}
								onChange={(event) => {
									setLogCursor(null);
									setLogFilter({
										...logFilter,
										session_id: event.target.value,
									});
								}}
							/>
							<select
								aria-label="Severity"
								value={logFilter.severity}
								onChange={(event) => {
									setLogCursor(null);
									setLogFilter({ ...logFilter, severity: event.target.value });
								}}
							>
								<option value="">All severity</option>
								<option value="info">Info</option>
								<option value="warning">Warning</option>
								<option value="error">Error</option>
							</select>
							<input
								aria-label="Component"
								placeholder="Component"
								value={logFilter.component}
								onChange={(event) => {
									setLogCursor(null);
									setLogFilter({ ...logFilter, component: event.target.value });
								}}
							/>
							<label>
								Since
								<input
									type="datetime-local"
									value={logFilter.since}
									onChange={(event) => {
										setLogCursor(null);
										setLogFilter({ ...logFilter, since: event.target.value });
									}}
								/>
							</label>
						</div>
						<div className="row-list">
							{logs.items.map((item) => (
								<button
									type="button"
									key={item.id}
									onClick={() => void openLogSession(item.session_id)}
								>
									<strong>
										{item.severity} · {item.code}
									</strong>
									<span>{item.message}</span>
									<small>
										{item.component} · {localTime(item.created_at)} ·{" "}
										{item.session_id}
									</small>
								</button>
							))}
						</div>
						{logs.items.length === 0 && (
							<p>No diagnostics match the filters.</p>
						)}
						<button
							type="button"
							disabled={!logs.next_cursor}
							onClick={() => setLogCursor(logs.next_cursor)}
						>
							Next page
						</button>
						{logCursor && (
							<button type="button" onClick={() => setLogCursor(null)}>
								First page
							</button>
						)}
					</section>
				)}
				{page === "settings" && view && (
					<section className="panel">
						<h2>Board view</h2>
						<p className="subtle">
							Personal presentation only. Session statuses and permissions are
							server controlled.
						</p>
						<fieldset>
							<legend>Card fields</legend>
							{(Object.keys(fieldNames) as Field[]).map((field) => (
								<label className="choice" key={field}>
									<input
										type="checkbox"
										checked={view.fields.includes(field)}
										onChange={(event) =>
											setView({
												...view,
												fields: event.target.checked
													? [...view.fields, field]
													: view.fields.filter((item) => item !== field),
											})
										}
									/>
									{fieldNames[field]}
								</label>
							))}
						</fieldset>
						<fieldset>
							<legend>Display group order</legend>
							{view.group_order.map((status, index) => (
								<div className="order-row" key={status}>
									<span>{status}</span>
									<button
										type="button"
										disabled={index === 0}
										onClick={() => {
											const order = [...view.group_order];
											[order[index - 1], order[index]] = [
												order[index],
												order[index - 1],
											];
											setView({ ...view, group_order: order });
										}}
									>
										Up
									</button>
									<button
										type="button"
										disabled={index === 3}
										onClick={() => {
											const order = [...view.group_order];
											[order[index + 1], order[index]] = [
												order[index],
												order[index + 1],
											];
											setView({ ...view, group_order: order });
										}}
									>
										Down
									</button>
								</div>
							))}
						</fieldset>
						<label className="choice">
							<input
								type="checkbox"
								checked={view.show_ended}
								onChange={(event) =>
									setView({ ...view, show_ended: event.target.checked })
								}
							/>
							Show recently ended sessions
						</label>
						<label htmlFor="view-agent">Default agent filter</label>
						<select
							id="view-agent"
							value={view.agent_filter ?? ""}
							onChange={(event) =>
								setView({ ...view, agent_filter: event.target.value || null })
							}
						>
							<option value="">All agents</option>
							{agents.map((agent) => (
								<option key={agent.id} value={agent.id}>
									{agent.name}
								</option>
							))}
						</select>
						<button
							type="button"
							disabled={view.fields.length === 0}
							onClick={() => void saveView()}
						>
							Save my view
						</button>
						<h2>Deployment presentation</h2>
						<p>
							Brand: {config?.brand_name}. Accent: {config?.accent_color}.
						</p>
						<p className="subtle">
							Set deployment environment values and restart to change
							installation defaults.
						</p>
					</section>
				)}
			</div>
			{selected && (
				<div className="drawer-backdrop">
					<aside className="detail-drawer" aria-label="Session detail">
						<div className="detail-heading">
							<div>
								<p className="eyebrow">Session detail</p>
								<h2>
									{selected.agent_name ??
										agents.find((item) => item.id === selected.agent_id)
											?.name ??
										"Agent"}
								</h2>
								<small>{selected.id}</small>
							</div>
							<button type="button" onClick={() => setSelected(null)}>
								Close
							</button>
						</div>
						<p>
							{selected.status} · {selected.channel} · version{" "}
							{selected.version_number ?? selected.version_id}
						</p>
						{selected.destination_masked && (
							<p>Destination: {selected.destination_masked}</p>
						)}
						{selected.error_code && <p role="alert">{selected.error_code}</p>}
						<div className="detail-tabs">
							{(["conversation", "events", "logs", "metrics"] as const).map(
								(tab) => (
									<button
										type="button"
										key={tab}
										aria-current={detailTab === tab ? "page" : undefined}
										onClick={() => setDetailTab(tab)}
									>
										{tab}
									</button>
								),
							)}
						</div>
						{detailTab === "conversation" && (
							<ol className="timeline">
								{events
									.filter((event) => event.kind === "transcript")
									.map((event) => (
										<li key={event.id}>
											<small>
												{localTime(event.created_at)} · {event.speaker}
											</small>
											<p>{event.text}</p>
											{event.details.final === false && <em>Interim</em>}
											{event.details.interrupted === true && (
												<em>Interrupted; partial output</em>
											)}
										</li>
									))}
							</ol>
						)}
						{detailTab === "events" && (
							<ol className="timeline">
								{events
									.filter((event) => event.kind !== "transcript")
									.map((event) => (
										<li key={event.id}>
											<small>
												{localTime(event.created_at)} · {event.source}
											</small>
											<strong>{event.kind}</strong>
											<pre>{JSON.stringify(event.details)}</pre>
										</li>
									))}
							</ol>
						)}
						{detailTab === "logs" && (
							<div className="timeline">
								{detailLogs.length === 0 && (
									<p>No diagnostics for this session.</p>
								)}
								{detailLogs.map((item) => (
									<div key={item.id}>
										<small>
											{localTime(item.created_at)} · {item.component}
										</small>
										<p>
											{item.severity} · {item.code}: {item.message}
										</p>
									</div>
								))}
							</div>
						)}
						{detailTab === "metrics" && (
							<div className="timeline">
								<p>Duration: {duration(selected, now)}</p>
								<p>
									Last measured speech-end to playback-start latency:{" "}
									{typeof selected.metrics.last_e2e_latency_ms === "number"
										? `${selected.metrics.last_e2e_latency_ms} ms`
										: "not measured"}
								</p>
								<p className="subtle">
									Server-side metric; browser speaker latency is not measured.
								</p>
								<h3>Provider usage</h3>
								{usageRows(selected.metrics.usage).length === 0 && (
									<p>Not measured</p>
								)}
								{usageRows(selected.metrics.usage).map((item) => (
									<p
										key={`${String(item.type)}-${String(item.provider)}-${String(item.model)}`}
									>
										<strong>
											{String(item.provider)} · {String(item.model)}
										</strong>
										: {String(item.input_tokens ?? 0)} input tokens,{" "}
										{String(item.output_tokens ?? 0)} output tokens,{" "}
										{String(item.characters_count ?? 0)} characters,{" "}
										{String(item.audio_duration ?? 0)}s audio
									</p>
								))}
							</div>
						)}
					</aside>
				</div>
			)}
		</section>
	);
}
