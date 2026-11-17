<script lang="ts">
	import * as settingsStore from "$lib/stores/settings.svelte";
	import { Button } from "$lib/components/ui/button";

	interface Props { settingKey: string; label: string }
	let { settingKey, label }: Props = $props();
	type Patterns = Record<string, string[][]>;
	let language = $state("");
	let error = $state("");
	const patterns = $derived((settingsStore.getValue(settingKey) ?? {}) as Patterns);
	function copy(): Patterns { return JSON.parse(JSON.stringify(patterns)); }
	function update(fn: (draft: Patterns) => void): void {
		const draft = copy();
		fn(draft);
		settingsStore.markDirty(settingKey, draft);
	}
	function addLanguage(): void {
		const name = language.trim();
		if (!name || name in patterns) { error = "Enter a new language code, or * for all languages."; return; }
		update((draft) => { draft[name] = []; });
		language = "";
		error = "";
	}
</script>

<div class="px-4 py-3">
	<h4 class="text-sm font-medium">{label}</h4>
	<p class="text-xs text-muted-foreground mb-2">Each pattern matches its words in order. Use | between alternatives within a word.</p>
	{#if settingsStore.getValue("voice_commands.enabled")}
		<p class="text-xs text-muted-foreground mb-2">Personal commands are enabled in Commands, so these patterns are retained but inactive.</p>
	{/if}
	{#each Object.entries(patterns) as [code, rows] (code)}
		<div class="border rounded-md p-3 mb-2">
			<div class="flex justify-between items-center gap-2 mb-2">
				<strong class="text-sm">{code === "*" ? "All languages (*)" : code}</strong>
				<Button variant="ghost" size="sm" onclick={() => update((draft) => { delete draft[code]; })}>Remove language</Button>
			</div>
			{#each rows as row, rowIndex (rowIndex)}
				<div class="flex flex-wrap items-center gap-2 mb-2">
					{#each row as word, wordIndex (wordIndex)}
						<input class="w-28 rounded-md border bg-background px-2 py-1 text-sm" value={word}
							aria-label={`Word ${wordIndex + 1} of pattern ${rowIndex + 1} for ${code}`}
							oninput={(event) => update((draft) => { draft[code][rowIndex][wordIndex] = event.currentTarget.value; })} />
						<button type="button" class="text-sm text-muted-foreground" aria-label={`Remove word ${wordIndex + 1}`} onclick={() => update((draft) => { draft[code][rowIndex].splice(wordIndex, 1); })}>×</button>
					{/each}
					<Button variant="outline" size="sm" onclick={() => update((draft) => { draft[code][rowIndex].push(""); })}>Add word</Button>
					<Button variant="ghost" size="sm" onclick={() => update((draft) => { draft[code].splice(rowIndex, 1); })}>Remove pattern</Button>
				</div>
			{/each}
			<Button variant="outline" size="sm" onclick={() => update((draft) => { draft[code].push([""]); })}>Add pattern</Button>
		</div>
	{/each}
	<div class="flex flex-wrap gap-2">
		<input class="w-40 rounded-md border bg-background px-3 py-2 text-sm" aria-label={`Language for ${label}`} placeholder="Language code or *" bind:value={language} />
		<Button variant="outline" size="sm" onclick={addLanguage}>Add language</Button>
	</div>
	{#if error}<p role="alert" class="text-xs text-destructive mt-1">{error}</p>{/if}
</div>
