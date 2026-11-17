import assert from "node:assert/strict";
import { test } from "node:test";
import { saveSettings } from "../src/lib/api.ts";

test("form settings use one request including default resets", async (t) => {
	let calls = 0;
	t.mock.method(globalThis, "fetch", async (url, init) => {
		calls++;
		assert.equal(url, "/api/settings");
		assert.deepEqual(JSON.parse(init.body), { values: { editor: "", "stt.language": "en" } });
		return Response.json({ status: "ok" });
	});
	await saveSettings({ editor: "", "stt.language": "en" });
	assert.equal(calls, 1);
});

test("batch errors retain the backend validation message", async (t) => {
	t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "conflicting commands" }, { status: 400 }));
	await assert.rejects(() => saveSettings({ editor: "new" }), /conflicting commands/);
});

test("profile names and argument lists are sent as structured data", async (t) => {
	t.mock.method(globalThis, "fetch", async (_url, init) => {
		assert.deepEqual(JSON.parse(init.body), { values: {}, profiles: { "my.profile": { command: ["agent", "--resume"] } } });
		return Response.json({ status: "ok" });
	});
	await saveSettings({}, { "my.profile": { command: ["agent", "--resume"] } });
});
