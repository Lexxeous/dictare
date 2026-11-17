<script lang="ts">
	import type { FieldMeta, JsonSchema } from "$lib/types";
	import FieldRenderer from "../FieldRenderer.svelte";
	import TomlField from "./TomlField.svelte";

	interface Props { schema: JsonSchema; defaults: unknown }
	let { schema, defaults }: Props = $props();
	const events = [
		["start", "Start listening"], ["stop", "Stop listening"],
		["transcribing", "Transcribing"], ["ready", "Ready to listen"],
		["transcribed", "Transcription received"], ["submit", "Submit"],
		["sent", "Sent to assistant"], ["agent_announce", "Announce assistant"],
	];
	const properties: Array<[string, string, string]> = [
		["enabled", "bool", "Play this feedback."],
		["path", "str", "Custom sound file path. Leave blank to use the built-in sound."],
		["volume", "float", "Volume from 0 (silent) to 1 (full)."],
		["focus_gated", "bool", "Skip when the assistant terminal is focused."],
	];
	function fields(event: string): FieldMeta[] {
		const eventDefaults = (defaults as Record<string, Record<string, unknown>> | null)?.[event] ?? {};
		return properties.filter(([name]) => event !== "agent_announce" || name !== "path")
			.map(([name, type, description]) => ({
				key: `audio.sounds.${event}.${name}`, type, description,
				default: eventDefaults[name], env_var: "",
			}));
	}
</script>

<div class="px-4 mb-6">
	<h3 class="py-2 text-sm font-medium">Sound feedback</h3>
	<p class="text-xs text-muted-foreground mb-3">Choose which feedback plays for each event.</p>
	{#each events as [event, label] (event)}
		<details class="border rounded-md mb-2">
			<summary class="cursor-pointer px-4 py-3 text-sm font-medium">{label}</summary>
			{#each fields(event) as field (field.key)}
				<FieldRenderer {field} {schema} nestedForm />
			{/each}
		</details>
	{/each}
	<TomlField section="audio.sounds" label="Advanced: edit configuration text" />
</div>
