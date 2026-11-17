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
	const listFields = [
		["command", "Command and arguments"], ["continue_args", "Resume arguments"],
		["live_dangerously_args", "Permission-bypass arguments"],
	];
	function profileValue(name: string, field: string): unknown {
		const dirty = settingsStore.getDirtyProfiles()[name];
		if (dirty && field in dirty) return dirty[field];
		return (profiles[name] as Record<string, unknown> | undefined)?.[field];
	}
	function listValue(name: string, field: string): string {
		const value = profileValue(name, field);
		return Array.isArray(value) ? value.join("\n") : "";
	}
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
		<h3 class="text-sm font-medium mb-2">Assistant profiles</h3>
		{#each options as option (option.value)}
			<details class="border rounded-md mb-2">
				<summary class="cursor-pointer px-4 py-3 text-sm font-medium">{option.label}</summary>
				<div class="px-4 pb-4 space-y-3">
					<label class="block text-sm">Description
						<input class="mt-1 w-full rounded-md border bg-background px-3 py-2" type="text"
							value={(profileValue(option.value, "description") as string) ?? ""}
							oninput={(event) => settingsStore.markProfileDirty(option.value, "description", event.currentTarget.value)} />
					</label>
					{#each listFields as [field, label] (field)}
						<label class="block text-sm">{label}
							<textarea class="mt-1 w-full min-h-20 rounded-md border bg-background px-3 py-2"
								value={listValue(option.value, field)}
								oninput={(event) => settingsStore.markProfileDirty(option.value, field, event.currentTarget.value === "" ? [] : event.currentTarget.value.split("\n"))}></textarea>
						</label>
					{/each}
					<p class="text-xs text-muted-foreground">Enter one command or argument per line. Arguments are passed directly, without a shell.</p>
					<div class="flex items-center justify-between gap-4">
						<span class="text-sm">Permission mode</span>
						<SelectField options={[{ value: "true", label: "Use relaxed permissions" }, { value: "false", label: "Use normal permissions" }]}
							value={profileValue(option.value, "live_dangerously") == null ? "" : String(profileValue(option.value, "live_dangerously"))}
							defaultDisplay="" defaultLabelOverride="Use global setting"
							onchange={(value) => settingsStore.markProfileDirty(option.value, "live_dangerously", value === "" ? null : value === "true")} />
					</div>
				</div>
			</details>
		{/each}
		<TomlField section="agent_profiles" label="Advanced: edit assistant profiles" />
	</div>
</div>
