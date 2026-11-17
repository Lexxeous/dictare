<script lang="ts">
	import { onMount } from "svelte";
	import { Mic, MicOff } from "lucide-svelte";
	import { Button } from "$lib/components/ui/button";
	import { fetchStatus, type StatusResponse } from "$lib/api";
	import { hotkeyLabel, listeningLabel, setListening, strictMute } from "$lib/listening";
	import { getSchema } from "$lib/stores/settings.svelte";
	import ReviewPanel from "./ReviewPanel.svelte";

	let status = $state<StatusResponse | null>(null);
	let error = $state("");
	let pending = $state(false);
	let reviewPending = $state(false);
	let strictRequest = $state(false);
	let waitingFor: boolean | null = $state(null);
	let waitStarted = 0;
	const active = $derived(status?.stt.active ?? false);
	const strict = $derived(status?.platform.state === "strict_muted");
	const loading = $derived(status?.platform.loading?.active ?? false);
	const personal = $derived(getSchema()?.voice_commands ?? getSchema()?.values.voice_commands as { enabled?: boolean; mute?: string; listen?: string; send?: string } | undefined);
	function phrases(action: "mute" | "listen" | "send", fallback: string): string {
		const value = personal?.[action] || String(getSchema()?.presets[`voice_commands.${action}`]?.default ?? "");
		return personal?.enabled ? value.split(/\r?\n/).map((phrase) => phrase.trim()).filter(Boolean).map((phrase) => `“${phrase}”`).join(" / ") : fallback;
	}

	onMount(() => {
		let disposed = false;
		let busy = false;
		async function refresh() {
			if (busy) return;
			busy = true;
			try {
				const next = await fetchStatus();
				if (disposed) return;
				status = next;
				if (error.startsWith("Cannot reach Dictare.")) error = "";
				if (waitingFor !== null && next.stt.active === waitingFor) waitingFor = null;
				if (waitingFor !== null && Date.now() - waitStarted > 15000) {
					waitingFor = null;
					error = "Dictare has not changed listening yet. Check its status before trying again.";
				}
			} catch {
				if (!disposed) {
					status = null;
					waitingFor = null;
					error = "Cannot reach Dictare. Start it from your usual launcher, then try again.";
				}
			} finally { busy = false; }
		}
		void refresh();
		const timer = setInterval(refresh, 1000);
		return () => { disposed = true; clearInterval(timer); };
	});

	async function enterStrictMute() {
		if (!status || strictRequest || reviewPending) return;
		strictRequest = true;
		error = "";
		try {
			await strictMute();
		} catch (cause) {
			error = (cause as Error).message || "Could not confirm strict mute.";
		} finally {
			strictRequest = false;
		}
	}

	async function toggleListening() {
		if (!status || pending || waitingFor !== null) return;
		const on = !active;
		pending = true;
		error = "";
		try {
			await setListening(on);
			waitingFor = on;
			waitStarted = Date.now();
		} catch {
			error = "Could not confirm the change. Check Dictare's status before trying again.";
		} finally { pending = false; }
	}
</script>

<section class="px-4 space-y-6" aria-label="Everyday Dictare controls">
	<div class="rounded-lg border p-5 space-y-4">
		<p role="status" class="text-lg">{loading ? "Getting ready…" : strict && status?.platform.strict_mute_pending ? "Turning on strict mute…" : strict && status?.platform.strict_mute_error ? "Strict mute needs attention" : status ? listeningLabel(status.platform.state) : "Connecting to Dictare…"}</p>
		<p class="text-sm text-muted-foreground">Speak naturally, then pause to let Dictare write your words.</p>
		<Button size="lg" class="w-full sm:w-auto h-auto min-h-11 whitespace-normal" onclick={toggleListening} disabled={!status || loading || pending || waitingFor !== null || reviewPending || strict || strictRequest}>
			{#if active}<MicOff />{:else}<Mic />{/if}
			{strict ? "Resume with hotkey" : pending ? "Requesting change…" : waitingFor !== null ? "Waiting for listening to change…" : active ? "Stop listening" : "Start listening"}
		</Button>
		<p class="text-sm text-muted-foreground">Stopping listening keeps Dictare open. A current sentence may finish processing first.</p>
		{#if strict}
			{#if status?.platform.strict_mute_source_test}
				<p class="text-sm">Use the development hotkey simulator to resume.</p>
			{:else}
				<p class="text-sm">Press {status ? hotkeyLabel(status.platform.hotkey.key) : "your hotkey"} to resume.</p>
			{/if}
			{#if status?.platform.strict_mute_pending}<p role="status" class="text-sm">Stopping microphone and audio…</p>{/if}
			{#if status?.platform.strict_mute_error}<p role="alert" class="text-sm text-destructive">Strict mute needs attention: {status.platform.strict_mute_error}</p>{/if}
		{:else}
			<div class="space-y-2">
				<Button variant="outline" onclick={enterStrictMute} disabled={!status || loading || pending || waitingFor !== null || reviewPending || strictRequest || !status.platform.strict_mute_available}>
					{strictRequest ? "Turning on strict mute…" : "Strict mute"}
				</Button>
				<p class="text-sm text-muted-foreground">Strict mute turns off microphone input and audio. Only your hotkey can resume listening.</p>
				{#if status && !status.platform.strict_mute_available}<p class="text-sm">A working hotkey is required to use strict mute.</p>{/if}
			</div>
		{/if}
		{#if status?.platform.state === "muted"}
			<p class="text-sm">Voice mute still hears the “listen” command. Use Stop listening above to turn listening off.</p>
			{#if status.platform.voice_mute_error}<p role="alert" class="text-sm text-destructive">Mute needs attention: {status.platform.voice_mute_error}</p>{/if}
		{/if}
		{#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
	</div>
	<ReviewPanel ready={status?.platform.state === "off"} onPendingChange={(value) => reviewPending = value} />
	<div class="rounded-lg border p-5 space-y-2 break-words">
		<h3 class="font-medium">Where your words go</h3>
		{#if status?.platform.output.mode === "keyboard"}
			<p>Words are typed into the app you are using. Click the text box you want to write in first.</p>
		{:else if status?.platform.output.current_agent}
			<p>Words go to <strong>{status.platform.output.current_agent}</strong>.</p>
		{:else}
			<p>No assistant is connected yet. Connect one, or choose Keyboard on the Dashboard to write into an app.</p>
		{/if}
	</div>
	<div class="space-y-3">
		<h3 class="text-lg">Voice command cheat sheet</h3>
		<p class="text-sm text-muted-foreground">{personal?.enabled ? "Your saved personal commands. Change them in Commands." : "These are the default English phrases. Advanced settings may use different commands. Choose Commands to set your own."}</p>
		<dl class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
			<dt class="font-medium break-words">{phrases("send", "“OK, send” or “OK, submit”")}</dt><dd>Send your words to the assistant.</dd>
			<dt class="font-medium break-words">{phrases("mute", "“OK, mute” or “OK, hold on”")}</dt><dd>Pause dictation by voice.</dd>
			<dt class="font-medium break-words">{phrases("listen", "“OK, listen” or “OK, listen up”")}</dt><dd>Resume dictation after standard voice mute.</dd>
			<dt class="font-medium">“Agent” followed by its name</dt><dd>Switch to another connected assistant.</dd>
		</dl>
	</div>
	<div class="space-y-3 pb-4">
		<h3 class="text-lg">Keyboard cheat sheet</h3>
		<p>Your shortcut key: <strong>{status ? hotkeyLabel(status.platform.hotkey.key) : "Checking…"}</strong></p>
		{#if status && !status.platform.hotkey.bound}<p class="text-sm">The shortcut is unavailable right now. You can use the listening button above.</p>{/if}
		<ul class="list-disc pl-5 space-y-2 text-sm">
			<li>Tap once to switch listening on or off.</li>
			<li>Tap twice to send your words.</li>
			<li>Hold Right Alt and tap the shortcut to switch between an assistant and typing into an app.</li>
		</ul>
		<p class="text-sm text-muted-foreground">Use Documentation for the full guide. Keyboard settings let you change shortcuts.</p>
	</div>
</section>
