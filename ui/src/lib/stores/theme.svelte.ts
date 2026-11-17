import { browser } from "$app/environment";

const STORAGE_KEY = "dictare-theme";

export type Theme = "light" | "dark" | "system";

function savedTheme(): Theme {
	if (!browser) return "system";
	try {
		const saved = localStorage.getItem(STORAGE_KEY);
		return saved === "light" || saved === "dark" ? saved : "system";
	} catch {
		return "system";
	}
}

let theme = $state<Theme>(savedTheme());

export function getTheme(): Theme {
	return theme;
}

export function setTheme(t: Theme): void {
	theme = t;
	if (browser) {
		try {
			localStorage.setItem(STORAGE_KEY, t);
		} catch {
			// The selected theme still applies when browser storage is unavailable.
		}
	}
	applyTheme(t);
}

export function applyTheme(t: Theme): void {
	if (!browser) return;
	const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
	const dark = t === "dark" || (t === "system" && prefersDark);
	document.documentElement.classList.toggle("dark", dark);
}
