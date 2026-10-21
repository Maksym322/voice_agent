import { type FormEvent, useCallback, useEffect, useState } from "react";

type Identity = { role: string; csrf_token: string };
type Agent = {
	id: string;
	name: string;
	revision: number;
	current_sessions: number;
	config: Record<string, unknown>;
};
type Version = { id: string; number: number };
type Binding = { environment: string; version_id: string; revision: number };

const SUPPORTED_PROVIDERS = [
	{ id: "google", label: "Google" },
	{ id: "openai", label: "OpenAI" },
] as const;

const SUPPORTED_MODELS: Record<string, { id: string; label: string }[]> = {
	google: [
		{ id: "gemini-3.5-flash-lite", label: "gemini-3.5-flash-lite" },
		{ id: "gemini-2.5-flash-lite", label: "gemini-2.5-flash-lite" },
	],
	openai: [{ id: "gpt-4o-mini", label: "gpt-4o-mini" }],
};

const VALID_PAIRS: Record<string, readonly string[]> = {
	google: ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite"],
	openai: ["gpt-4o-mini"],
};

function validateVoiceConfig(cfg: unknown): {
	valid: boolean;
	error?: string;
	effectiveProvider: "google" | "openai";
	effectiveModel: string;
} {
	if (!cfg || typeof cfg !== "object" || Array.isArray(cfg)) {
		return {
			valid: false,
			error: "Configuration must be a JSON object.",
			effectiveProvider: "openai",
			effectiveModel: "gpt-4o-mini",
		};
	}
	const rec = cfg as Record<string, unknown>;
	if (rec.voice === undefined || rec.voice === null) {
		return {
			valid: true,
			effectiveProvider: "openai",
			effectiveModel: "gpt-4o-mini",
		};
	}
	if (typeof rec.voice !== "object" || Array.isArray(rec.voice)) {
		return {
			valid: false,
			error: "voice must be a JSON object.",
			effectiveProvider: "openai",
			effectiveModel: "gpt-4o-mini",
		};
	}
	const voice = rec.voice as Record<string, unknown>;
	const provider =
		typeof voice.llm_provider === "string" ? voice.llm_provider : "openai";
	const model =
		typeof voice.llm_model === "string" ? voice.llm_model : "gpt-4o-mini";

	if (provider !== "openai" && provider !== "google") {
		return {
			valid: false,
			error: `voice.llm_provider must be one of openai, google (got ${String(provider)})`,
			effectiveProvider: "openai",
			effectiveModel: model,
		};
	}

	const allowedModels = VALID_PAIRS[provider];
	if (!allowedModels.includes(model)) {
		return {
			valid: false,
			error: `voice.llm_model must be one of ${allowedModels.join(", ")} for ${provider}`,
			effectiveProvider: provider as "google" | "openai",
			effectiveModel: model,
		};
	}

	return {
		valid: true,
		effectiveProvider: provider as "google" | "openai",
		effectiveModel: model,
	};
}

function extractVoice(cfg: Record<string, unknown> | null | undefined): {
	provider: string;
	model: string;
} {
	const voice = (
		cfg && typeof cfg === "object" && cfg.voice && typeof cfg.voice === "object"
			? (cfg.voice as Record<string, unknown>)
			: {}
	) as Record<string, unknown>;
	const provider =
		typeof voice.llm_provider === "string" ? voice.llm_provider : "openai";
	const model =
		typeof voice.llm_model === "string" ? voice.llm_model : "gpt-4o-mini";
	return { provider, model };
}

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
	const [createProvider, setCreateProvider] = useState("google");
	const [createModel, setCreateModel] = useState("gemini-3.5-flash-lite");
	const [editProvider, setEditProvider] = useState("openai");
	const [editModel, setEditModel] = useState("gpt-4o-mini");
	const [activeModelInfo, setActiveModelInfo] = useState<string | null>(null);
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
		const voiceCheck = validateVoiceConfig(agent.config);
		setEditProvider(voiceCheck.effectiveProvider);
		setEditModel(voiceCheck.effectiveModel);
		setError("");
		const versionsData = await api<Version[]>(
			`/api/agents/${agent.id}/versions`,
			identity,
		);
		setVersions(versionsData);
		const bindingsData = await api<Binding[]>(
			`/api/agents/${agent.id}/bindings`,
			identity,
		);
		setBindings(bindingsData);
		const localBinding = bindingsData.find(
			(item) => item.environment === "local",
		);
		if (localBinding?.version_id) {
			try {
				const activeConfig = await api<Record<string, unknown>>(
					`/api/agents/${agent.id}/versions/${localBinding.version_id}/export`,
					identity,
				);
				const activeVoice = extractVoice(activeConfig);
				setActiveModelInfo(`${activeVoice.provider} / ${activeVoice.model}`);
			} catch {
				setActiveModelInfo("unavailable");
			}
		} else {
			setActiveModelInfo(null);
		}
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

	function handleCreateProviderChange(newProv: string) {
		setCreateProvider(newProv);
		const defaultM =
			newProv === "google" ? "gemini-3.5-flash-lite" : "gpt-4o-mini";
		setCreateModel(defaultM);
	}

	function handleEditProviderChange(newProv: string) {
		let parsed: Record<string, unknown>;
		try {
			const raw = JSON.parse(configText);
			if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
				setError(
					"Cannot update provider in malformed JSON: Configuration must be a JSON object.",
				);
				return;
			}
			parsed = raw as Record<string, unknown>;
		} catch (e) {
			setError(
				`Cannot update provider in malformed JSON: ${
					e instanceof Error ? e.message : String(e)
				}`,
			);
			return;
		}

		const defaultM =
			newProv === "google" ? "gemini-3.5-flash-lite" : "gpt-4o-mini";
		const updated = {
			...parsed,
			voice: {
				...(typeof parsed.voice === "object" && parsed.voice !== null
					? (parsed.voice as Record<string, unknown>)
					: {}),
				llm_provider: newProv,
				llm_model: defaultM,
			},
		};
		setConfigText(JSON.stringify(updated, null, 2));
		setEditProvider(newProv);
		setEditModel(defaultM);
		setError("");
	}

	function handleEditModelChange(newModel: string) {
		let parsed: Record<string, unknown>;
		try {
			const raw = JSON.parse(configText);
			if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
				setError(
					"Cannot update model in malformed JSON: Configuration must be a JSON object.",
				);
				return;
			}
			parsed = raw as Record<string, unknown>;
		} catch (e) {
			setError(
				`Cannot update model in malformed JSON: ${
					e instanceof Error ? e.message : String(e)
				}`,
			);
			return;
		}

		const updated = {
			...parsed,
			voice: {
				...(typeof parsed.voice === "object" && parsed.voice !== null
					? (parsed.voice as Record<string, unknown>)
					: {}),
				llm_provider: editProvider,
				llm_model: newModel,
			},
		};
		setConfigText(JSON.stringify(updated, null, 2));
		setEditModel(newModel);
		setError("");
	}

	function handleConfigTextChange(newText: string) {
		setConfigText(newText);
		try {
			const parsed = JSON.parse(newText);
			if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
				const voiceCheck = validateVoiceConfig(parsed);
				if (voiceCheck.valid) {
					setError("");
					setEditProvider(voiceCheck.effectiveProvider);
					setEditModel(voiceCheck.effectiveModel);
				} else {
					setError(voiceCheck.error ?? "Unsupported voice LLM pair.");
				}
			}
		} catch {
			// Do not disrupt editing while typing malformed JSON
		}
	}

	function create(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		void run(async () => {
			const agent = await api<Agent>("/api/agents", identity, "POST", {
				name,
				config: {
					schema_version: 1,
					instructions,
					voice: {
						llm_provider: createProvider,
						llm_model: createModel,
					},
				},
			});
			await choose(agent);
			setMessage("Agent created.");
		});
	}

	function save(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (!selected) return;
		let parsed: Record<string, unknown>;
		try {
			const raw = JSON.parse(configText);
			if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
				setError("Configuration must be a JSON object.");
				return;
			}
			parsed = raw as Record<string, unknown>;
		} catch (e) {
			setError(
				`Invalid configuration JSON: ${
					e instanceof Error ? e.message : String(e)
				}`,
			);
			return;
		}
		const voiceCheck = validateVoiceConfig(parsed);
		if (!voiceCheck.valid) {
			setError(voiceCheck.error ?? "Unsupported voice LLM pair.");
			return;
		}
		void run(async () => {
			const agent = await api<Agent>(
				`/api/agents/${selected.id}/draft`,
				identity,
				"PUT",
				{ name, config: parsed },
				selected.revision,
			);
			await choose(agent);
			setMessage("Draft saved.");
		});
	}

	const savedDraftVoice = extractVoice(selected?.config);
	const editModelOptions = SUPPORTED_MODELS[editProvider] ?? [];

	return (
		<section aria-label="Agent configurations">
			<h2>Agent configurations</h2>
			<label htmlFor="agent-select">Agent</label>
			<select
				id="agent-select"
				value={selected?.id ?? ""}
				onChange={(event) => {
					const agent = agents.find((item) => item.id === event.target.value);
					if (agent) {
						void choose(agent).catch((reason: unknown) =>
							setError(String(reason)),
						);
					} else {
						setSelected(null);
						setName("");
						setInstructions("");
						setConfigText("");
						setCreateProvider("google");
						setCreateModel("gemini-3.5-flash-lite");
						setVersions([]);
						setBindings([]);
						setActiveModelInfo(null);
					}
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
					<label htmlFor="new-llm-provider">LLM provider</label>
					<select
						id="new-llm-provider"
						value={createProvider}
						onChange={(event) => handleCreateProviderChange(event.target.value)}
					>
						{SUPPORTED_PROVIDERS.map((p) => (
							<option key={p.id} value={p.id}>
								{p.label}
							</option>
						))}
					</select>
					<label htmlFor="new-llm-model">LLM model</label>
					<select
						id="new-llm-model"
						value={createModel}
						onChange={(event) => setCreateModel(event.target.value)}
					>
						{(SUPPORTED_MODELS[createProvider] ?? []).map((m) => (
							<option key={m.id} value={m.id}>
								{m.label}
							</option>
						))}
					</select>
					<p>
						Selected LLM: {createProvider === "google" ? "Google" : "OpenAI"} /{" "}
						{createModel}
					</p>
					<button type="submit">Create</button>
				</form>
			)}
			{selected && (
				<>
					<p>Draft revision {selected.revision}</p>
					<p>Current sessions: {selected.current_sessions}</p>
					<p>
						Draft LLM: {savedDraftVoice.provider} / {savedDraftVoice.model}
					</p>
					{canEdit ? (
						<form onSubmit={save}>
							<label htmlFor="agent-name">Name</label>
							<input
								id="agent-name"
								value={name}
								onChange={(event) => setName(event.target.value)}
								required
							/>
							<label htmlFor="agent-llm-provider">LLM provider</label>
							<select
								id="agent-llm-provider"
								value={editProvider}
								onChange={(event) =>
									handleEditProviderChange(event.target.value)
								}
							>
								{SUPPORTED_PROVIDERS.map((p) => (
									<option key={p.id} value={p.id}>
										{p.label}
									</option>
								))}
							</select>
							<label htmlFor="agent-llm-model">LLM model</label>
							<select
								id="agent-llm-model"
								value={editModel}
								onChange={(event) => handleEditModelChange(event.target.value)}
							>
								{editModelOptions.map((m) => (
									<option key={m.id} value={m.id}>
										{m.label}
									</option>
								))}
							</select>
							<label htmlFor="agent-config">Configuration JSON</label>
							<textarea
								id="agent-config"
								rows={14}
								value={configText}
								onChange={(event) => handleConfigTextChange(event.target.value)}
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
								onClick={() => {
									let parsed: unknown;
									try {
										parsed = JSON.parse(configText);
									} catch (e) {
										setError(
											`Invalid configuration JSON: ${
												e instanceof Error ? e.message : String(e)
											}`,
										);
										return;
									}
									if (
										!parsed ||
										typeof parsed !== "object" ||
										Array.isArray(parsed)
									) {
										setError("Configuration must be a JSON object.");
										return;
									}
									const voiceCheck = validateVoiceConfig(parsed);
									if (!voiceCheck.valid) {
										setError(voiceCheck.error ?? "Unsupported voice LLM pair.");
										return;
									}
									void run(async () => {
										const imported = await api<Agent>(
											`/api/agents/${selected.id}/import`,
											identity,
											"POST",
											parsed,
											selected.revision,
										);
										await choose(imported);
										setMessage("Configuration imported into draft.");
									});
								}}
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
												const updatedAgent = await api<Agent>(
													`/api/agents/${selected.id}`,
													identity,
												);
												await choose(updatedAgent);
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
					<p>Local active LLM: {activeModelInfo ?? "unavailable"}</p>
				</>
			)}
			{message && <p role="status">{message}</p>}
			{error && <p role="alert">{error}</p>}
		</section>
	);
}
