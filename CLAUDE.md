# Dictare — Claude Code Guide

Read [AGENTS.md](AGENTS.md) first for repository-specific instructions, code
standards, branch workflow, and development checks. Also consult
[ARCHITECTURE.md](ARCHITECTURE.md), [CONTRIBUTING.md](CONTRIBUTING.md), and
[SECURITY.md](SECURITY.md) when relevant. Keep this file as a short entry point;
do not duplicate the shared project rules here.

Dictare is a local voice-input layer for coding agents. It delivers
transcriptions over OpenVIP HTTP/SSE. It is not an autonomous agent runtime or
a multi-agent orchestrator.

Use the OpenVIP Python SDK (`from openvip import Client`) for client-side
protocol calls. Preserve platform-specific service behavior and the engine's
graceful shutdown and restart semantics. Follow the session adapter contracts
when adding or changing agent CLI integrations.

Do not push, publish, tag, or create a pull request unless the user asks.
