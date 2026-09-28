# Dictado App: guía del proyecto

App de dictado por voz para Windows (clon de Wispr Flow). 100% Python. Local, privado, gratis.
El dueño (Ivo) escribe en español → **respondé siempre en español**.

> **Para retomar:** este archivo se carga solo al abrir la carpeta. Leé todo antes de tocar nada.
> La app **se llamaba "Dictalo"** hasta la v1.0.0; en la v1.1.0 pasó a **"Dictado App"** (nombre, ícono,
> repo `ivorojas/dictado-app`). La carpeta local sigue llamándose `Dictalo` (solo el nombre de la carpeta).
> Es 100% autónoma: su propio `.venv`, su propio repo git y todo el código acá.

## Qué hace
Tap **F9** → grabás (aparece un overlay flotante con el espectro de tu voz) → tap **F9** de nuevo →
Whisper transcribe local en GPU → **pega el texto en el campo donde estás al cortar** (cualquier app). Corre
siempre en 2do plano (ícono en la barra), arranca con Windows.

## Comandos
- **Correr en dev (con consola/logs):** `.venv\Scripts\python.exe main.py`
- **Compilar el .exe:** `.venv\Scripts\pyinstaller.exe dictado.spec --noconfirm` → `dist\DictadoApp\`
- **Autotest de la interfaz del .exe:** `dist\DictadoApp\DictadoApp.exe --selftest-ui` → escribe
  `[selftest] interfaz OK` en `%TEMP%\dictado-selftest.log` (arma Ajustes/Historial sin mostrarlos; no toca datos).
- **Instalador:** `"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss` → `Output\DictadoApp-Setup.exe`
- **Actualizar la instalada sin reinstalar:** cerrar la app y `cp -rf dist/DictadoApp/* "%LOCALAPPDATA%\Programs\Dictado App\"`
- **Íconos / imágenes del README:** `assets\render_icon.py` (icono.ico + icon.png), `assets\render.py` (overlay),
  `assets\capture_ui.py` (capturas reales de Ajustes/Historial con datos de ejemplo).
- **Versión:** está en `brand.py` (`__version__`) y en `installer.iss` (`AppVersion`): mantenerlas iguales.
- Cerrar la app: ícono en la barra → Salir.

> ⚠️ **El venv propio vive en `.venv`** (tiene faster-whisper, CUDA libs, pyinstaller). Está gitignoreado.
> Si se borra/corrompe, recrearlo: `py -3.14 -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.txt`
> (baja ~2-3GB). El modelo Whisper se cachea aparte en `~/.cache/huggingface` (compartido, no se baja de nuevo).

## Arquitectura (archivos)
```
main.py        entry point. Tray (pystray) + state machine + hotkey + wiring. Hilo principal corre
               el overlay (tkinter mainloop); tray en run_detached(); listener pynput y worker STT en hilos.
brand.py       nombre (APP_NAME), versión e ícono dibujado con PIL (3 barras pixel-perfect <40px, 5 barras >=40).
config.py      Config dataclass. Datos en ~/.dictado (prefs.json). Migra ~/.dictalo (versión vieja) al arrancar.
recorder.py    captura mic 16kHz (sounddevice). Nivel + espectro FFT en vivo para el overlay; pico/RMS por dictado.
transcriber.py STT faster-whisper large-v3-turbo en CUDA int8 (fallback CPU). Idioma acotado a en/es.
               Colchón de silencio al final, filtro de alucinaciones de subtítulos, punto final + espacio.
injector.py    pega el texto: foco a la ventana destino + clipboard + Ctrl+V (con scan codes).
cleaner.py     limpieza opcional con Gemini (OFF; el dueño NO usa IA; oculta en Ajustes pero sigue en config).
overlay.py     ventanita flotante = ventana en capas Win32 (UpdateLayeredWindow, alpha por píxel), topmost,
               click-through, NOACTIVATE. Dibuja cada cuadro con looks.render() (~6 ms). Tk root invisible.
looks.py       estilos de la ventanita: DEFAULT + 12 PRESETS, resolve() (valida prefs), render() con PIL.
splash.py      tarjeta de carga centrada mientras carga el modelo (se cierra sola al estar listo).
ui.py          kit de interfaz: tema, fuentes Segoe UI Variable + íconos Segoe Fluent, formas suavizadas
               (PIL 4x → PhotoImage), Card/Button/Chip/Tag/TagCloud/Field/Select/ScrollArea, barra de título DWM.
settings.py    ventanas de Ajustes, Historial y Apariencia (galería de estilos + Personalizar + Mis estilos).
globalkey.py   atajo global para abrir Ajustes (Ctrl+F1 por defecto, config.open_hotkey). RegisterHotKey en
               su propio hilo (no hook): consume la combinación y devuelve False si otra app ya la tiene.
               La misma tecla abre y cierra (si está abierta, aunque sea detrás de otra ventana, la cierra).
               En Ajustes, Enter copia el último dictado, cierra y devuelve el foco a donde estabas; Esc cierra.
history.py     dictados con fecha en ~/.dictado/history.json; se borran solos a los 3 días (RETENTION_DAYS).
sounds.py      sonidos sintetizados (numpy+sounddevice) en packs: Suave, Burbuja, Digital, Campana, Silencio.
dictado.spec   build PyInstaller (windowed, bundlea faster-whisper + DLLs nvidia, ficha de versión del .exe).
installer.iss  Inno Setup: instala en %LOCALAPPDATA%\Programs\Dictado App, accesos, inicio con Windows.
icono.ico      ícono (degradé cian→violeta con barras de onda), generado por assets\render_icon.py.
```

## Decisiones técnicas y gotchas (CRÍTICO, leer antes de tocar injector/overlay/ui)
- **EL BUG QUE COSTÓ TODO, `SendInput` fallaba en silencio**: la estructura `INPUT` debe medir **40 bytes
  en x64**. La `union` tenía solo `KEYBDINPUT` (32 bytes) → `SendInput` rechazaba la llamada (devolvía 0) y
  NO inyectaba nada, nunca, en ningún lado. El fix: incluir `MOUSEINPUT` en la union (el miembro más grande)
  para que mida 40. **Verificar siempre `ctypes.sizeof(_INPUT) == 40`.** Esto explicó semanas de "no pega".
- **Inyección = clipboard + Ctrl+V con SCAN CODES**: las apps Chromium/Electron (Claude, Slack, navegador)
  **ignoran teclas sintéticas sin scan code**. `_ki()` setea `wScan = MapVirtualKey(vk)`. El texto se mete al
  clipboard, se manda Ctrl+V, y el clipboard se restaura **en 2do plano** (para no demorar el sonido/overlay).
- **Foco / destino del pegado**: se pega en la ventana en foco **al CORTAR** (F9 final), no la del inicio
  (el dueño lo pidió: clic en otro campo durante el dictado → pega ahí). La del inicio es solo fallback.
  `capture_foreground()` excluye ventanas propias y escritorio/barra de tareas. `_focus_window()` solo actúa si
  el foco cambió durante la transcripción (`ForegroundLockTimeout=0` + ALT-tap + `AttachThreadInput`).
- **Hotkey = hook LL de Windows**: pynput llama al callback DENTRO del hook. Nada lento ahí (abrir el mic de
  la interfaz USB tarda) ni excepciones: Windows da de baja el hook en silencio / pynput frena el listener →
  F9 muerto. Por eso el hook solo hace `_toggles.put()` y `_toggle_worker` procesa en otro hilo. Cambiar el
  atajo desde Ajustes re-arma el listener en vivo (`_hotkey_changed`).
- **Mic = interfaz USB Focusrite** ("Analogue 1 + 2"): a veces entrega **silencio digital** (tras suspender,
  si otra app toma el dispositivo). Síntoma en el log: `[stt] proceso 0.01s` con audio de varios segundos y
  `[stt] ''`. Ahora: `pico < 1e-5` → refresh de PortAudio + sonido de error + notificación; aviso a los 3s si
  sigue muerto; si el VAD descarta todo, reintento con VAD sensible (threshold 0.25).
- **Portapapeles**: `OpenClipboard` se reintenta (otra app puede tenerlo tomado); si falla, no se pega y se
  avisa (el texto queda en Historial). Se restaura a 1s (apps lentas leían tarde y pegaban lo viejo).
- **ctypes 64-bit**: TODA llamada Win32 que devuelve/recibe HANDLE/puntero lleva `restype`/`argtypes`
  explícitos. `ui.py` usa su propia `ctypes.WinDLL("user32")` para no pisar los prototipos de injector.py.
- **tkinter, nombres prohibidos en subclases de widgets**: `self._w` (es el path interno del widget) y
  `self._register` (lo usa `after()`). Pisarlos rompe todo con errores rarísimos. Ya pasó con los dos.
- **Tk no suaviza bordes**: toda forma redondeada se renderiza con PIL a 4× → `ui.shape()` (cacheada; cada
  widget guarda su PhotoImage para que el caché pueda vaciarse sin borrar nada en pantalla).
- **Barra de título**: `ui.style_window` pinta la barra nativa del color de la ventana vía DWM (atributos 20,
  34, 35, 36; Windows 11). Se muestra con alpha 0 → estilo → alpha 1, así no hay parpadeo blanco.
- **Previsualizar la UI sin molestar al dueño**: fuera de pantalla Windows NO pinta frames/canvas de Tk (salen
  negros). Lo que funciona (ver `assets/capture_ui.py`): ventana en pantalla con alpha 0 + click-through +
  NOACTIVATE, foto con `PrintWindow(PW_RENDERFULLCONTENT)`. Al mapearse Windows la activa ~25 ms (el lock de
  foco está en 0 por la app): se devuelve el foco en el acto. **Nunca usar datos reales del dueño** en capturas.
- **pythonw / stdout**: en el .exe (sin consola) `sys.stdout` es None → cualquier print mata la app.
  `main._setup_stdio()` redirige a `~/.dictado/dictado.log` (append, tope 2MB). **Para diagnosticar: ese log.**
- **Migración Dictalo → Dictado App**: al arrancar, `config.migrate_legacy_data()` renombra `~/.dictalo` a
  `~/.dictado` (si está en uso, copia prefs/history). OJO: importar `main.py` la dispara; en pruebas no
  importarlo con la app vieja abierta. `~/.dictado-app` son restos de la app ANTERIOR a Dictalo (no usar).
- **Instalador**: mantiene el `AppId` de Dictalo (`{{D1C7A10E-...-DICTALOAPP001}}`, tal cual) para
  ACTUALIZAR la instalación vieja; `[InstallDelete]` borra su carpeta y accesos; `AppMutex` pide cerrarla.
- **Instancia única**: mutex `Global\DictadoApp_SingleInstance`; además no arranca si está abierta la vieja
  (`Global\Dictalo_SingleInstance`), porque pelearían por el atajo.
- **Overlay (v1.2)**: ya no es Tk. Es una ventana en capas Win32 propia (`overlay.LayeredWindow`): clase con
  `DefWindowProcW` como procedimiento (sin callbacks de Python; sus mensajes los despacha el mainloop de Tk,
  mismo hilo), `WS_EX_LAYERED|TRANSPARENT|TOPMOST|TOOLWINDOW|NOACTIVATE`, se muestra con
  `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE|SWP_SHOWWINDOW)` y cada cuadro va por `UpdateLayeredWindow`
  (BGRA con alpha premultiplicado). Medido: nunca toma el foco. Permite sombra, cristal, resplandor, sin fondo.
- **Estilos de la ventanita**: config guarda `overlay_preset` ("aurora"…, "custom" o "mine:<nombre>"),
  `overlay_custom` y `overlay_mine`; `looks.current(config)` devuelve el estilo resuelto. `looks.resolve`
  descarta valores inválidos (un prefs.json viejo o editado a mano nunca rompe el overlay).
- **Movimiento de las barras (solo visual)**: bandas del mic → `looks.resample` → `looks.exaggerate`
  (curva gain+gamma según `config.bar_intensity`, 0.8 por defecto, deslizador en Ajustes) → `looks.follow`
  (suben rápido, bajan suave). El silencio sigue quieto (0 → 0). Las barras usan hasta ~78% del alto y está
  verificado que nunca se salen de la forma (648 combinaciones al 100%). El dueño NO quiere tocar la
  ganancia de audio/transcripción: lo que se exagera es solo lo visual.
- **Crear el Tk root activa la ventana un instante** (aunque se retire enseguida): pasa al arrancar la app (ok)
  y en autotests/capturas → ahí se devuelve el foco en el acto (`ui.restore_foreground`).
- **Arranque instantáneo**: el modelo carga + warmup del mic en un hilo de fondo; el tray aparece al toque.
  El delay de ~6s al abrir es cargar el modelo en VRAM; **se resuelve con el auto-arranque** (queda caliente).
- **Modelo STT**: large-v3-turbo, CUDA int8, `beam_size=5`, `hotwords=vocabulario`,
  `condition_on_previous_text=False`. RTX 3070 del dueño → ~0.45 s por dictado corto (36% es detectar idioma).
  Medido: int8_float16/float16 no mejoran nada; nuestros cambios no afectan la precisión. Pesa la distancia al mic.
- **No usa la nube ni IA** para el dictado normal. Cleanup Gemini existe pero está OFF y oculto.

## Estado actual (v1.2.0)
Funciona end-to-end: dicta, transcribe, pega donde cortás, overlay con espectro, sonidos, splash, avisos si el
mic no capta o no se pudo pegar, Ajustes rediseñados (guardado automático), historial de 3 días con ventana
propia y búsqueda, vocabulario en etiquetas con "Ver más", auto-arranque, idioma en/es.
v1.2: ventanita personalizable (12 estilos prearmados, editor pieza por pieza con vista previa en vivo,
"Mis estilos" con nombre) y packs de sonidos.

## Cómo verificar (sin poder hablar)
El asistente NO puede usar la voz ni ver la pantalla del dueño. Para validar:
- Compilar + autotest de interfaz (`--selftest-ui`) + smoke-test: lanzar el .exe, leer
  `~/.dictado/dictado.log` → debe llegar a "Listo para dictar. ✓" sin Traceback.
- Diseño: `assets/capture_ui.py` (o un visor igual) genera capturas reales con datos de ejemplo.
- Verificaciones de API se pueden correr (ej. `ctypes.sizeof(_INPUT)==40`).
- Lo demás (que pegue, calidad de audio) lo prueba el dueño y reporta.

## Ideas a futuro (discutidas)
El dueño YA RECHAZÓ por ahora: limpieza con IA, modo comando, tono por app, reemplazos/snippets, preview toast,
detectar el idioma mientras habla (más rápido pero no garantiza igual precisión; pidió solo mejoras objetivas).
Hecho: punto final + espacio, normalización de espacios, idioma en/es, historial, resiliencia a suspensión,
colchón de silencio + filtro de alucinaciones, pegado robusto, rediseño completo de Ajustes/Historial, ícono y
nombre nuevos, publicación: repo **PÚBLICO** `ivorojas/dictado-app` (README en inglés, MIT, releases).
Roadmap público: aceleración GPU AMD/Intel (whisper.cpp+Vulkan). Mac se sacó a pedido (Windows-only).

## Convenciones
- Responder siempre en español. Mensajes de usuario en la app, en español.
- Sin comentarios obvios. Código limpio y consistente con el existente. Títulos de la UI sin guiones.
- Verificar (compilar + autotest + smoke-test del .exe + leer el log) antes de reportar algo como hecho.
- Tras cambiar código: recompilar y pisar la instalada (`%LOCALAPPDATA%\Programs\Dictado App`).
  Si no, el dueño sigue usando la versión vieja (pasó muchas veces: "no se ejecutaba en la que usaba").
