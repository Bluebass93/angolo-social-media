# angolo-social-media

Repo tecnico per la pubblicazione automatica dei post social de L'Angolo del Cappotto.

- `pending/` — immagini + caption del prossimo post in uscita (svuotata dopo ogni pubblicazione)
- `scripts/publish.py` — pubblica il carosello su Instagram e il post su Facebook via Graph API
- `.github/workflows/publish.yml` — workflow manuale (Actions → "Pubblica post social" → Run workflow)

Vedi `pending/README.md` per il formato atteso.

## Post programmati

Il workflow gira da solo ogni 5 minuti (cron) e pubblica solo i post il cui orario e' passato, mai prima.
GitHub puo' ritardare i cron: aspettati la pubblicazione da 0 a ~15 minuti dopo l'orario indicato
(di solito 5-10), raramente di piu' nelle ore di punta.

**Programmare un post**: crea `pending/<nome>/` con le slide (`01-...png`, `02-...`), `caption_ig.txt`,
`caption_fb.txt` (opzionale `fb-cover.png`) e un `post.json`:

```json
{ "publish_at": "2026-10-22 10:00" }
```

L'ora e' italiana (Europe/Rome, CET/CEST gestiti da soli). Fai commit e push: fine.
Senza `publish_at` il post in sottocartella parte solo col lancio manuale.

**Annullare**: rimuovi la cartella `pending/<nome>/` (commit + push) prima dell'orario.

**Dopo la pubblicazione**: la cartella passa in `published/<nome>/` con `state.json` (id Instagram/Facebook).
Un canale gia' pubblicato non viene mai rifatto; se uno dei due fallisce, il retry successivo rifa'
solo quello mancante. Dopo 3 tentativi falliti il post e' marcato `failed` in `state.json` e non riprova piu'
(controlla l'errore in `last_error`).

**Manuale**: i file messi direttamente in `pending/` e il lancio manuale di "Pubblica post social"
funzionano come prima. Il lancio manuale ha l'opzione `dry_run` (simulazione, nessuna pubblicazione).
