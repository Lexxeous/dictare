<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import { Power } from "lucide-svelte";
	import { stopEngine } from "$lib/api";
	import { confirmEngineShutdown } from "$lib/engine-shutdown";
	import * as settingsStore from "$lib/stores/settings.svelte";

	let pending = $state(false);
	let error = $state("");
	const requested = $derived(settingsStore.getEngineShutdownRequested());

	async function stop() {
		if (pending || requested) return;
		pending = true;
		error = "";
		try {
			const accepted = await confirmEngineShutdown(
				(message) => window.confirm(message), stopEngine, settingsStore.hasDirtyFields()
			);
			if (accepted) settingsStore.setEngineShutdownRequested(true);
		} catch {
			error = "Could not confirm that Dictare stopped. Check the tray before trying again.";
		} finally {
			pending = false;
		}
	}
</script>

<div class="px-4 mb-6 space-y-2">
	<div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3">
		<div class="min-w-0 break-words">
			<p class="text-sm font-medium">Stop Dictare</p>
			<p class="text-xs text-muted-foreground">Stop the whole engine. Launch-at-login settings stay unchanged.</p>
		</div>
		<Button class="w-full sm:w-auto max-w-full whitespace-normal h-auto min-h-10 py-2" variant="destructive" onclick={stop} disabled={pending || requested}>
			<Power class="size-3.5 mr-1.5 shrink-0" />
			{pending ? "Requesting stop…" : requested ? "Stop requested" : "Stop Dictare"}
		</Button>
	</div>
	{#if error}
		<p role="alert" class="text-sm text-destructive">{error}</p>
	{/if}
</div>
