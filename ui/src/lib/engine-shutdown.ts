/** Confirmation and transport remain separate so cancellation sends nothing. */
export async function confirmEngineShutdown(
	confirm: (message: string) => boolean,
	send: () => Promise<void>,
	hasUnsavedChanges = false
): Promise<boolean> {
	const warning = hasUnsavedChanges ? " Your unsaved settings will not be saved." : "";
	if (!confirm(
		"Stop Dictare entirely? This stops the engine, not just listening. " +
		"The settings page will disconnect. Start Dictare again from the tray or your usual launcher." + warning
	)) return false;
	await send();
	return true;
}
