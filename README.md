<div align="center">

<img src="https://raw.githubusercontent.com/dragfly/dictare/main/assets/icon.svg" width="80" height="80" alt="dictare icon">

# DICTA**re**™

**Voice layer for AI coding agents.**

Speak to your agent. No window focus required. 100% local.

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/dragfly/dictare/actions/workflows/ci.yml/badge.svg)](https://github.com/dragfly/dictare/actions)

[dictare.io](https://dictare.io) · [OpenVIP™ Protocol](https://openvip.dev)

</div>

<div align="center">

[![Watch the video](https://img.youtube.com/vi/8RThA4HRd8w/maxresdefault.jpg)](https://youtu.be/8RThA4HRd8w)

*If you want to know how a poker game turned into a voice interaction system for coding agents...* **[watch this →](https://youtu.be/8RThA4HRd8w)**

</div>

---

## Why dictare

Most voice tools (Wispr Flow, Superwhisper, etc.) simulate keystrokes — they type into
whatever window has focus. Switch to your browser and your code gets your voice.

Dictare uses a protocol. Your agent listens via SSE and receives transcriptions **regardless
of window focus**. Your coding agent can be behind 3 other windows — it still gets your words.

## Features

- **No focus required** — agent receives voice even when its window is in the background
- **Agent-native** — transcriptions go to the agent protocol, not a text field
- **100% local** — STT runs on-device, zero data leaves your machine
- **Multi-agent** — switch agents by voice: *"agent coding"*, *"agent review"*
- **Open protocol** — [OpenVIP](https://openvip.dev) — any tool can implement the SSE endpoint
- **Bidirectional** — STT (voice in) + TTS (voice out)

## Install

**macOS, recommended** — [full guide](https://dictare.io/docs/installation/)

```bash
brew tap dragfly/tap
brew install dictare
dictare setup
```

Homebrew installs the Dictare entry point and macOS dependencies. Dictare owns
the runtime in `~/.local/share/dictare/versions/`; Homebrew also provides the
signed launcher source used by `dictare setup`.

**Linux or direct install**

```bash
curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
```

Upgrades and rollback are managed by Dictare, not by Homebrew:

```bash
dictare upgrade
dictare rollback
dictare repair
```

Clean reinstall on macOS:

```bash
dictare uninstall
brew uninstall dictare
brew install dictare
dictare setup
```

### Permissions

> **macOS** — grant when prompted:
> 1. **Microphone** — prompted on first launch
> 2. **Input Monitoring** — System Settings → Privacy & Security → enable Dictare
> 3. **Accessibility** — needed for keyboard mode (typing into other apps)
>
> After granting all three: `dictare repair`

> **Linux** — two steps:
> 1. **Input group** (hotkey, X11 + Wayland): `sudo usermod -aG input $USER` — log out/in
> 2. **ydotool** (keyboard mode on Wayland): `sudo apt install ydotool`

## Quick Start

```bash
dictare agent freddie       # starts the default profile (OpenAI Codex)
```

That's it. The service starts automatically. Speak — your agent receives the transcription.

If you prefer a different coding agent:

```bash
dictare agent ozzy --profile codex      # OpenAI Codex
dictare agent gilmour --profile gemini  # Google Gemini CLI
dictare agent bowie --profile aider     # Aider
```

To discover options, run `dictare --help`. Command groups have their own
help: `dictare service --help` lists commands such as `stop`, and
`dictare agent --help` lists agent options.

## How It Works

```
  Microphone
      │
      ▼
  STT Module       Whisper (MLX / CTranslate2) or Parakeet (ONNX)
      │             all local, zero cold-start
      ▼
  Pipeline         submit detection, mute control, agent switching
      │
      ▼
  OpenVIP          HTTP / SSE — open protocol
      │
      ▼
  Agent            receives transcription, no window focus needed
```

The engine runs as a background service (launchd on macOS, systemd on Linux).
STT models are preloaded at startup. Each agent connects in its own terminal.

## Agent Profiles

Profiles are predefined in `~/.config/dictare/config.toml`:

```toml
[agent_profiles]
default = "codex"
live_dangerously = false

[agent_profiles.claude]
command = ["claude", "--max-turns", "10000"]
continue_args = ["-c"]
live_dangerously_args = ["--dangerously-skip-permissions"]
description = "Claude"

[agent_profiles.codex]
command = ["codex"]
continue_args = ["resume", "--last"]
live_dangerously_args = ["--dangerously-bypass-approvals-and-sandbox"]
description = "OpenAI Codex"

[agent_profiles.gemini]
command = ["gemini"]
continue_args = ["--resume", "latest"]
live_dangerously_args = ["--yolo"]
description = "Google Gemini"

[agent_profiles.aider]
command = ["aider"]
description = "Aider (AI pair programming)"

[agent_profiles.pi]
command = ["pi"]
continue_args = ["-c"]
description = "Pi"
```

Then connect:

```bash
dictare agent freddie                      # default profile (codex)
dictare agent ozzy --profile claude        # use claude profile
dictare agent freddie --continue           # resume the named agent session
dictare agent freddie resume               # shorthand for --continue
dictare agent freddie -- claude --model opus  # explicit command override
```

For Codex, continuation uses the named agent binding when available; otherwise
it selects the newest Codex session in the current folder. Dictare displays the
selected session ID before Codex starts, or explains when it must delegate
selection to the configured resume arguments.

## Voice Commands

| Say | Action |
|---|---|
| *"ok, submit"* / *"ok, send"* / *"ok, invia"* / *"ja, senden"* | Submit to agent (Enter) |
| *"ok, mute"* / *"ok, hold on"* | Mute (stop listening) |
| *"ok, listen"* / *"ok, listen up"* | Unmute (resume listening) |
| *"agent coding"* / *"agent review"* | Switch active agent |

Submit triggers are multilingual (en, de, es, it, fr) and fully configurable.

## Hotkey Cheat Sheet

Default hotkey: **Right ⌘** (macOS) / **Scroll Lock** (Linux).

| Gesture | Action |
|---------|--------|
| **Single tap** | Toggle listening on/off |
| **Double tap** | Submit (send Enter to agent) |
| **Right Alt + hotkey** | Switch mode: agents ↔ keyboard |

## Service Management

Run `dictare service --help` to see the complete service command list.

```bash
dictare upgrade             # Install latest runtime and switch atomically
dictare rollback            # Switch back to the previous runtime
dictare repair              # Repair runtime/service/launcher integration
dictare uninstall           # Move runtime/service state aside for clean reinstall
dictare service install     # Install + enable (auto-starts at login)
dictare service start       # Start the service
dictare service stop        # Stop the service
dictare service restart     # Restart the service and wait for engine readiness
dictare service status      # Show service and engine status
dictare service logs        # View recent logs
dictare service uninstall   # Remove the service
```

The bottom of the settings **Home** page has a **Stop Dictare** control. It asks for confirmation
and requests a clean engine shutdown, distinct from stopping listening. The
page reports when the engine disconnects and explains how to start it again
from the tray or usual launcher. Launch-at-login preferences are unchanged.
A lost request connection is reported as unconfirmed rather than as success.

## Home and Documentation

Settings opens on **Home**, with Start listening / Stop listening controls,
the current destination for your words, and voice-command and keyboard cheat
sheets. Click the Dictare logo to return Home. On a narrow screen, use the menu
icon to open navigation from the top. Select a page, use the close icon, or
press Escape to close it. On desktop, the same control collapses or expands the
sidebar. Choose light, system, or dark appearance under General settings.

**Documentation** displays the README included with your installed copy as
rendered Markdown. Reading it does not require GitHub or an internet connection;
use the copy icon on a code block to copy its contents. External links open separately.
Remote badges and images appear as descriptions
to avoid loading external resources. Home keeps everyday guidance separate
from the README's installation and developer reference.

Stopping listening keeps Dictare running. **Stop Dictare** is the separate,
confirmed action that closes the whole engine.

## Personal voice commands

Open **Commands** in settings and turn on **Use my voice commands** to choose
your own complete phrases for Mute, Resume, and Send, such as “Dictare mute,”
“Dictare listen,” and “Dictare send.” Enter one phrase per line, then save.
Home shows the saved phrases. Other speech is still dictated while listening.

Each action accepts 1–32 phrases of 1–10 words. Matching uses the existing
Latin-letter/number tokenizer, ignoring case, punctuation, and accents. Choose
distinct phrases for different actions; conflicting phrases are rejected
together without changing the file. Empty fields restore the default phrases.

Turning personal commands off restores your existing advanced trigger patterns,
including language-specific choices. The master voice-control switch still
applies. Resume works after voice mute; use Home or your shortcut to start
fully stopped listening. Voice mute currently keeps recognition active to hear
Resume; it does not turn off microphone capture.

## Standard mute and strict mute

Standard voice mute keeps listening for your configured Resume phrase; it
suppresses normal dictation and its feedback while it waits. To stop microphone
input and audio instead, choose **Strict mute** on Home. Press your hotkey to
resume; a working hotkey is required. Strict mute stays active across a normal
engine restart. If Dictare cannot confirm that audio stopped, Home shows the
problem instead of claiming silence.

For source development, global hotkeys are disabled to avoid interfering with
an installed engine. Simulate a tap using `./scripts/dev.sh hotkey`.

## Review words before sending

In Settings → General, turn on **Review words before sending** and save. After
each prompt, Dictare stops listening and shows your words and their assistant
on Home. Choose Send or Discard, then start listening again when ready. A
failed send leaves the unsent words visible. The destination is the original
assistant connection; reconnecting under the same name does not redirect it.
Sending queues the message for that connection, which is not a guarantee the
assistant has processed it.

Keyboard mode cannot safely hold the focused window as a destination. In that
mode, copy your words from the review panel and discard the draft. A pending
prompt is kept in memory only and is lost if Dictare closes. Resolve it before
stopping or restarting from Dictare.

## Privacy and local diagnostics

Normal dictation processes microphone audio in memory. The latest transcript
stays in memory for resend and status; Dictare does not create a transcript
history or save microphone recordings in its normal dictation path.

Operational logs retain counts, timing, delivery status, session/destination
identifiers, and launch metadata. Normal logs omit transcript previews and
recognized command text. Agent `--verbose` and engine debug logging can include
spoken content; enable them only when needed and review logs before sharing.
This change does not remove content from older log files.

Aggregate usage statistics are saved locally. Speech synthesis can cache
generated audio under Dictare's data directory (`tts-cache`); this is separate
from microphone recordings. An assistant receiving your words may store its
own conversation history, which Dictare does not manage or delete.

## Keyboard Mode

No agent? Use dictare as a dictation tool — voice to keystrokes in any app.

```bash
dictare config set output.mode keyboard
```

**Hotkey** to toggle listening (configurable):
- macOS: **Right ⌘** by default
- Linux: **Scroll Lock** by default

```bash
dictare config set hotkey.key KEY_RIGHTALT   # change hotkey
```

## Text-to-Speech

```bash
dictare speak "Hello world"
dictare speak --engine piper "Hello"
echo "Hello" | dictare speak
```

Engines: `espeak`, `say` (macOS), `piper`, `kokoro`

## Configuration

```bash
dictare config edit           # Open config in editor
dictare config list           # Show all settings
dictare config get stt.model
dictare config set stt.language it
```

Full configuration reference at [dictare.io/docs/configuration](https://dictare.io/docs/configuration/).

## Development

Use the checkout-local runner when you want to try source changes without
calling the Homebrew-installed `dictare` command:

```bash
./scripts/dev.sh setup
./scripts/dev.sh run --help
./scripts/dev.sh stack
```

Open `http://127.0.0.1:5173/ui/`. In another terminal use
`./scripts/dev.sh listen` to start capture or `./scripts/dev.sh pause` to stop
capture. The local runner disables global hotkey handling; it does not use
the installed macOS launcher to control the source engine.

The runner uses this repository's `.venv`, keeps its copied config and runtime
state under the ignored `.dictare-dev/` folder, and serves its engine on port
18770 with the settings UI on port 5173. The installed service on port 8770 and
its runtime remain separate. Add `--mlx` to `setup` on Apple Silicon if you
want the MLX speech stack. `./scripts/dev.sh test`, `lint`, and `typecheck` run
checks through the same local Python environment.

For the underlying manual setup:

```bash
git clone https://github.com/dragfly/dictare && cd dictare

# macOS Apple Silicon (MLX GPU acceleration)
uv sync --python 3.11 --extra mlx

# macOS Intel / Linux
uv sync --python 3.11

# Run engine in foreground
uv run --python 3.11 dictare serve

# Tests
uv run --python 3.11 pytest tests/ -x

# Tests (parallel)
uv run --python 3.11 pytest tests/ -x -n auto
```

> Ghostty users: add `keybind = shift+enter=text:\n` to config. See [TERMINAL_COMPATIBILITY.md](TERMINAL_COMPATIBILITY.md).

## Protocol

dictare is the reference implementation of [OpenVIP](https://openvip.dev) — an open protocol for
voice input to AI agents. Any tool can implement the SSE endpoint and receive
voice transcriptions from dictare.

## Legacy Homebrew Installs

If you installed Dictare before `0.5.0` with the old Homebrew-owned runtime,
clean that install first:

```bash
curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/scripts/uninstall.sh | bash
```

Then install with either supported entry point.

Homebrew-guided macOS install:

```bash
brew tap dragfly/tap
brew install dictare
dictare setup
```

Direct installer:

```bash
curl -fsSL https://raw.githubusercontent.com/dragfly/dictare/main/install.sh | bash
```

Both paths end in the same Dictare-owned runtime store. Your config and models
are preserved in `~/.config/dictare/` and `~/.local/share/dictare/`.

## License

MIT

### Settings UI checks

From `ui/`, run `npm test` for shutdown confirmation and protocol checks
(requires Node 22.18 or newer for TypeScript stripping),
`npx --no-install svelte-check --tsconfig ./tsconfig.json`, and `npm run build`.
The production build updates the packaged UI in `src/dictare/ui/dist/`.
For a source backend on another port, set `DICTARE_API_TARGET` to its origin
when starting Vite; `/api` and `/openvip` requests are proxied to that engine.
When reusing dependencies across Git worktrees, explicitly set
`DICTARE_DEV_DEPENDENCIES` to the shared `ui/node_modules` directory in an
ignored `ui/.env.local`. Vite keeps its file-serving boundary enabled.
