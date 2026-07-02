<h1 align="center">Dictalo</h1>

<p align="center">
  <b>Voice dictation for Windows.</b> Press <kbd>F9</kbd>, speak, press <kbd>F9</kbd> again —
  your words are typed into whatever app you're using.
</p>

<p align="center">
  <b>100% local</b> · <b>private</b> · <b>free & open source</b> · GPU-accelerated (NVIDIA)
</p>

<p align="center">
  <img src="assets/overlay-recording.png" width="440" alt="Dictalo recording overlay with live voice spectrum">
</p>

---

## What it is

Dictalo is a free, local, open-source dictation app for Windows — a clone of [Wispr Flow](https://wisprflow.ai).
Tap <kbd>F9</kbd> to start recording (a floating overlay shows your voice spectrum in real time), tap <kbd>F9</kbd>
again, and [OpenAI's Whisper](https://github.com/openai/whisper) transcribes **on your own GPU** and pastes the
text into the field you're in — **any app**: browser, chat, editor, IDE.

It lives in the system tray, starts with Windows, and stays out of your way.

> **No cloud. No account. No subscription. Your audio never leaves your PC.**

## Demo

| Recording | Transcribing |
|:---:|:---:|
| <img src="assets/overlay-recording.png" width="320" alt="Recording"> | <img src="assets/overlay-processing.png" width="320" alt="Processing"> |

The overlay floats on top, is click-through, and never steals focus — so the paste lands exactly where your cursor was.

## Features

- ⚡ **Real-time local transcription** — Whisper `large-v3-turbo` on your GPU (sub-second on an RTX 3070)
- 🌎 **Spanish + English** with automatic language detection
- 📋 **Pastes into any app** — works even in Chromium/Electron apps (Slack, Discord, browsers) via real scan-code <kbd>Ctrl</kbd>+<kbd>V</kbd>
- 🎛️ **Floating overlay** with a live voice spectrum
- 🗣️ **Custom vocabulary** — feed it names and terms so Whisper nails the words you actually use
- 🔒 **100% offline** — private by design, nothing is uploaded
- 🧰 **Tray icon, autostart, backup history, gentle sounds, settings window**
- 💤 **Resilient to sleep/resume** — re-arms the hotkey and refreshes audio after your PC wakes up

## Requirements

- **Windows 10/11** (64-bit)
- A **microphone**
- **GPU:** an **NVIDIA** card (CUDA) for real-time speed. No NVIDIA? Dictalo automatically falls back to **CPU** — it still works, just slower.

## Install

1. Download the latest **`Dictalo-Setup.exe`** from the [Releases](../../releases) page.
2. Run it. Dictalo installs to `%LOCALAPPDATA%\Programs\Dictalo`, adds a Start Menu shortcut and starts with Windows.
3. First launch loads the model into memory (~a few seconds). After that it's always warm.

> The installer is large (~1 GB) because it bundles the CUDA runtime so it works out of the box on NVIDIA GPUs.

## Usage

- **Tap <kbd>F9</kbd>** to start recording → **tap <kbd>F9</kbd>** again to stop. The text is pasted where your cursor is.
- **Double-click the tray icon** to open **Settings**: microphone, hotkey, custom vocabulary, and backup history.
- Quit from the tray icon → **Salir**.

## Build from source

Requires **Python 3.14** (64-bit) and an NVIDIA GPU for the CUDA path.

```bash
# 1. Create the virtual environment and install dependencies (~2-3 GB: faster-whisper, CUDA libs, PyInstaller)
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Run in dev (with console logs)
.venv\Scripts\python.exe main.py

# 3. Build the standalone .exe  ->  dist\Dictalo\
.venv\Scripts\pyinstaller.exe dictalo.spec --noconfirm

# 4. (optional) Build the installer  ->  Output\Dictalo-Setup.exe   (needs Inno Setup 6)
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

The Whisper model is cached separately in `~/.cache/huggingface` (downloaded once, shared across builds).

## How it works

100% Python. The pieces:

| File | Role |
|---|---|
| `main.py` | Tray, state machine, hotkey wiring, sleep/resume watchdog |
| `recorder.py` | 16 kHz mic capture + live FFT spectrum for the overlay |
| `transcriber.py` | Whisper via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on CUDA (int8), CPU fallback |
| `injector.py` | Pastes text: refocuses your window + clipboard + scan-code Ctrl+V |
| `overlay.py` | Floating, click-through, top-most overlay (Win32 layered window) |
| `settings.py` | Settings window (mic, hotkey, vocabulary, history) |
| `config.py` · `history.py` · `sounds.py` · `splash.py` | Preferences, backup history, sounds, load splash |

Whisper is OpenAI's open-source model (MIT). Dictalo runs it locally through faster-whisper — **the OpenAI API is never called**.

## Compatibility

| Platform | Status |
|---|---|
| **Windows + NVIDIA GPU** | ✅ Full speed (CUDA / GPU) |
| **Windows + AMD/Intel/no GPU** | ✅ Works on **CPU** (slower — GPU acceleration is on the roadmap) |
| **macOS / Linux** | ❌ Not supported yet — Dictalo relies on native Windows APIs (text injection, overlay, hotkey). A port is welcome as a contribution. |

## Roadmap

- 🎮 **AMD/Intel GPU acceleration** via whisper.cpp + Vulkan
- 🍎 **macOS port** (rewrite of the native layers + Metal STT backend)

## Privacy

Everything runs on your machine. Audio is captured, transcribed locally, and discarded. The only network access
Dictalo needs is a **one-time model download** on first run. There is no telemetry and no account.

## Credits & license

- [OpenAI Whisper](https://github.com/openai/whisper) — the speech recognition model (MIT)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — fast local inference (MIT)

Released under the [MIT License](LICENSE).
