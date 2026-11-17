<script lang="ts">
	import { Switch } from "$lib/components/ui/switch";
	import { Button } from "$lib/components/ui/button";
	import * as settingsStore from "$lib/stores/settings.svelte";

	const defaults = { mute: "ok mute\nok hold on", listen: "ok listen\nok listen up", send: "ok send\nok submit" };
	const actions = [
		{ key: "mute", label: "Mute", example: "Dictare mute" },
		{ key: "listen", label: "Resume", example: "Dictare listen" },
		{ key: "send", label: "Send", example: "Dictare send" }
	] as const;
	const enabled = $derived(settingsStore.getValue("voice_commands.enabled") === true);
	const errors = $derived(settingsStore.getSaveErrors());
	function fieldValue(action: "mute" | "listen" | "send"): string {
		const key = `voice_commands.${action}`;
		if (key in settingsStore.getDirty()) return String(settingsStore.getValue(key) ?? "");
		return settingsStore.getSchema()?.voice_commands?.[action] || String(settingsStore.getValue(key) || defaults[action]);
	}

	function restore() {
		for (const action of actions) settingsStore.markDirty(`voice_commands.${action.key}`, defaults[action.key]);
	}
</script>

<section class="px-4 space-y-6 pb-6">
	{#if errors.settings}<p role="alert" class="text-sm text-destructive">{errors.settings}</p>{/if}
	<div class="rounded-lg border p-4 space-y-3">
		<div class="flex items-center justify-between gap-4">
			<label for="personal-commands" class="font-medium">Use my voice commands</label>
			<Switch id="personal-commands" checked={enabled} onCheckedChange={(value) => settingsStore.markDirty("voice_commands.enabled", value)} />
		</div>
		<p class="text-sm text-muted-foreground">Use these phrases for muting, resuming, and sending. Your previous commands are kept and return when you turn this off.</p>
		{#if settingsStore.getValue("pipeline.enabled") === false}
			<p class="text-sm">Voice controls are turned off. Enable them to use these commands.</p>
			<Button variant="outline" onclick={() => settingsStore.markDirty("pipeline.enabled", true)}>Enable voice controls</Button>
		{/if}
	</div>
	<p class="text-sm">Write the complete words you want to say, including your chosen name or cue. Enter one phrase per line. You can use several phrases for each action.</p>
	<p class="text-sm text-muted-foreground">Other speech is still dictated while listening.</p>
	<p class="text-sm text-muted-foreground">Use 1–10 words per phrase, with Latin letters or numbers. Capital letters, punctuation, and accents do not change a command. Choose distinct phrases for different actions.</p>
	{#each actions as action}
		{@const key = `voice_commands.${action.key}`}
		<div class="space-y-2">
			<label for={`command-${action.key}`} class="block font-medium">{action.label}</label>
			<textarea
				id={`command-${action.key}`}
				rows="3"
				maxlength="2000"
				class="w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
				value={fieldValue(action.key)}
				placeholder={action.example}
				aria-describedby={`command-${action.key}-hint`}
				oninput={(event) => settingsStore.markDirty(key, event.currentTarget.value)}
			></textarea>
			<p id={`command-${action.key}-hint`} class="text-sm text-muted-foreground">For example, “{action.example}”. Leave empty to restore the default phrases when saved.</p>
			{#if errors[key]}<p role="alert" class="text-sm text-destructive">{errors[key]}</p>{/if}
		</div>
	{/each}
	<p class="text-sm text-muted-foreground">Voice commands need listening to be running. To restart fully stopped listening, use Home or your shortcut key. Save your changes below to apply them.</p>
	<Button variant="outline" onclick={restore}>Restore default phrases</Button>
</section>
