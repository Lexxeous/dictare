<script lang="ts">
	import * as settingsStore from "$lib/stores/settings.svelte";
	import SelectField from "./SelectField.svelte";
	import BoolField from "./BoolField.svelte";
	import TomlField from "./TomlField.svelte";
	import { Button } from "$lib/components/ui/button";

	const profiles = $derived((settingsStore.getValue("agent_profiles") ?? {}) as Record<string, unknown>);
	const options = $derived([
		...Object.entries(profiles)
			.filter(([, value]) => value !== null && typeof value === "object" && !Array.isArray(value))
			.map(([name]) => ({ value: name, label: name })),
		...settingsStore.getCreatedProfiles().map((name) => ({ value: name, label: name })),
	]);
	let newName = $state("");
	let nameError = $state("");
	function addProfile(): void {
		const name = newName.trim();
		if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(name) || ["default", "live_dangerously", "constructor", "prototype"].includes(name)) {
			nameError = "Use letters, numbers, dots, hyphens or underscores for a new profile name.";
			return;
		}
		if (options.some((option) => option.value === name)) {
			nameError = "A profile with this name already exists.";
			return;
		}
		settingsStore.createProfile(name);
		newName = "";
		nameError = "";
	}
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
					{#if settingsStore.getCreatedProfiles().includes(option.value)}
						<p class="text-xs text-muted-foreground">Enter an executable as the first line of the command before saving.</p>
						<Button variant="ghost" size="sm" onclick={() => settingsStore.discardNewProfile(option.value)}>Remove new profile</Button>
					{/if}
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
		<div class="flex flex-wrap gap-2 mb-3">
			<input class="w-48 rounded-md border bg-background px-3 py-2 text-sm" aria-label="New profile name" placeholder="New profile name" bind:value={newName} />
			<Button variant="outline" size="sm" onclick={addProfile}>Add profile</Button>
		</div>
		{#if nameError}<p role="alert" class="text-xs text-destructive mb-2">{nameError}</p>{/if}
		<TomlField section="agent_profiles" label="Advanced: edit assistant profiles" />
	</div>
</div>
