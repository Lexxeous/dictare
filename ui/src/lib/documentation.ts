import MarkdownIt from "markdown-it";

const repository = "https://github.com/dragfly/dictare/blob/main/";

/** Only bundled documentation uses this renderer; arbitrary HTML is never emitted. */
export function renderDocumentation(source: string): string {
	const markdown = new MarkdownIt({ html: true, linkify: false });
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
