#!/usr/bin/env python3
"""
Pubblica il carosello in pending/ su Instagram e Facebook.

Convenzione cartella pending/:
  pending/01-xxx.webp, 02-xxx.webp, ... (ordine alfabetico = ordine slide)
  Le slide possono essere anche video: pending/03-xxx.mp4 (H.264, senza audio va bene).
  Una slide = un solo file (immagine OPPURE video, non entrambi).
  pending/caption_ig.txt   (caption per Instagram, carosello completo)
  pending/caption_fb.txt   (caption per Facebook, "carosello in prosa")

POST PROGRAMMATI: ogni sottocartella pending/<nome>/ e' un post (stesse regole di file) con in piu'
  pending/<nome>/post.json  es. {"publish_at": "2026-10-22 10:00"}   (ora italiana, Europe/Rome, CET/CEST)
Il cron (ogni 5 min) pubblica solo i post con publish_at gia' passato. Stato in <nome>/state.json
(committato dal workflow): un canale gia' pubblicato non viene mai rifatto. A fine successo la cartella
passa in published/. Senza publish_at un post in sottocartella parte solo con il lancio manuale.
Con DRY_RUN=1 nessuna chiamata Graph API e nessuna modifica ai file. FAKE_NOW="YYYY-MM-DD HH:MM" (ora
italiana) simula l'ora corrente nei test.

Facoltativo: pending/fb-cover.png = copertina solo per Facebook (non entra nel carosello Instagram).
Se non c'è, per Facebook si usa la prima immagine (non video) in ordine alfabetico
(deve essere la variante cover senza "Scorri ->", vedi reference_carosello_instagram_template).
"""
import json
import os
import shutil
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import notify, one_line

try:
    import requests
except ImportError:  # serve solo per le chiamate reali (non in DRY_RUN)
    requests = None

GRAPH = "https://graph.facebook.com/v21.0"
DRY_RUN = os.environ.get("DRY_RUN") == "1"
REPO = os.environ.get("GITHUB_REPOSITORY", "dry/run")
SHA = os.environ.get("GITHUB_SHA", "0" * 40)
IG_ID = os.environ.get("IG_BUSINESS_ACCOUNT_ID", "IG_DRY")
PAGE_ID = os.environ.get("PAGE_ID", "PAGE_DRY")
TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")
TZ = ZoneInfo("Europe/Rome")
MAX_ATTEMPTS = 3

PENDING_DIR = "pending"
PUBLISHED_DIR = "published"
IMAGE_EXT = (".webp", ".jpg", ".jpeg", ".png")
VIDEO_EXT = (".mp4", ".mov")
FB_COVER_PREFIX = "fb-cover"  # facoltativo: copertina solo per Facebook (non è una slide Instagram)


class PublishError(Exception):
    pass


def fail(msg):
    raise PublishError(msg)


_dry_counter = [0]


def raw_url(base, filename):
    return f"https://raw.githubusercontent.com/{REPO}/{SHA}/{base}/{filename}"


def graph_post(path, **params):
    if DRY_RUN:
        _dry_counter[0] += 1
        print(f"  [DRY-RUN] POST /{path} {sorted(k for k in params)}")
        return {"id": f"dry-{_dry_counter[0]}", "post_id": f"dry-{_dry_counter[0]}"}
    params["access_token"] = TOKEN
    resp = requests.post(f"{GRAPH}/{path}", data=params, timeout=30)
    data = resp.json()
    if "error" in data:
        fail(f"POST /{path} -> {data['error']}")
    return data


def graph_get(path, **params):
    params["access_token"] = TOKEN
    resp = requests.get(f"{GRAPH}/{path}", params=params, timeout=30)
    data = resp.json()
    if "error" in data:
        fail(f"GET /{path} -> {data['error']}")
    return data


def wait_until_finished(creation_id, timeout_s=120):
    if DRY_RUN:
        return
    waited = 0
    while waited < timeout_s:
        status = graph_get(creation_id, fields="status_code")["status_code"]
        if status == "FINISHED":
            return
        if status == "ERROR":
            fail(f"Container {creation_id} in errore durante il processing")
        time.sleep(5)
        waited += 5
    fail(f"Timeout in attesa del processing di {creation_id}")


def now_rome():
    fake = os.environ.get("FAKE_NOW")
    if fake:
        return datetime.fromisoformat(fake.replace("T", " ")).replace(tzinfo=TZ)
    return datetime.now(TZ)


def parse_publish_at(value):
    """Ora italiana (Europe/Rome). Se manca l'offset si assume l'ora locale italiana (CET/CEST)."""
    dt = datetime.fromisoformat(str(value).strip().replace("T", " "))
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def read_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def write_json(path, data):
    if DRY_RUN:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def publish_post(folder, base, state, save):
    """Pubblica il post in `folder` (URL raw sotto `base`). `state` tiene ig_media_id / fb_post_id;
    `save()` lo persiste su disco dopo ogni canale. Canali gia' pubblicati vengono saltati."""
    files = sorted(os.listdir(folder))
    images = sorted(
        f for f in files
        if f.lower().endswith(IMAGE_EXT + VIDEO_EXT) and not f.lower().startswith(FB_COVER_PREFIX)
    )
    if not images:
        fail(f"Nessuna immagine trovata in {folder}/")
    fb_cover = next((f for f in files if f.lower().startswith(FB_COVER_PREFIX)), None)
    cover = fb_cover or next((f for f in images if f.lower().endswith(IMAGE_EXT)), None)
    if cover is None:
        fail(f"Serve almeno un'immagine (copertina) in {folder}/")

    caption_ig_path = os.path.join(folder, "caption_ig.txt")
    caption_fb_path = os.path.join(folder, "caption_fb.txt")
    if not os.path.exists(caption_ig_path) or not os.path.exists(caption_fb_path):
        fail(f"Servono caption_ig.txt e caption_fb.txt in {folder}/")

    caption_ig = open(caption_ig_path, encoding="utf-8").read().strip()
    caption_fb = open(caption_fb_path, encoding="utf-8").read().strip()
    url = lambda f: raw_url(base, f)

    print(f"Immagini trovate ({len(images)}): {images}")

    # --- Instagram: carosello ---
    if state.get("ig_media_id"):
        print(f"Instagram gia' pubblicato ({state['ig_media_id']}), salto")
    else:
        if len(images) == 1:
            if images[0].lower().endswith(VIDEO_EXT):
                fail("Un post con un solo file deve essere un'immagine")
            creation = graph_post(f"{IG_ID}/media", image_url=url(images[0]), caption=caption_ig)
            ig_container_id = creation["id"]
        else:
            child_ids = []
            for img in images:
                if img.lower().endswith(VIDEO_EXT):
                    child = graph_post(
                        f"{IG_ID}/media",
                        media_type="VIDEO",
                        video_url=url(img),
                        is_carousel_item="true",
                    )
                    wait_until_finished(child["id"], timeout_s=300)
                else:
                    child = graph_post(f"{IG_ID}/media", image_url=url(img), is_carousel_item="true")
                child_ids.append(child["id"])
                print(f"  slide {img} -> container {child['id']}")

            container = graph_post(
                f"{IG_ID}/media",
                media_type="CAROUSEL",
                children=",".join(child_ids),
                caption=caption_ig,
            )
            ig_container_id = container["id"]

        wait_until_finished(ig_container_id)
        published = graph_post(f"{IG_ID}/media_publish", creation_id=ig_container_id)
        state["ig_media_id"] = published["id"]
        save()  # subito: se Facebook fallisce, al retry Instagram non si rifa'
        print(f"Instagram pubblicato: media id {published['id']}")

    # --- Facebook: solo la prima immagine (cover), caption in prosa ---
    if state.get("fb_post_id"):
        print(f"Facebook gia' pubblicato ({state['fb_post_id']}), salto")
    else:
        fb_post = graph_post(f"{PAGE_ID}/photos", url=url(cover), caption=caption_fb)
        state["fb_post_id"] = fb_post.get("post_id", fb_post.get("id"))
        save()
        print(f"Facebook pubblicato: post id {state['fb_post_id']}")


def post_title(folder, name):
    try:
        return str(read_json(os.path.join(folder, "post.json"), {}).get("title") or name)
    except Exception:
        return name


def channels_done(state):
    return " + ".join(c for c, k in (("Instagram", "ig_media_id"), ("Facebook", "fb_post_id")) if state.get(k)) or "nessuno"


def links(state):
    out = []
    try:
        if state.get("fb_post_id") and not DRY_RUN:
            out.append(f"Facebook: https://www.facebook.com/{state['fb_post_id']}")
        if state.get("ig_media_id") and not DRY_RUN:
            out.append("Instagram: " + graph_get(state["ig_media_id"], fields="permalink").get("permalink", ""))
    except Exception:
        pass
    return ("\n" + "\n".join(out)) if out else ""


def notify_ok(title, state):
    notify(f"Pubblicato: {title}\nCanali: {channels_done(state)}{links(state)}\nOra: {now_rome():%d/%m/%Y %H:%M}")


def notify_error(title, state, err, attempt):
    """Un solo messaggio per tentativo fallito; l'ultimo dice che il post e' marcato failed."""
    missing = [n for n, k in (("Instagram", "ig_media_id"), ("Facebook", "fb_post_id")) if not state.get(k)]
    msg = (f"PROBLEMA pubblicazione: {title}\nCanale in errore: {' + '.join(missing)}"
           f" (gia' ok: {channels_done(state)})\nErrore: {one_line(err)}\nTentativo {attempt}/{MAX_ATTEMPTS}")
    if attempt >= MAX_ATTEMPTS:
        msg += f"\nIl post e' marcato failed ({now_rome():%d/%m/%Y %H:%M}): non riprovo piu', serve il tuo intervento."
    else:
        msg += "\nRiprovo al prossimo giro (circa 5 minuti)."
    notify(msg)


def run_flat():
    """Comportamento storico: file direttamente in pending/ (solo lancio manuale)."""
    if not os.path.isdir(PENDING_DIR):
        return
    has_images = any(
        f.lower().endswith(IMAGE_EXT + VIDEO_EXT) for f in os.listdir(PENDING_DIR)
        if os.path.isfile(os.path.join(PENDING_DIR, f))
    )
    if not has_images:
        print("Nessun post manuale in pending/ (file diretti)")
        return
    state_path = os.path.join(PENDING_DIR, "state.json")  # evita doppioni se un canale fallisce
    state = read_json(state_path, {})
    try:
        publish_post(PENDING_DIR, PENDING_DIR, state, lambda: write_json(state_path, state))
    except Exception as e:
        notify_error("post manuale", state, e, 1)
        raise
    notify_ok("post manuale", state)
    if not DRY_RUN:  # svuota pending/ (solo file diretti, le sottocartelle programmate restano)
        for f in os.listdir(PENDING_DIR):
            fp = os.path.join(PENDING_DIR, f)
            if os.path.isfile(fp) and f not in (".gitkeep", "README.md"):
                os.remove(fp)
    print("Post manuale pubblicato")


def run_scheduled():
    """Pubblica i post in pending/<nome>/ con publish_at passato. Ritorna True se tutto ok."""
    if not os.path.isdir(PENDING_DIR):
        return True
    now = now_rome()
    print(f"Ora italiana: {now:%Y-%m-%d %H:%M %Z}")
    ok = True
    for name in sorted(os.listdir(PENDING_DIR)):
        folder = os.path.join(PENDING_DIR, name)
        meta_path = os.path.join(folder, "post.json")
        if not os.path.isdir(folder) or not os.path.exists(meta_path):
            continue
        try:
            meta = read_json(meta_path, {})
            if not meta.get("publish_at"):
                print(f"[{name}] senza publish_at: solo manuale, salto")
                continue
            when = parse_publish_at(meta["publish_at"])
        except Exception as e:  # JSON o data non valida: non pubblicare mai alla cieca
            print(f"[{name}] post.json non valido ({e}), salto", file=sys.stderr)
            ok = False
            continue
        if when > now:
            print(f"[{name}] programmato per {when:%Y-%m-%d %H:%M %Z}: non ancora")
            continue
        state_path = os.path.join(folder, "state.json")
        state = read_json(state_path, {})
        if state.get("status") == "failed":
            print(f"[{name}] bloccato dopo {state.get('attempts')} tentativi falliti, salto (vedi state.json)")
            ok = False
            continue
        print(f"[{name}] DUE (publish_at {when:%Y-%m-%d %H:%M %Z}), pubblico")
        save = lambda: write_json(state_path, state)
        state["attempts"] = state.get("attempts", 0) + 1
        save()
        try:
            publish_post(folder, f"{PENDING_DIR}/{name}", state, save)
        except Exception as e:
            state["last_error"] = str(e)[:500]
            if state["attempts"] >= MAX_ATTEMPTS:
                state["status"] = "failed"
            save()
            print(f"[{name}] ERRORE: {e}", file=sys.stderr)
            notify_error(post_title(folder, name), state, e, state["attempts"])
            ok = False
            continue
        state["status"] = "published"
        state["published_at"] = now.isoformat()
        save()
        notify_ok(post_title(folder, name), state)
        if not DRY_RUN:
            os.makedirs(PUBLISHED_DIR, exist_ok=True)
            shutil.move(folder, os.path.join(PUBLISHED_DIR, name))
        print(f"[{name}] OK -> {PUBLISHED_DIR}/{name}")
    return ok


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"  # all (manuale) | scheduled (cron)
    ok = True
    if mode == "all":
        try:
            run_flat()
        except PublishError as e:
            print(f"ERRORE: {e}", file=sys.stderr)
            ok = False
    ok = run_scheduled() and ok
    print("OK" if ok else "TERMINATO CON ERRORI")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
