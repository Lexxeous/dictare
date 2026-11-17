<script lang="ts">
	import { Button } from "$lib/components/ui/button";
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { getEngineBarVisible } from "$lib/stores/settings.svelte";

	const hasDirty = $derived(settingsStore.hasDirtyFields());
	const status = $derived(settingsStore.getSaveStatus());
	const engineBarVisible = $derived(getEngineBarVisible());
	const visible = $derived(hasDirty || status === "error");
</script>

{#if visible}
	<div
		class="fixed left-0 right-0 border-t bg-background/95 backdrop-blur px-6 py-3 z-50 transition-[bottom] duration-200"
		style="bottom: {engineBarVisible ? 44 : 0}px"
	>
		<div class="max-w-[50rem] mx-auto flex items-center justify-end gap-3">
			{#if status === "error"}
				<span role="alert" class="text-sm text-destructive mr-auto">{settingsStore.getSaveErrors().settings || "Some fields had errors"}</span>
			{/if}
			{#if hasDirty}
				<Button
					variant="ghost"
					size="sm"
					onclick={() => settingsStore.resetDirty()}
				>
					Cancel
				</Button>
			{/if}
			<Button
				disabled={status === "saving"}
				onclick={() => hasDirty ? settingsStore.saveAll() : settingsStore.retrySavedRestart()}
				size="sm"
			>
				{status === "saving" ? "Saving..." : hasDirty ? "Save Changes" : "Retry Restart"}
			</Button>
		</div>
	</div>
{/if}
