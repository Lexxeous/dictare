import MarkdownIt from "markdown-it";

const repository = "https://github.com/dragfly/dictare/blob/main/";

/** Only bundled documentation uses this renderer; arbitrary HTML is never emitted. */
export function renderDocumentation(source: string): string {
	const markdown = new MarkdownIt({ html: true, linkify: false });
	for (const type of ["fence", "code_block"] as const) {
		const renderCode = markdown.renderer.rules[type]!;
		markdown.renderer.rules[type] = (tokens, index, options, env, renderer) =>
			`<div class="documentation-code"><button type="button" data-copy-code aria-label="Copy code" title="Copy code"><svg class="copy-icon" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><svg class="check-icon" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg><span class="sr-only" data-copy-status aria-live="polite"></span></button>${renderCode(tokens, index, options, env, renderer)}</div>`;
	}
	markdown.renderer.rules.html_block = () => "";
	markdown.renderer.rules.html_inline = () => "";
	// Keep reading offline and avoid contacting badge/video/image hosts on page load.
	markdown.renderer.rules.image = (tokens, index) =>
		`<span>${markdown.utils.escapeHtml(tokens[index].content)}</span>`;
	const headings = new Map<string, number>();
	markdown.core.ruler.push("documentation-headings", (state) => {
		for (let index = 0; index < state.tokens.length; index++) {
			const token = state.tokens[index];
			if (token.type !== "heading_open") continue;
			const text = state.tokens[index + 1].children?.map((child) => child.content).join("") ?? "";
			const slug = text.toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, "").trim().replace(/\s+/g, "-") || "section";
			const count = headings.get(slug) ?? 0;
			headings.set(slug, count + 1);
			token.attrSet("id", `docs-${slug}${count ? `-${count}` : ""}`);
		}
	});
	const originalLink = markdown.renderer.rules.link_open;
	markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
		const token = tokens[index];
		const href = String(token.attrGet("href") ?? "");
		if (href.startsWith("#")) {
			token.attrSet("href", `#docs-${href.slice(1)}`);
		} else {
			try {
				const url = new URL(href, repository);
				if (!["https:", "http:", "mailto:"].includes(url.protocol)) {
					token.attrSet("href", "");
				} else {
					token.attrSet("href", url.href);
					token.attrSet("target", "_blank");
					token.attrSet("rel", "noopener noreferrer");
				}
			} catch { token.attrSet("href", ""); }
		}
		return originalLink ? originalLink(tokens, index, options, env, renderer) : renderer.renderToken(tokens, index, options);
	};
	return markdown.render(source);
}

/** Report clipboard failures without claiming a copy succeeded. */
export async function copyDocumentationCode(text: string, clipboard: Pick<Clipboard, "writeText"> | undefined, fallback?: (text: string) => boolean): Promise<boolean> {
	try {
		if (clipboard) {
			await clipboard.writeText(text);
			return true;
		}
	} catch { /* Try the browser's copy command below. */ }
	try { return fallback?.(text) ?? false; } catch { return false; }
}
