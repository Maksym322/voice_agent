import { type FormEvent, useEffect, useState } from "react";
import { AgentEditor } from "./AgentEditor";

type Identity = {
	id: string;
	email: string;
	role: "admin" | "operator" | "viewer";
	csrf_token: string;
};

async function jsonResponse(response: Response): Promise<Identity> {
	if (!response.ok) {
		if (response.status === 401)
			throw new Error("Invalid credentials or session expired.");
		throw new Error("The service is unavailable. Please try again.");
	}
	return (await response.json()) as Identity;
}

export function App() {
	const [identity, setIdentity] = useState<Identity | null>(null);
	const [loading, setLoading] = useState(true);
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [error, setError] = useState("");

	useEffect(() => {
		const controller = new AbortController();
		fetch("/api/auth/me", {
			credentials: "same-origin",
			signal: controller.signal,
		})
			.then(async (response) => {
				if (response.status === 401) return null;
				return jsonResponse(response);
			})
			.then(setIdentity)
			.catch((reason: unknown) => {
				if (!controller.signal.aborted) setError(String(reason));
			})
			.finally(() => {
				if (!controller.signal.aborted) setLoading(false);
			});
		return () => controller.abort();
	}, []);

	async function signIn(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError("");
		try {
			const response = await fetch("/api/auth/login", {
				method: "POST",
				credentials: "same-origin",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ email, password }),
			});
			setIdentity(await jsonResponse(response));
			setPassword("");
		} catch (reason) {
			setError(String(reason));
		}
	}

	async function signOut() {
		setError("");
		try {
			const response = await fetch("/api/auth/logout", {
				method: "POST",
				credentials: "same-origin",
				headers: { "X-CSRF-Token": identity?.csrf_token ?? "" },
			});
			if (!response.ok) throw new Error("Sign-out failed. Please try again.");
			setIdentity(null);
		} catch (reason) {
			setError(String(reason));
		}
	}

	return (
		<main className="shell">
			<header>
				<p className="eyebrow">Voice Fleet</p>
				<h1>Operator dashboard</h1>
				<p className="subtle">
					Foundation access for one independent installation.
				</p>
			</header>
			{loading ? (
				<p role="status">Checking your session…</p>
			) : identity ? (
				<section aria-label="Dashboard">
					<p>
						Signed in as <strong>{identity.email}</strong>
					</p>
					<p>Role: {identity.role}</p>
					<p className="subtle">
						Voice sessions are not available in this foundation build.
					</p>
					<AgentEditor identity={identity} />
					<button type="button" onClick={signOut}>
						Sign out
					</button>
				</section>
			) : (
				<section aria-label="Sign in">
					<h2>Sign in</h2>
					<form onSubmit={signIn}>
						<label htmlFor="email">Email</label>
						<input
							id="email"
							type="email"
							autoComplete="username"
							value={email}
							onChange={(event) => setEmail(event.target.value)}
							required
						/>
						<label htmlFor="password">Password</label>
						<input
							id="password"
							type="password"
							autoComplete="current-password"
							value={password}
							onChange={(event) => setPassword(event.target.value)}
							required
						/>
						<button type="submit">Sign in</button>
					</form>
				</section>
			)}
			{error && <p role="alert">{error}</p>}
		</main>
	);
}
