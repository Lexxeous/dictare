<script lang="ts">
	import * as settingsStore from "$lib/stores/settings.svelte";
	import SelectField from "./SelectField.svelte";
	import BoolField from "./BoolField.svelte";
	import TomlField from "./TomlField.svelte";

	const profiles = $derived((settingsStore.getValue("agent_profiles") ?? {}) as Record<string, unknown>);
	const options = $derived(Object.entries(profiles)
		.filter(([, value]) => value !== null && typeof value === "object" && !Array.isArray(value))
		.map(([name]) => ({ value: name, label: name })));
	const selected = $derived((settingsStore.getValue("agent_profiles.default") as string | null) ?? "");
	const dangerous = $derived(Boolean(settingsStore.getValue("agent_profiles.live_dangerously")));
</script>

<div class="mb-6">
	<div class="flex items-start justify-between gap-6 rounded-lg px-4 py-3">
		<div>
			<span class="text-sm font-medium">Default assistant profile</span>
			<p class="text-xs text-muted-foreground">Used when starting an assistant without choosing a profile.</p>
		</div>
		<SelectField {options} value={selected} defaultDisplay="" defaultLabelOverride="No default" allowCustom onchange={(value) => settingsStore.markDirty("agent_profiles.default", value)} />
	</div>
	<div class="flex items-start justify-between gap-6 rounded-lg px-4 py-3">
		<div>
			<span class="text-sm font-medium">Use relaxed permissions by default</span>
			<p class="text-xs text-muted-foreground">Applies each profile's configured permission-bypass arguments when available.</p>
		</div>
		<BoolField checked={dangerous} onchange={(value) => settingsStore.markDirty("agent_profiles.live_dangerously", value)} />
	</div>
	<div class="px-4 mt-2">
		<TomlField section="agent_profiles" label="Advanced: edit assistant profiles" />
	</div>
</div>
