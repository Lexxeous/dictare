# Capture and headset work checkpoint

Features 10 (wake phrase and hold-to-talk) and 11 (headset controls) remain
in progress on the local `feature/capture-headset-checkpoint-10-11` branch.
This checkpoint is not merged into develop or released.

## Feature 10: capture activation

Settings, local speech-recognition phrase gating, optional end-phrase
buffering, status indicators, and paired hold gestures are implemented.
The paired launcher protocol cancels on disconnect or timeout and rejects
stale, overlapping, and replayed gestures. Wake matching currently handles
Latin letters and digits and depends on recognition quality; it is not a
general multilingual wake detector.

Simulated shortcut edges have exercised live transcription and delivery;
physical Right Command down/up pairs reached an isolated launcher and socket
receiver. Physical launcher-to-engine speech delivery remains unverified.
Before considering this feature complete, test an updated, fully restarted
launcher end to end with speech, lost release, timeout, mode changes, mute,
destination changes, and shutdown. Check wake/end phrase accuracy and privacy
with real speakers and noise, voice-command compatibility, desktop and narrow
UI layouts, and each supported platform. Linux and Windows physical hold have
not been validated. A test encountered a PortAudio invalid output-channel-count
error for feedback sounds; capture continued, but the sound issue needs review.

## Feature 11: headset controls

Settings explain that tested AirPods click interception is unavailable; no
gesture mapping, Siri suppression, or interception is implemented. On the
tested AirPods A2564 and macOS 15.5, media-event monitoring and the
AVAudioApplication input-mute callback received no gesture events, and an
IOHID open attempt was unsupported. Double/triple gestures invoked Siri.
These observations do not establish behavior for every device or OS version.

Next, investigate supported device-specific APIs and permissions, and verify
whether distinct gestures and safe consumption are possible on actual target
hardware. Only expose mappings after capability and system-behavior restoration
are demonstrated. Keep unsupported devices clearly labeled.

The ignored `feature-requests/IMPLEMENTATION-HANDOFF-10-11.md` contains local
investigation history and test details when available. The development stack
may be user-owned; do not stop it without checking first.
