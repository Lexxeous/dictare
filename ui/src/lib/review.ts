export type ReviewDraft = {
	id: string;
	destination: string;
	messages: string[];
	sending: boolean;
	can_send: boolean;
};

export async function fetchReview(): Promise<ReviewDraft | null> {
	const response = await fetch("/api/review", { cache: "no-store" });
	if (!response.ok) throw new Error("Could not check the pending prompt.");
	const result = await response.json();
	return result.draft as ReviewDraft | null;
}

export async function resolveReview(id: string, action: "send" | "discard"): Promise<string> {
	const response = await fetch(`/api/review/${encodeURIComponent(id)}/${action}`, { method: "POST" });
	if (!response.ok) throw new Error("Could not reach Dictare. Your prompt may still be waiting.");
	const result = await response.json();
	return result.status as string;
}
