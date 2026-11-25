# DeafNews TikTok — pipeline

Video verticali da articoli deafnews.it, descritti da un file JSON in `specs/<slug>.json`.

```bash
python3 tools/make.py setup                       # una volta per sessione: modelli Kokoro + pacchetti
python3 tools/make.py check   specs/<slug>.json   # voce (in cache) + contact sheet -> $DN_WORK/out/check.jpg
python3 tools/make.py still   specs/<slug>.json <scena> <secondi>
python3 tools/make.py build   specs/<slug>.json   # video + copertina in $DN_WORK/out
python3 tools/make.py publish specs/<slug>.json   # copia in videos/ covers/ specs/, commit, push, verifica URL
```

- `engine.py`: modelli di scena (title, text, emoji, badge, pill, card, list, code, gauge, timeline, line, hearts, preset `cta`).
- `make.py`: voce Kokoro `im_nicola`, effetti sonori automatici per tipo di elemento, musica ducked, render parallelo, montaggio.
- `sfx.py`: effetti sonori e musica sintetizzati.
- Esempio completo: `specs/vcenter-zero-day.json`.

Cartella di lavoro: `$DN_WORK` (predefinita `/home/claude/dn-work`). Modelli: `$KOKORO_DIR` (predefinita `/home/claude/kokoro`).
