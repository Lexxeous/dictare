<script lang="ts">
	import type { FieldMeta, JsonSchema } from "$lib/types";
	import { resolveFieldSchema } from "$lib/schema";
	import FieldRenderer from "../FieldRenderer.svelte";
	import TomlField from "./TomlField.svelte";
	import * as settingsStore from "$lib/stores/settings.svelte";

	type Group = "audio.advanced" | "stt.advanced" | "pipeline.mute_filter" | "pipeline.submit_filter" | "pipeline.agent_filter";
	interface Props { section: Group; schema: JsonSchema }
	let { section, schema }: Props = $props();

	const groups: Record<Props["section"], Array<[string, string, string]>> = {
		"pipeline.mute_filter": [
			["enabled", "bool", "Recognize spoken mute and resume commands."],
			["confidence_threshold", "float", "Minimum confidence for matching a command."],
			["max_scan_words", "int", "Maximum recent words checked for a command."],
			["decay_rate", "float", "How quickly confidence decreases for earlier words."],
		],
		"pipeline.submit_filter": [
			["enabled", "bool", "Recognize spoken send commands."],
			["confidence_threshold", "float", "Minimum confidence for matching a command."],
			["max_scan_words", "int", "Maximum recent words checked for a command."],
			["decay_rate", "float", "How quickly confidence decreases for earlier words."],
		],
		"pipeline.agent_filter": [
			["enabled", "bool", "Allow switching assistants by voice."],
			["match_threshold", "float", "Minimum similarity for matching an assistant name."],
		],
		"audio.advanced": [
			["sample_rate", "int", "Audio sample rate in hertz."],
			["channels", "int", "Number of input audio channels."],
			["device", "str", "Legacy input device setting. Prefer Input Device above."],
			["pre_buffer_ms", "int", "Milliseconds of audio kept before speech starts."],
			["min_speech_ms", "int", "Minimum speech duration in milliseconds."],
			["transcribing_sound_min_ms", "int", "Minimum recording length before the transcription sound plays, in milliseconds."],
		],
		"stt.advanced": [
			["device", "str", "Processor used for speech recognition."],
			["compute_type", "str", "Recognition precision; available options depend on the processor."],
			["beam_size", "int", "Recognition search width; higher values can take longer."],
			["hotwords", "str", "Comma-separated words to help recognition."],
			["max_repetitions", "int", "Maximum repeated words before filtering."],
		],
	};
	const titles: Record<Group, string> = {
		"audio.advanced": "Audio tuning", "stt.advanced": "Recognition tuning",
		"pipeline.mute_filter": "Mute and resume", "pipeline.submit_filter": "Send commands",
		"pipeline.agent_filter": "Switch assistants",
	};
	const fields = $derived(groups[section].map(([name, type, description]): FieldMeta => {
		const key = `${section}.${name}`;
		return { key, type, description, default: resolveFieldSchema(key, schema)?.default, env_var: "" };
	}));
</script>

<div class="mb-6">
	<h3 class="px-4 py-2 text-sm font-medium">{titles[section]}</h3>
	{#each fields as field (field.key)}
		<FieldRenderer {field} {schema} nestedForm />
	{/each}
	{#if section === "pipeline.agent_filter" || section === "pipeline.mute_filter"}
		{@const listKey = section === "pipeline.agent_filter" ? "pipeline.agent_filter.triggers" : "pipeline.mute_filter.listen_phrases"}
		<div class="px-4 py-3">
			<label for={listKey} class="text-sm font-medium">
				{section === "pipeline.agent_filter" ? "Assistant switch words" : "Spoken resume responses"}
			</label>
			<p class="text-xs text-muted-foreground mb-2">One phrase per line. Blank lines are ignored; leave empty to use no phrases.</p>
			<textarea
				id={listKey}
				class="w-full min-h-24 rounded-md border bg-background px-3 py-2 text-sm"
				value={((settingsStore.getValue(listKey) as string[] | null) ?? []).join("\n")}
				oninput={(event) => {
					const text = event.currentTarget.value;
					settingsStore.markDirty(listKey, text === "" ? [] : text.split("\n"));
				}}
			></textarea>
		</div>
	{/if}
	<div class="px-4 mt-2">
		<TomlField {section} label="Advanced: edit configuration text" />
	</div>
</div>
