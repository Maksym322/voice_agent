import { Room, RoomEvent, Track } from "livekit-client";
import { useEffect, useRef, useState } from "react";

type Identity = { role: string; csrf_token: string };
type Agent = { id: string; name: string };
type Session = {
	id: string;
	version_id: string;
	status: string;
	deadline_at: string;
	end_reason: string | null;
	error_code: string | null;
	metrics: Record<string, unknown>;
	url?: string;
	token?: string;
};
type Event = {
	id: string;
	kind: string;
	speaker: string | null;
	text: string | null;
	details: Record<string, unknown>;
};

async function request<T>(path: string, identity: Identity, method = "GET") {
	const response = await fetch(path, {
		method,
		credentials: "same-origin",
		headers:
			method === "GET"
				? undefined
				: { "X-CSRF-Token": identity.csrf_token, Origin: location.origin },
	});
	if (!response.ok) {
		const body = (await response.json().catch(() => ({}))) as {
			detail?: string;
		};
		throw new Error(body.detail ?? `Request failed (${response.status})`);
	}
	return (await response.json()) as T;
}

export function VoicePlayground({ identity }: { identity: Identity }) {
	const [agents, setAgents] = useState<Agent[]>([]);
	const [agentId, setAgentId] = useState("");
	const [session, setSession] = useState<Session | null>(null);
	const [events, setEvents] = useState<Event[]>([]);
	const [error, setError] = useState("");
	const [audioBlocked, setAudioBlocked] = useState(false);
	const [secondsLeft, setSecondsLeft] = useState(0);
	const roomRef = useRef<Room | null>(null);
	const audioRef = useRef<HTMLDivElement>(null);
	const activeId = useRef<string | null>(null);
	const canStart = identity.role === "admin" || identity.role === "operator";
	const sessionId = session?.id;
	const deadline = session?.deadline_at;

	useEffect(() => {
		if (!canStart) return;
		void request<Agent[]>("/api/agents", identity)
			.then(setAgents)
			.catch((reason: unknown) => setError(String(reason)));
	}, [identity, canStart]);

	useEffect(() => {
		if (!sessionId || !deadline) return;
		const timer = window.setInterval(() => {
			setSecondsLeft(
				Math.max(0, Math.ceil((Date.parse(deadline) - Date.now()) / 1000)),
			);
			void Promise.all([
				request<Session>(`/api/sessions/${sessionId}`, identity),
				request<Event[]>(`/api/sessions/${sessionId}/events`, identity),
			])
				.then(([updated, history]) => {
					setSession(updated);
					setEvents(history);
					if (updated.status === "ended" || updated.status === "error") {
						activeId.current = null;
						void roomRef.current?.disconnect();
					}
				})
				.catch((reason: unknown) => setError(String(reason)));
		}, 2000);
		return () => window.clearInterval(timer);
	}, [sessionId, deadline, identity]);

	useEffect(() => {
		return () => {
			void roomRef.current?.disconnect();
			if (activeId.current) {
				void request(
					`/api/sessions/${activeId.current}/end`,
					identity,
					"POST",
				).catch(() => undefined);
			}
		};
	}, [identity]);

	async function start() {
		if (!agentId) return;
		setError("");
		setEvents([]);
		let created: Session | null = null;
		try {
			created = await request<Session>(
				`/api/agents/${agentId}/sessions`,
				identity,
				"POST",
			);
			if (!created.url || !created.token)
				throw new Error("Room credentials were not issued");
			setSession(created);
			activeId.current = created.id;
			const room = new Room();
			roomRef.current = room;
			room.on(RoomEvent.TrackSubscribed, (track) => {
				if (track.kind === Track.Kind.Audio) {
					const element = track.attach();
					audioRef.current?.appendChild(element);
				}
			});
			room.on(RoomEvent.TrackUnsubscribed, (track) => {
				for (const element of track.detach()) element.remove();
			});
			room.on(RoomEvent.AudioPlaybackStatusChanged, () =>
				setAudioBlocked(!room.canPlaybackAudio),
			);
			room.on(RoomEvent.Disconnected, () => {
				if (activeId.current === created?.id) {
					setError("Voice connection ended.");
					void request(
						`/api/sessions/${created.id}/end`,
						identity,
						"POST",
					).catch(() => undefined);
					activeId.current = null;
				}
			});
			await room.connect(created.url, created.token);
			await room.localParticipant.setMicrophoneEnabled(true);
			setAudioBlocked(!room.canPlaybackAudio);
		} catch (reason) {
			setError(String(reason));
			await roomRef.current?.disconnect();
			roomRef.current = null;
			if (created) {
				activeId.current = null;
				void request(`/api/sessions/${created.id}/end`, identity, "POST").catch(
					() => undefined,
				);
			}
		}
	}

	async function end() {
		if (!session) return;
		setError("");
		try {
			const updated = await request<Session>(
				`/api/sessions/${session.id}/end`,
				identity,
				"POST",
			);
			activeId.current = null;
			setSession(updated);
			await roomRef.current?.disconnect();
		} catch (reason) {
			setError(String(reason));
		}
	}

	if (!canStart) return null;
	return (
		<section aria-label="Voice playground">
			<h2>Voice playground</h2>
			<label htmlFor="voice-agent">Agent</label>
			<select
				id="voice-agent"
				value={agentId}
				onChange={(event) => setAgentId(event.target.value)}
				disabled={session?.status === "pending" || session?.status === "active"}
			>
				<option value="">Choose an agent</option>
				{agents.map((agent) => (
					<option key={agent.id} value={agent.id}>
						{agent.name}
					</option>
				))}
			</select>
			{!session || session.status === "ended" || session.status === "error" ? (
				<button type="button" disabled={!agentId} onClick={() => void start()}>
					Start voice session
				</button>
			) : (
				<button type="button" onClick={() => void end()}>
					End session
				</button>
			)}
			{audioBlocked && (
				<button
					type="button"
					onClick={() => void roomRef.current?.startAudio()}
				>
					Enable speaker
				</button>
			)}
			{session && (
				<p role="status">
					{session.status} · {secondsLeft}s remaining · version{" "}
					{session.version_id}
					{session.error_code && ` · ${session.error_code}`}
				</p>
			)}
			<div ref={audioRef} />
			<h3>Transcript</h3>
			<ol aria-label="Voice transcript">
				{events
					.filter((event) => event.kind === "transcript" && event.text)
					.map((event) => (
						<li key={event.id}>
							<strong>{event.speaker}</strong>: {event.text}{" "}
							{event.details.final === false && <em>(interim)</em>}
							{event.details.interrupted === true && <em>(interrupted)</em>}
						</li>
					))}
			</ol>
			{error && <p role="alert">{error}</p>}
		</section>
	);
}
