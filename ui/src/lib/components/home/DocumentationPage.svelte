<script lang="ts">
	import readme from "../../../../../README.md?raw";
	import { copyDocumentationCode, renderDocumentation } from "$lib/documentation";
	import { base } from "$app/paths";
	import { onMount } from "svelte";
	const html = renderDocumentation(readme);
	let article: HTMLElement;
	onMount(() => {
		function copyFallback(text: string): boolean {
			const input = document.createElement("textarea");
			input.value = text;
			input.style.position = "fixed";
			input.style.opacity = "0";
			const previous = document.activeElement as HTMLElement | null;
			document.body.appendChild(input);
			try {
				input.select();
				return document.execCommand("copy");
			} finally {
				input.remove();
				previous?.focus();
			}
		}
		async function onCopy(event: MouseEvent) {
			const target = event.target;
			if (!(target instanceof Element)) return;
			const button = target.closest<HTMLButtonElement>("button[data-copy-code]");
			if (!button || !article.contains(button)) return;
			const code = button.parentElement?.querySelector("pre code");
			if (!code) return;
			const copied = await copyDocumentationCode(code.textContent ?? "", navigator.clipboard, copyFallback);
			const status = copied ? "Copied" : "Copy failed";
			button.dataset.copyState = copied ? "copied" : "error";
			button.setAttribute("aria-label", status);
			button.title = status;
			const announcement = button.querySelector("[data-copy-status]");
			if (announcement) announcement.textContent = status;
		}
		article.addEventListener("click", onCopy);
		return () => article.removeEventListener("click", onCopy);
	});
</script>

<section class="px-4 pb-8 min-w-0">
	<p class="text-sm text-muted-foreground mb-6">The full README bundled with this copy of Dictare. Reading works offline; external links open in a new tab.</p>
	<article bind:this={article} class="documentation">{@html html}</article>
	<p class="text-sm mt-6"><a class="underline" href={`${base}/third-party-notices.txt`} target="_blank" rel="noopener noreferrer">Third-party notices</a></p>
</section>

<style>
	.documentation { overflow-wrap: anywhere; line-height: 1.7; }
	.documentation :global(h1) { font-size: 1.5rem; margin: 1.5rem 0 1rem; }
	.documentation :global(h2) { font-size: 1.25rem; margin: 1.5rem 0 .75rem; }
	.documentation :global(h3) { font-size: 1.125rem; margin: 1.25rem 0 .5rem; }
	.documentation :global(p), .documentation :global(ul), .documentation :global(ol) { margin: .75rem 0; }
	.documentation :global(ul) { list-style: disc; padding-left: 1.5rem; }
	.documentation :global(ol) { list-style: decimal; padding-left: 1.5rem; }
	.documentation :global(a) { color: hsl(var(--primary)); text-decoration: underline; }
	.documentation :global(pre) { overflow-x: auto; max-width: 100%; padding: 1rem; border-radius: .5rem; background: hsl(var(--muted)); }
	.documentation :global(.documentation-code) { position: relative; max-width: 100%; }
	.documentation :global(.documentation-code pre) { padding-right: 3rem; }
	.documentation :global(.documentation-code button) { position: absolute; right: .5rem; top: .5rem; border: 1px solid hsl(var(--border)); border-radius: .375rem; padding: .375rem; background: hsl(var(--background)); color: hsl(var(--foreground)); }
	.documentation :global(.documentation-code .check-icon) { display: none; }
	.documentation :global(.documentation-code button[data-copy-state="copied"] .copy-icon) { display: none; }
	.documentation :global(.documentation-code button[data-copy-state="copied"] .check-icon) { display: block; }
	.documentation :global(.documentation-code button[data-copy-state="error"]) { color: hsl(var(--destructive)); }
	.documentation :global(.documentation-code button:focus-visible) { outline: 2px solid hsl(var(--ring)); outline-offset: 2px; }
	.documentation :global(code) { font-size: .85em; }
	.documentation :global(table) { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; margin: 1rem 0; }
	.documentation :global(th), .documentation :global(td) { padding: .5rem .75rem; border: 1px solid hsl(var(--border)); text-align: left; }
	.documentation :global(blockquote) { border-left: 3px solid hsl(var(--border)); padding-left: 1rem; }
	.documentation :global(hr) { margin: 1.5rem 0; }
</style>
