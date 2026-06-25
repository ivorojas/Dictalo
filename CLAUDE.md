# Dictalo — guía del proyecto

App de dictado por voz para Windows (clon de Wispr Flow). 100% Python. Local, privado, gratis.
El dueño (Ivo) escribe en español → **respondé siempre en español**.

> **Para retomar:** este archivo se carga solo al abrir la carpeta. Leé todo antes de tocar nada.
> Dictalo **reemplazó** a una app vieja ("Dictation App") que ya **se eliminó**. Dictalo es 100% autónomo:
> tiene su propio `.venv`, su propio repo git y todo el código en esta carpeta.

## Qué hace
Tap **F9** → grabás (aparece un overlay flotante con el espectro de tu voz) → tap **F9** de nuevo →
Whisper transcribe local en GPU → **pega el texto en el campo donde estás** (cualquier app). Corre
siempre en 2do plano (ícono en la barra), arranca con Windows.

## Comandos
- **Correr en dev (con consola/logs):** `.venv\Scripts\python.exe main.py`
- **Compilar el .exe:** `.venv\Scripts\pyinstaller.exe dictalo.spec --noconfirm` → `dist\Dictalo\`
- **Instalador:** `"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss` → `Output\Dictalo-Setup.exe`
- **Actualizar la instalada sin reinstalar:** después de compilar, `cp -rf dist/Dictalo/* "%LOCALAPPDATA%\Programs\Dictalo\"`
- Cerrar la app: ícono en la barra → Salir.

> ⚠️ **El venv propio vive en `.venv`** (tiene faster-whisper, CUDA libs, pyinstaller). Está gitignoreado.
> Si se borra/corrompe, recrearlo: `py -3.14 -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.txt`
> (baja ~2-3GB). El modelo Whisper se cachea aparte en `~/.cache/huggingface` (compartido, no se baja de nuevo).

## Arquitectura (archivos)
```
main.py        — entry point. Tray (pystray) + state machine + hotkey + wiring. Hilo principal corre
                 el overlay (tkinter mainloop); tray en run_detached(); listener pynput y worker STT en hilos.
config.py      — Config dataclass. Carga ~/.dictalo/prefs.json. Incluye vocabulario editable.
recorder.py    — captura mic 16kHz (sounddevice). Calcula nivel + espectro FFT en vivo para el overlay.
transcriber.py — STT faster-whisper large-v3-turbo en CUDA int8. Detección de idioma acotada a en/es.
                 Cierra el texto con punto final. _register_cuda_dlls() carga las DLLs CUDA.
injector.py    — pega el texto: foco a la ventana destino + clipboard + Ctrl+V (con scan codes).
cleaner.py     — limpieza opcional con Gemini (OFF por defecto; el dueño NO usa IA).
overlay.py     — overlay flotante (tkinter topmost, NOACTIVATE, click-through). Barras = espectro real.
splash.py      — tarjeta de carga centrada mientras carga el modelo (se cierra sola al estar listo).
settings.py    — ventana de Ajustes (tema oscuro): mic, atajo, vocabulario, historial de respaldo.
history.py     — guarda los últimos 12 dictados en ~/.dictalo/history.json (respaldo si no pegó).
sounds.py      — sonidos suaves sintetizados (numpy+sounddevice), reemplazan winsound.Beep.
dictalo.spec   — build PyInstaller (windowed, bundlea faster-whisper + DLLs nvidia).
installer.iss  — Inno Setup (instala en %LOCALAPPDATA%\Programs\Dictalo, shortcuts, startup).
icono.ico      — ícono verde-agua.
```

## Decisiones técnicas y gotchas (CRÍTICO — leer antes de tocar injector/overlay)
- **EL BUG QUE COSTÓ TODO — `SendInput` fallaba en silencio**: la estructura `INPUT` debe medir **40 bytes
  en x64**. La `union` tenía solo `KEYBDINPUT` (32 bytes) → `SendInput` rechazaba la llamada (devolvía 0) y
  NO inyectaba nada, nunca, en ningún lado. El fix: incluir `MOUSEINPUT` en la union (el miembro más grande)
  para que mida 40. **Verificar siempre `ctypes.sizeof(_INPUT) == 40`.** Esto explicó semanas de "no pega".
- **Inyección = clipboard + Ctrl+V con SCAN CODES**: las apps Chromium/Electron (Claude, Slack, navegador)
  **ignoran teclas sintéticas sin scan code**. `_ki()` setea `wScan = MapVirtualKey(vk)`. El texto se mete al
  clipboard, se manda Ctrl+V, y el clipboard se restaura **en 2do plano** (para no demorar el sonido/overlay).
- **Foco**: `capture_foreground()` guarda tu ventana al apretar F9 (excluye ventanas propias de Dictalo).
  `_focus_window()` se la devuelve antes de pegar, con `ForegroundLockTimeout=0` + ALT-tap + `AttachThreadInput`
  (Windows bloquea `SetForegroundWindow` desde un proceso de fondo). Guarda: nunca pega en ventana propia.
- **ctypes 64-bit**: TODA llamada Win32 que devuelve/recibe HANDLE/puntero lleva `restype`/`argtypes`
  explícitos. Sin esto el puntero se trunca a 32 bits → "access violation writing 0x0".
- **DLLs CUDA**: el wheel de ctranslate2 NO trae cuBLAS/cuDNN. Vienen de `nvidia-*-cu12` (requirements) y
  `transcriber._register_cuda_dlls()` las registra en el DLL search path (usa `sys._MEIPASS` si frozen).
- **pythonw / stdout**: en el .exe (sin consola) `sys.stdout` es None → cualquier print mata la app.
  `main._setup_stdio()` redirige a `~/.dictalo/dictalo.log` (line-buffered). **Para diagnosticar: leer ese log.**
- **Overlay sin robar foco**: estilos `WS_EX_NOACTIVATE | WS_EX_TRANSPARENT` aplicados al HWND top-level real
  (`GetAncestor(GA_ROOT)`), mostrar vía alpha (no deiconify). Así no roba el foco y el Ctrl+V cae en tu campo.
- **Instancia única**: named mutex `Global\Dictalo_SingleInstance` en main. Sin esto se apilan instancias y
  se pisan en el hotkey.
- **Arranque instantáneo**: el modelo carga + warmup del mic en un hilo de fondo; el tray aparece al toque.
  El delay de ~6s al abrir es cargar el modelo en VRAM — **se resuelve con el auto-arranque** (queda caliente).
- **Auto-arranque**: hay un shortcut en la carpeta Startup de Windows → Dictalo arranca con la PC. Por eso
  después de reiniciar es instantáneo (siempre corriendo, como Wispr).
- **Modelo STT**: large-v3-turbo, CUDA int8, `beam_size=5` (precisión), `hotwords=vocabulario`,
  `condition_on_previous_text=False`. RTX 3070 del dueño → sub-segundo por dictado.
- **No usa la nube ni IA** para el dictado normal. Cleanup Gemini existe pero está OFF (el dueño no lo quiere).

## Estado actual (MVP funcional y verificado andando)
Funciona end-to-end: dicta, transcribe perfecto, pega en cualquier app, overlay con espectro, sonidos suaves,
splash, historial, ajustes, vocabulario, auto-arranque, idioma en/es, punto final.

## Cómo verificar (sin poder hablar)
El asistente NO puede usar la voz ni ver la pantalla del dueño. Para validar:
- Compilar y hacer smoke-test: lanzar el .exe, esperar ~17s, leer `~/.dictalo/dictalo.log` → debe llegar a
  "Listo para dictar. ✓" sin Traceback.
- Verificaciones de API se pueden correr (ej. `ctypes.sizeof(_INPUT)==40`, `SendInput` devuelve >0).
- Lo demás (que pegue, calidad de audio, diseño) lo prueba el dueño y reporta.

## Ideas a futuro (discutidas)
El dueño YA RECHAZÓ por ahora: limpieza con IA, modo comando, tono por app, reemplazos/snippets, preview toast.
Le interesó y ya está hecho: punto final + espacio al final, idioma en/es, sensibilidad de barras, historial,
doble-clic abre Ajustes, CLAUDE.md/docs, venv propio de Dictalo (la carpeta vieja ya se eliminó).
Posible próximo: respaldo en GitHub (no hay remoto aún).

## Convenciones
- Responder siempre en español. Mensajes de usuario en la app, en español.
- Sin comentarios obvios. Código limpio y consistente con el existente.
- Verificar (compilar + smoke-test del .exe + leer el log) antes de reportar algo como hecho.
- Tras cambiar código: recompilar y pisar la instalada (`cp dist/Dictalo/* a %LOCALAPPDATA%\Programs\Dictalo`).
  Si no, el dueño sigue usando la versión vieja (pasó muchas veces: "no se ejecutaba en la que usaba").
