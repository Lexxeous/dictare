<script lang="ts">
	import { untrack } from "svelte";
	import type { TabDef } from "$lib/types";
	import { Separator } from "$lib/components/ui/separator";
	import { ChevronRight, Sun, Moon, Monitor, Menu, X } from "lucide-svelte";
	import { getTheme, setTheme, type Theme } from "$lib/stores/theme.svelte";
	import { getFixedBottomPx } from "$lib/stores/settings.svelte";

	interface Props {
		tabs: TabDef[];
		activeNavId: string;
		version: string;
	}

	let { tabs, activeNavId = $bindable(), version }: Props = $props();

	/** Set of expanded parent IDs (expandable tabs whose children are visible). */
	let expanded = $state<Set<string>>(new Set());
	let mobileOpen = $state(false);
	let navigation: HTMLElement;
	let menuButton: HTMLButtonElement;

	function closeMenu(restoreFocus = false) {
		if (!mobileOpen) return;
		mobileOpen = false;
		if (restoreFocus) menuButton?.focus();
	}

	function onOutsideClick(event: MouseEvent) {
		if (event.target instanceof Node && !navigation?.contains(event.target)) closeMenu();
	}

	/** When activeNavId changes, ensure the parent tab is expanded. */
	$effect(() => {
		for (const tab of tabs) {
			if (tab.children) {
				if (tab.children.some((c) => c.id === activeNavId) || tab.id === activeNavId) {
					// untrack: read expanded without creating a reactive dependency on it
					// (writing to expanded would otherwise re-trigger this effect → infinite loop)
					const current = untrack(() => expanded);
					if (!current.has(tab.id)) {
						expanded = new Set([...current, tab.id]);
					}
				}
			}
		}
	});

	function toggleExpand(tabId: string) {
		const next = new Set(expanded);
		if (next.has(tabId)) {
			next.delete(tabId);
		} else {
			next.add(tabId);
		}
		expanded = next;
	}

	function selectLeaf(id: string) {
		activeNavId = id;
		closeMenu(true);
	}

	function isActive(id: string): boolean {
		return activeNavId === id;
	}

	function parentIsActive(tab: TabDef): boolean {
		if (!tab.children) return false;
		return tab.children.some((c) => c.id === activeNavId);
	}
</script>

<svelte:document onclick={onOutsideClick} />
<svelte:window
	onkeydown={(event) => {
		if (mobileOpen && event.key === "Escape") {
			event.preventDefault();
			closeMenu(true);
		}
	}}
	onresize={() => {
		if (window.innerWidth >= 640) closeMenu();
	}}
/>

<nav bind:this={navigation} aria-label="Settings navigation" style="--settings-bottom: {getFixedBottomPx()}px" class="relative z-30 w-full sm:w-52 shrink-0 border-b sm:border-b-0 sm:border-r bg-background sm:bg-background/50 sm:h-screen sm:overflow-y-auto p-3 flex flex-col">
	<div class="flex items-center justify-between gap-2">
		<button aria-label="Dictare Home" onclick={() => selectLeaf("home")} class="min-w-0 flex-1 px-3 py-2 text-left rounded-md focus-visible:ring-2 focus-visible:ring-ring">
			<span class="flex items-center gap-2">
				<svg aria-hidden="true" class="shrink-0" width="24" height="24" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
					<rect x="0" y="0" width="100" height="100" rx="22" fill="#6d5ce6"/>
					<g transform="translate(0, 4)">
						<rect x="35" y="12" width="30" height="48" rx="15" fill="none" stroke="#FFFFFF" stroke-width="6"/>
						<path d="M 30 46 A 20 26 0 0 0 70 46" stroke="#FFFFFF" stroke-width="6" fill="none" stroke-linecap="round"/>
						<line x1="50" y1="72" x2="50" y2="82" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round"/>
						<line x1="38" y1="82" x2="62" y2="82" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round"/>
					</g>
				</svg>
				<span class="text-sm font-semibold tracking-tight">DICTA<span style="color: #6d5ce6">re</span></span>
			</span>
			{#if version}
				<span title={version} class="mt-1 block truncate text-[11px] text-muted-foreground">{version}</span>
			{/if}
		</button>
		<button bind:this={menuButton} class="sm:hidden shrink-0 flex size-10 items-center justify-center rounded-md border focus-visible:ring-2 focus-visible:ring-ring" aria-label={mobileOpen ? "Close settings menu" : "Open settings menu"} aria-expanded={mobileOpen} aria-controls="settings-pages" onclick={() => mobileOpen = !mobileOpen}>
			{#if mobileOpen}<X aria-hidden="true" class="size-4" />{:else}<Menu aria-hidden="true" class="size-4" />{/if}
		</button>
	</div>
	<div id="settings-pages" class="{mobileOpen ? 'flex' : 'hidden'} absolute inset-x-0 top-full max-h-[calc(100dvh-6rem-var(--settings-bottom))] overflow-y-auto border-b bg-background p-3 shadow-lg sm:static sm:max-h-none sm:overflow-visible sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none sm:flex flex-col sm:flex-1">
	<Separator class="hidden sm:block mb-3" />

	<div class="space-y-0.5">
		{#each tabs as tab (tab.id)}
			{@const Icon = tab.icon}
			{#if tab.children}
				<!-- Expandable parent -->
				<button
					class="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors
						{parentIsActive(tab)
							? 'text-accent-foreground font-medium'
							: 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'}"
					onclick={() => toggleExpand(tab.id)}
				>
					<Icon class="size-4 shrink-0" />
					<span class="flex-1 text-left">{tab.label}</span>
					<ChevronRight
						class="size-3.5 transition-transform duration-150 {expanded.has(tab.id) ? 'rotate-90' : ''}"
					/>
				</button>

				<!-- Children -->
				{#if expanded.has(tab.id)}
					<div class="ml-3 pl-3 border-l border-border/60 space-y-0.5 py-0.5">
						{#each tab.children as child (child.id)}
							<button
								class="flex w-full items-center rounded-md px-3 py-1.5 text-sm transition-colors
									{isActive(child.id)
										? 'bg-accent text-accent-foreground font-medium'
										: 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'}"
					onclick={() => selectLeaf(child.id)}
					aria-current={isActive(child.id) ? "page" : undefined}
							>
								{child.label}
							</button>
						{/each}
					</div>
				{/if}
			{:else}
				<!-- Simple leaf item -->
				<button
					class="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors
						{isActive(tab.id)
							? 'bg-accent text-accent-foreground font-medium'
							: 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'}"
					onclick={() => selectLeaf(tab.id)}
					aria-current={isActive(tab.id) ? "page" : undefined}
				>
					<Icon class="size-4 shrink-0" />
					{tab.label}
				</button>
			{/if}
		{/each}
	</div>
	<div class="mt-3 sm:mt-auto pt-3 border-t border-border/60">
		<div class="flex items-center justify-center gap-1 p-1 rounded-lg bg-muted/50">
			{#each [{ t: "light" as Theme, Icon: Sun }, { t: "system" as Theme, Icon: Monitor }, { t: "dark" as Theme, Icon: Moon }] as { t, Icon }}
				<button
					onclick={() => setTheme(t)}
					class="flex-1 flex items-center justify-center py-1.5 rounded-md transition-colors
						{getTheme() === t
							? 'bg-background text-foreground shadow-sm ring-1 ring-border'
							: 'text-muted-foreground hover:text-foreground'}"
					title={t.charAt(0).toUpperCase() + t.slice(1)}
				>
					<Icon class="size-3.5" />
				</button>
			{/each}
		</div>
	</div>
	</div>
</nav>
