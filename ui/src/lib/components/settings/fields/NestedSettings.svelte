<script lang="ts">
	import type { FieldMeta, JsonSchema } from "$lib/types";
	import { resolveFieldSchema } from "$lib/schema";
	import FieldRenderer from "../FieldRenderer.svelte";
	import TomlField from "./TomlField.svelte";

	interface Props { section: "audio.advanced" | "stt.advanced"; schema: JsonSchema }
	let { section, schema }: Props = $props();

	const groups: Record<Props["section"], Array<[string, string, string]>> = {
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
	const fields = $derived(groups[section].map(([name, type, description]): FieldMeta => {
		const key = `${section}.${name}`;
		return { key, type, description, default: resolveFieldSchema(key, schema)?.default, env_var: "" };
	}));
</script>

<div class="mb-6">
	<h3 class="px-4 py-2 text-sm font-medium">{section === "audio.advanced" ? "Audio tuning" : "Recognition tuning"}</h3>
	{#each fields as field (field.key)}
		<FieldRenderer {field} {schema} nestedForm />
	{/each}
	<div class="px-4 mt-2">
		<TomlField {section} label="Advanced: edit configuration text" />
	</div>
</div>
