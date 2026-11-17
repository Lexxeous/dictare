/** Send an explicit listening request; never stop the whole engine. */
export async function setListening(on: boolean): Promise<void> {
	const response = await fetch("/openvip/control", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ command: on ? "stt.start" : "stt.stop" }),
		signal: AbortSignal.timeout(5000)
	});
	if (!response.ok) throw new Error(`Listening request failed: ${response.status}`);
	const result = await response.json();
	if (result.status !== "ok") throw new Error("Dictare did not accept the listening request");
}

export function listeningLabel(state: string): string {
	switch (state) {
		case "off": return "Listening is off";
		case "muted": return "Dictation is muted";
		case "listening": return "Ready to hear you";
		case "recording": return "Hearing your words";
		case "transcribing": return "Turning speech into text";
		case "playing": return "Speaking to you";
		default: return "Checking Dictare…";
	}
}

export function hotkeyLabel(key: string): string {
	const names: Record<string, string> = {
		KEY_RIGHTMETA: "Right Command (⌘)", KEY_LEFTMETA: "Left Command (⌘)",
		KEY_SCROLLLOCK: "Scroll Lock", KEY_RIGHTALT: "Right Alt",
		KEY_LEFTALT: "Left Alt", KEY_RIGHTCTRL: "Right Control",
		KEY_LEFTCTRL: "Left Control", KEY_RIGHTSHIFT: "Right Shift",
		KEY_LEFTSHIFT: "Left Shift"
	};
	return names[key] ?? key.replace(/^KEY_/, "").replaceAll("_", " ");
}
