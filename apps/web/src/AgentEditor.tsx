import { type FormEvent, useCallback, useEffect, useState } from "react";

type Identity = { role: string; csrf_token: string };
type Agent = {
	id: string;
	name: string;
	revision: number;
	config: Record<string, unknown>;
};
type Version = { id: string; number: number };
type Binding = { environment: string; version_id: string; revision: number };

async function api<T>(
	path: string,
	identity: Identity,
	method = "GET",
	body?: unknown,
	revision?: number,
): Promise<T> {
	const response = await fetch(path, {
		method,
		credentials: "same-origin",
		headers: {
			...(method !== "GET"
				? {
						Origin: window.location.origin,
						"X-CSRF-Token": identity.csrf_token,
					}
				: {}),
			...(body !== undefined ? { "Content-Type": "application/json" } : {}),
			...(revision !== undefined ? { "If-Match": String(revision) } : {}),
		},
		...(body !== undefined ? { body: JSON.stringify(body) } : {}),
	});
	if (!response.ok) {
		const detail = (await response.json().catch(() => ({}))) as {
			detail?: unknown;
		};
		throw new Error(
			typeof detail.detail === "string"
				? detail.detail
				: JSON.stringify(
						detail.detail ?? `Request failed (${response.status})`,
					),
		);
	}
	return (await response.json()) as T;
}

export function AgentEditor({ identity }: { identity: Identity }) {
	const [agents, setAgents] = useState<Agent[]>([]);
	const [selected, setSelected] = useState<Agent | null>(null);
	const [name, setName] = useState("");
	const [instructions, setInstructions] = useState("");
	const [configText, setConfigText] = useState("");
	const [versions, setVersions] = useState<Version[]>([]);
	const [bindings, setBindings] = useState<Binding[]>([]);
	const [error, setError] = useState("");
	const [message, setMessage] = useState("");
	const canEdit = identity.role === "admin" || identity.role === "operator";
	const refresh = useCallback(async () => {
		setAgents(await api<Agent[]>("/api/agents", identity));
	}, [identity]);
	useEffect(() => {
		refresh().catch((reason: unknown) => setError(String(reason)));
	}, [refresh]);

	async function choose(agent: Agent) {
		setSelected(agent);
		setName(agent.name);
		setInstructions(String(agent.config.instructions ?? ""));
		setConfigText(JSON.stringify(agent.config, null, 2));
		setVersions(
			await api<Version[]>(`/api/agents/${agent.id}/versions`, identity),
		);
		setBindings(
			await api<Binding[]>(`/api/agents/${agent.id}/bindings`, identity),
		);
	}

	async function run(action: () => Promise<void>) {
		setError("");
		setMessage("");
		try {
			await action();
			await refresh();
		} catch (reason) {
			setError(String(reason));
		}
	}

	function create(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		void run(async () => {
			const agent = await api<Agent>("/api/agents", identity, "POST", {
				name,
				config: { schema_version: 1, instructions },
			});
			await choose(agent);
			setMessage("Agent created.");
		});
	}

	function save(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (!selected) return;
		void run(async () => {
			const agent = await api<Agent>(
				`/api/agents/${selected.id}/draft`,
				identity,
				"PUT",
				{ name, config: JSON.parse(configText) as unknown },
				selected.revision,
			);
			await choose(agent);
			setMessage("Draft saved.");
		});
	}

	return (
		<section aria-label="Agent configurations">
			<h2>Agent configurations</h2>
			<label htmlFor="agent-select">Agent</label>
			<select
				id="agent-select"
				value={selected?.id ?? ""}
				onChange={(event) => {
					const agent = agents.find((item) => item.id === event.target.value);
					if (agent)
						void choose(agent).catch((reason: unknown) =>
							setError(String(reason)),
						);
				}}
			>
				<option value="">Choose an agent</option>
				{agents.map((agent) => (
					<option key={agent.id} value={agent.id}>
						{agent.name}
					</option>
				))}
			</select>
			{canEdit && !selected && (
				<form onSubmit={create}>
					<h3>Create agent</h3>
					<label htmlFor="new-name">Name</label>
					<input
						id="new-name"
						value={name}
						onChange={(event) => setName(event.target.value)}
						required
					/>
					<label htmlFor="new-instructions">Instructions</label>
					<textarea
						id="new-instructions"
						value={instructions}
						onChange={(event) => setInstructions(event.target.value)}
						required
					/>
					<button type="submit">Create</button>
				</form>
			)}
			{selected && (
				<>
					<p>Draft revision {selected.revision}</p>
					{canEdit ? (
						<form onSubmit={save}>
							<label htmlFor="agent-name">Name</label>
							<input
								id="agent-name"
								value={name}
								onChange={(event) => setName(event.target.value)}
								required
							/>
							<label htmlFor="agent-config">Configuration JSON</label>
							<textarea
								id="agent-config"
								rows={14}
								value={configText}
								onChange={(event) => setConfigText(event.target.value)}
								required
							/>
							<button type="submit">Save draft</button>
						</form>
					) : (
						<pre>{configText}</pre>
					)}
					{canEdit && (
						<>
							<button
								type="button"
								onClick={() =>
									void run(async () => {
										const version = await api<Version>(
											`/api/agents/${selected.id}/publish`,
											identity,
											"POST",
											undefined,
											selected.revision,
										);
										setMessage(`Published v${version.number}.`);
										await choose(
											await api<Agent>(`/api/agents/${selected.id}`, identity),
										);
									})
								}
							>
								Publish draft
							</button>
							<button
								type="button"
								onClick={() =>
									void run(async () => {
										const imported = await api<Agent>(
											`/api/agents/${selected.id}/import`,
											identity,
											"POST",
											JSON.parse(configText) as unknown,
											selected.revision,
										);
										await choose(imported);
										setMessage("Configuration imported into draft.");
									})
								}
							>
								Import JSON into draft
							</button>
						</>
					)}
					<h3>Published versions</h3>
					<ul>
						{versions.map((version) => (
							<li key={version.id}>
								v{version.number}{" "}
								<button
									type="button"
									onClick={() =>
										void run(async () => {
											const config = await api<Record<string, unknown>>(
												`/api/agents/${selected.id}/versions/${version.id}/export`,
												identity,
											);
											const blob = new Blob([JSON.stringify(config, null, 2)], {
												type: "application/json",
											});
											const link = document.createElement("a");
											link.href = URL.createObjectURL(blob);
											link.download = `${selected.name}-v${version.number}.json`;
											link.click();
											URL.revokeObjectURL(link.href);
										})
									}
								>
									Export
								</button>
								{canEdit && (
									<button
										type="button"
										onClick={() =>
											void run(async () => {
												const current = bindings.find(
													(item) => item.environment === "local",
												);
												await api(
													`/api/agents/${selected.id}/bindings/local`,
													identity,
													"PUT",
													{
														version_id: version.id,
														expected_revision: current?.revision ?? 0,
													},
												);
												await choose(selected);
												setMessage(
													`Local binding switched to v${version.number}.`,
												);
											})
										}
									>
										Activate locally
									</button>
								)}
							</li>
						))}
					</ul>
					<p>
						Local active version:{" "}
						{versions.find(
							(version) =>
								version.id ===
								bindings.find((item) => item.environment === "local")
									?.version_id,
						)?.number ?? "none"}
					</p>
				</>
			)}
			{message && <p role="status">{message}</p>}
			{error && <p role="alert">{error}</p>}
		</section>
	);
}
