import assert from "node:assert/strict";
import { test } from "node:test";
import { fetchReview, resolveReview } from "../src/lib/review.ts";

test("review controls load without caching and resolve the selected draft", async (t) => {
	const calls = [];
	t.mock.method(globalThis, "fetch", async (url, options) => {
		calls.push([url, options]);
		return Response.json(url === "/api/review" ? { draft: { id: "abc", messages: ["hello"] } } : { status: "scheduled" });
	});
	assert.equal((await fetchReview()).messages[0], "hello");
	assert.equal(calls[0][1].cache, "no-store");
	assert.equal(await resolveReview("a/b", "send"), "scheduled");
	assert.equal(calls[1][0], "/api/review/a%2Fb/send");
	assert.equal(calls[1][1].method, "POST");
});

test("review transport does not claim failed HTTP actions succeeded", async (t) => {
	t.mock.method(globalThis, "fetch", async () => new Response("", { status: 503 }));
	await assert.rejects(fetchReview, /Could not check/);
	await assert.rejects(() => resolveReview("abc", "discard"), /Could not reach/);
});
