import assert from "node:assert/strict";
import { test } from "node:test";
import { conflictingSections } from "../src/lib/settings-conflicts.ts";

test("detects form edits inside raw sections before saving", () => {
  assert.deepEqual(conflictingSections(
    { "audio.advanced.channels": 2, "stt.advanced.beam_size": 5 },
    { "audio.advanced": "[audio.advanced]", "stt.advanced": "[stt.advanced]" },
  ), ["audio.advanced", "stt.advanced"]);
});

test("does not confuse siblings or similarly named sections", () => {
  assert.deepEqual(conflictingSections(
    { "audio.advanced_extra.channels": 2, "audio.input_device": "mic" },
    { "audio.advanced": "text" },
  ), []);
});

test("detects replacement of a whole section or its parent", () => {
  assert.deepEqual(conflictingSections({ audio: {} }, { "audio.advanced": "text" }), ["audio.advanced"]);
  assert.deepEqual(conflictingSections({ "audio.advanced": {} }, { "audio.advanced": "text" }), ["audio.advanced"]);
});

test("profile edits conflict with the raw assistant profiles section", () => {
  assert.deepEqual(conflictingSections({}, { agent_profiles: "text" }, { "my.profile": { description: "x" } }), ["agent_profiles"]);
  assert.deepEqual(conflictingSections({}, { "audio.advanced": "text" }, { codex: {} }), []);
});
