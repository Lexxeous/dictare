<script lang="ts">
	import { onMount } from "svelte";
	import { Button } from "$lib/components/ui/button";
	import { fetchReview, resolveReview, type ReviewDraft } from "$lib/review";

	let { ready, onPendingChange }: { ready: boolean; onPendingChange: (pending: boolean) => void } = $props();
	let draft = $state<ReviewDraft | null>(null);
	let busy = $state(false);
	let error = $state("");
	let message = $state("");

	async function refresh() {
		try {
			draft = await fetchReview();
			onPendingChange(draft !== null);
		} catch {
			// Keep the last visible prompt on connection failure.
		}
	}

	onMount(() => {
		void refresh();
		const timer = setInterval(() => { void refresh(); }, 1000);
		return () => clearInterval(timer);
	});

	async function resolve(action: "send" | "discard") {
		if (!draft || busy || !ready) return;
		busy = true;
		error = "";
		message = "";
		try {
			const status = await resolveReview(draft.id, action);
			if (status === "scheduled") message = "Queued for the connected assistant. Start listening again when you're ready.";
			else if (status === "discarded") message = "Prompt discarded. Start listening again when you're ready.";
			else if (status === "partial") error = "Only part of the prompt was sent. Review what remains before trying again.";
			else if (status === "failed") error = "Could not send to the original destination. Your prompt is still here; you can copy or discard it.";
			else error = "That prompt could not be changed. Check its status and try again.";
			await refresh();
		} catch (cause) {
			error = (cause as Error).message;
		} finally {
			busy = false;
		}
	}
</script>

{#if draft}
	<div class="rounded-lg border p-5 space-y-3" aria-label="Prompt waiting for review">
		<h3 class="font-medium">Review your words</h3>
		<p class="text-sm">Destination: <strong>{draft.destination}</strong></p>
		<div class="whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-sm">{draft.messages.join("\n")}</div>
		{#if !draft.can_send}
			<p class="text-sm">This destination cannot be safely used for review. Copy your words if needed, then discard them.</p>
		{/if}
		<p class="text-sm text-muted-foreground">Listening stays off until you start it again. If Dictare closes, unsent words are lost.</p>
		<div class="flex flex-wrap gap-2">
			<Button onclick={() => resolve("send")} disabled={!ready || !draft.can_send || draft.sending || busy}>Send</Button>
			<Button variant="outline" onclick={() => resolve("discard")} disabled={!ready || draft.sending || busy}>Discard</Button>
		</div>
		{#if !ready}<p class="text-sm">Waiting for listening to stop…</p>{/if}
	</div>
{/if}
{#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
{#if message}<p role="status" class="text-sm">{message}</p>{/if}
