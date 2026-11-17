import assert from "node:assert/strict";
import { test } from "node:test";
import { setListening, listeningLabel, hotkeyLabel } from "../src/lib/listening.ts";
import { renderDocumentation } from "../src/lib/documentation.ts";

test("listening controls use explicit speech commands, never shutdown", async (t) => {
	const calls = [];
	t.mock.method(globalThis, "fetch", async (url, options) => {
		assert.equal(url, "/openvip/control");
		calls.push(JSON.parse(options.body).command);
		return Response.json({ status: "ok" });
	});
	await setListening(true);
	await setListening(false);
	assert.deepEqual(calls, ["stt.start", "stt.stop"]);
});

test("failed listening request is not shown as accepted", async (t) => {
	const fetch = t.mock.method(globalThis, "fetch", async () => new Response("", { status: 503 }));
	await assert.rejects(() => setListening(true), /503/);
	fetch.mock.mockImplementation(async () => Response.json({ status: "error" }));
	await assert.rejects(() => setListening(false), /did not accept/);
});

test("Home labels distinguish mute, off and active work", () => {
	assert.match(listeningLabel("muted"), /muted/);
	assert.match(listeningLabel("off"), /off/);
	assert.match(listeningLabel("transcribing"), /text/);
	assert.equal(hotkeyLabel("KEY_RIGHTMETA"), "Right Command (⌘)");
});

test("README Markdown includes headings, tables, lists and escaped code", () => {
	const html = renderDocumentation("# Guide\n\n- Speak\n\n| Key | Action |\n|---|---|\n| Tap | Listen |\n\n```html\n<script>example</script>\n```\n");
	assert.match(html, /id="docs-guide"/);
	assert.match(html, /<table>/);
	assert.match(html, /<li>Speak<\/li>/);
	assert.match(html, /&lt;script&gt;example/);
});

test("raw HTML, unsafe URLs and remote image loads are excluded", () => {
	const html = renderDocumentation('<script>alert(1)</script>\n\nHello <img src="x" onerror="alert(2)">\n\n[unsafe](javascript:alert(3))\n\n![badge](https://example.org/track.png)');
	assert.doesNotMatch(html, /<script|<img|href="javascript:/);
	assert.match(html, /badge/);
});

test("relative README links and heading anchors resolve deliberately", () => {
	const html = renderDocumentation("# Guide\n\n# Guide\n\n[Guide](#guide) [License](LICENSE)");
	assert.match(html, /id="docs-guide-1"/);
	assert.match(html, /href="#docs-guide"/);
	assert.match(html, /https:\/\/github.com\/dragfly\/dictare\/blob\/main\/LICENSE/);
	assert.match(html, /rel="noopener noreferrer"/);
});
