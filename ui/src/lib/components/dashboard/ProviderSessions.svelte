<script lang="ts">
	import { onMount, onDestroy } from "svelte";

	type Session = { connection_id: string; provider: string; name: string; cwd: string; session_id: string; available: boolean; selected: boolean; draft: string; delivery_failed: boolean };
	type Turn = { id: string; status: string; response: string };
	let sessions = $state<Session[]>([]);
	let cwd = $state("");
	let resumeId = $state("");
	let error = $state("");
	let busy = $state(false);
	let expanded = $state<string | null>(null);
	let turns = $state<Turn[]>([]);
	let timer: ReturnType<typeof setInterval>;

	async function request(path: string, options?: RequestInit) {
		const result = await fetch(path, options);
		const data = await result.json();
		if (!result.ok) throw new Error(data.detail ?? "Request failed");
		return data;
	}
	async function refresh() {
		try {
			const data = await request("/api/provider-sessions");
			sessions = data.sessions;
			if (data.failed) error = "A provider could not be verified. Its sessions are unavailable.";
			if (expanded && sessions.some(s => s.connection_id === expanded && s.available)) {
				turns = (await request(`/api/provider-sessions/${expanded}/turns`)).turns;
			}
		} catch (e) { error = String(e); }
	}
	async function action(fn: () => Promise<void>) {
		busy = true; error = "";
		try { await fn(); await refresh(); } catch (e) { error = String(e); } finally { busy = false; }
	}
	function start(resume: boolean) {
		if (resume && !resumeId.trim()) { error = "Enter a session ID to resume."; return; }
		return action(async () => { await request("/api/provider-sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cwd, resume_id: resume ? resumeId.trim() : null }) }); });
	}
	function stop(session: Session) {
		if (session.draft && !confirm("This session has an unsent draft. Stop and discard it?")) return;
		return action(async () => { await request(`/api/provider-sessions/${session.connection_id}`, { method: "DELETE" }); if (expanded === session.connection_id) { expanded = null; turns = []; } });
	}
	onMount(() => { refresh(); timer = setInterval(refresh, 5000); });
	onDestroy(() => clearInterval(timer));
</script>

<section class="rounded-lg border bg-card p-4 space-y-3" aria-label="Managed Codex sessions">
	<h3 class="text-sm font-semibold">Managed Codex sessions</h3>
	<p class="text-sm text-muted-foreground">Start a session here, or resume a saved Codex session by ID. Resuming creates a new connection; it does not control an existing terminal. Codex can write in the working folder. Requests for approval are declined.</p>
	<div class="flex flex-wrap gap-2">
		<label class="flex flex-col gap-1 text-sm grow">Working folder<input class="rounded border bg-background px-2 py-1" placeholder="/absolute/path" bind:value={cwd} /></label>
		<label class="flex flex-col gap-1 text-sm grow">Session ID (for resume)<input class="rounded border bg-background px-2 py-1" bind:value={resumeId} /></label>
	</div>
	<div class="flex flex-wrap gap-2">
		<button class="rounded border px-3 py-1 text-sm" disabled={busy || !cwd.trim()} onclick={() => start(false)}>Start new</button>
		<button class="rounded border px-3 py-1 text-sm" disabled={busy || !cwd.trim()} onclick={() => start(true)}>Resume history</button>
	</div>
	{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
	{#each sessions as session (session.connection_id)}
		<div class="rounded border p-3 space-y-2 min-w-0">
			<p class="text-sm font-semibold break-all">{session.provider}: {session.name}</p>
			<p class="text-xs break-all">Folder: {session.cwd}<br />Session ID: {session.session_id}</p>
			<p class="text-xs">{session.available ? (session.selected ? "Selected" : "Available") : "Unavailable — choose another target explicitly"}</p>
			{#if session.delivery_failed}<p class="text-sm text-destructive">Delivery could not be confirmed. Copy the draft before stopping; it will not be retried automatically.</p>{/if}
			{#if session.draft}<label class="block text-sm">Unsent or unconfirmed draft<textarea class="block w-full rounded border bg-background p-2" readonly value={session.draft}></textarea></label>{/if}
			<div class="flex flex-wrap gap-2">
				<button class="rounded border px-3 py-1 text-sm" disabled={busy || !session.available || session.selected} onclick={() => action(async () => { await request(`/api/provider-sessions/${session.connection_id}/select`, { method: "POST" }); })}>Select</button>
				<button class="rounded border px-3 py-1 text-sm" disabled={!session.available} onclick={() => { expanded = expanded === session.connection_id ? null : session.connection_id; turns = []; refresh(); }}>{expanded === session.connection_id ? "Hide responses" : "Show responses"}</button>
				<button class="rounded border px-3 py-1 text-sm" disabled={busy} onclick={() => stop(session)}>Stop</button>
			</div>
			{#if expanded === session.connection_id}
				{#each turns as turn (turn.id)}<div class="whitespace-pre-wrap break-words text-sm"><span class="text-xs text-muted-foreground">{turn.status}</span><br />{turn.response || "Waiting for response…"}</div>{/each}
			{/if}
		</div>
	{/each}
</section>
