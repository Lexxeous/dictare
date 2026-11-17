import assert from "node:assert/strict";
import { test } from "node:test";
import { confirmEngineShutdown } from "../src/lib/engine-shutdown.ts";
import { stopEngine } from "../src/lib/api.ts";

test("declining confirmation sends no stop command", async () => {
	let calls = 0;
	const result = await confirmEngineShutdown(() => false, async () => { calls++; });
	assert.equal(result, false);
	assert.equal(calls, 0);
});

test("confirmation explains whole-engine shutdown and unsaved settings", async () => {
	let calls = 0;
	const result = await confirmEngineShutdown((message) => {
		assert.match(message, /not just listening/);
		assert.match(message, /unsaved settings/);
		assert.match(message, /disconnect/);
		return true;
	}, async () => { calls++; }, true);
	assert.equal(result, true);
	assert.equal(calls, 1);
});

test("accepted stop sends engine.shutdown rather than stt.stop", async (t) => {
	t.mock.method(globalThis, "fetch", async (url, init) => {
		assert.equal(url, "/openvip/control");
		assert.equal(init?.method, "POST");
		assert.deepEqual(JSON.parse(String(init?.body)), { command: "engine.shutdown" });
		return Response.json({ status: "ok" });
	});
	await stopEngine();
});

test("HTTP and protocol failures are not reported as accepted shutdown", async (t) => {
	const fetch = t.mock.method(globalThis, "fetch", async () => new Response("failed", { status: 503 }));
	await assert.rejects(stopEngine, /503/);
	fetch.mock.mockImplementation(async () => Response.json({ status: "error" }));
	await assert.rejects(stopEngine, /did not accept/);
});

test("lost connection remains unconfirmed instead of claiming success", async (t) => {
	t.mock.method(globalThis, "fetch", async () => { throw new TypeError("connection lost"); });
	await assert.rejects(stopEngine, /connection lost/);
});

test("restart reports a refused review guard instead of claiming success", async (t) => {
	const { restartEngine } = await import("../src/lib/api.ts");
	t.mock.method(globalThis, "fetch", async () => Response.json({ status: "error", error: "Send or discard the pending prompt before continuing." }));
	await assert.rejects(restartEngine, /Send or discard/);
});
