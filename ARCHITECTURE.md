# Architecture

## Overview

dictare is a **voice layer for AI coding agents**. It implements the [OpenVIP protocol](spec/) —
an open HTTP/SSE protocol for delivering voice input to any AI agent.

Unlike tools that simulate keystrokes (requiring window focus), dictare delivers transcriptions
directly to the agent's SSE endpoint. The agent receives voice input regardless of window focus.

```
  Hotkey (Right ⌘)
        │
        ▼
  Audio Capture + VAD
  (Silero, local)
        │
        ▼
  STT Engine
  (Whisper via MLX/CTranslate2, or Parakeet via ONNX — all local)
        │
        ▼
  Pipeline
  (filters: language detection, submit trigger, agent switching)
        │
        ▼
  HTTP Server (FastAPI)
  ├── OpenVIP SSE endpoint  →  agent receives transcription (no focus needed)
  └── Web UI                →  settings, status, TTS
```

## Components

```
src/dictare/
├── core/        Engine, HTTP server (FastAPI), OpenVIP SSE
├── stt/         STT engines: MLXWhisper, FasterWhisper, Parakeet (ONNX)
├── audio/       Capture (sounddevice), VAD (Silero), device monitoring
├── hotkey/      IPC transport (Unix socket), runtime status
├── pipeline/    Composable filters + executors (DI via PipelineLoader)
├── agent/       Agent client (openvip SDK)
├── tts/         TTS engines: Kokoro, Piper, espeak, macOS say
├── daemon/      launchd (macOS) / systemd (Linux) service management
├── tray/        System tray (pystray)
└── cli/         Typer CLI entry points
```

On macOS, a Swift launcher (`Dictare.app`) handles `CGEventTap` for the hotkey,
communicating with the Python engine via Unix socket IPC.
The launcher also owns an optional single AppKit/WebKit window, requested by
the tray through a local distributed notification. It loads the existing UI
from a loopback engine address; the browser and window share the engine and
settings, while keeping separate tab-takeover groups. Closing the window hides
it without changing engine lifecycle. This window requires the Swift launcher;
the browser remains usable with source or remote engines.

## STT Engines

Capture lifetime is separate from recognition-worker recovery. VAD events,
queued recognition jobs, completions and timeout events carry a capture
generation. Discard and completed Stop boundaries invalidate that generation,
clear pending capture/deferred submit, and reject old work before state changes,
transcript statistics/logging, pipeline control actions or delivery. A native
recognizer already executing may finish; its canceled result is ignored.

The controller owns state/watchdog cancellation. The engine's reentrant delivery
lock serializes cancellation with pipeline execution and sending. Reset VAD
under its existing owner lock before advancing the generation, so callbacks
already running retain their old identity. VAD callbacks must not acquire the
delivery lock while holding the VAD lock. Preserve queue shutdown sentinels.
This capture contract does not itself implement strict mute or cancel TTS.

| Config | Engine | Runtime | Hardware |
|--------|--------|---------|----------|
| `tiny`…`large-v3-turbo` | FasterWhisperEngine | CTranslate2 | Linux / Intel Mac |
| `tiny`…`large-v3-turbo` | MLXWhisperEngine | MLX | macOS Apple Silicon |
| `parakeet-v3` | ParakeetEngine | ONNX Runtime | any |

## Service Architecture

dictare runs as a persistent background service (launchd on macOS, systemd on Linux).
The STT model is preloaded at startup — zero cold-start when you speak.

Agents connect via `dictare agent <name>` which opens an SSE connection and forwards
transcriptions to the agent process (Claude Code, Cursor, Aider, etc.).

## Protocol

dictare is the reference implementation of [OpenVIP](spec/) — an open spec for
voice input to AI agents. Any tool can implement the SSE endpoint and receive
voice commands from dictare.
