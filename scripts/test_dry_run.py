#!/usr/bin/env python3
"""
Dry-run: verifica l'intera catena Graph API SENZA rendere nulla visibile.

- Instagram: crea i container del carosello e aspetta che siano FINISHED,
  ma non chiama mai media_publish (quello è l'unico passo che pubblica davvero).
- Facebook: crea una foto con published=false (non appare nel feed), la verifica,
  poi la cancella.
"""
import os
import sys
import time
import requests

GRAPH = "https://graph.facebook.com/v21.0"
REPO = os.environ["GITHUB_REPOSITORY"]
SHA = os.environ["GITHUB_SHA"]
IG_ID = os.environ["IG_BUSINESS_ACCOUNT_ID"]
PAGE_ID = os.environ["PAGE_ID"]
TOKEN = os.environ["PAGE_ACCESS_TOKEN"]

TEST_IMAGES = ["dry-run-1.png", "dry-run-2.png"]


def raw_url(filename):
    return f"https://raw.githubusercontent.com/{REPO}/{SHA}/test-assets/{filename}"


def fail(msg):
    print(f"ERRORE: {msg}", file=sys.stderr)
    sys.exit(1)


def graph_post(path, **params):
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


def graph_delete(path, **params):
    params["access_token"] = TOKEN
    resp = requests.delete(f"{GRAPH}/{path}", data=params, timeout=30)
    return resp.json()


def wait_until_finished(creation_id, timeout_s=120):
    waited = 0
    while waited < timeout_s:
        status = graph_get(creation_id, fields="status_code")["status_code"]
        print(f"  status {creation_id}: {status}")
        if status == "FINISHED":
            return
        if status == "ERROR":
            fail(f"Container {creation_id} in errore durante il processing")
        time.sleep(5)
        waited += 5
    fail(f"Timeout in attesa del processing di {creation_id}")


def test_instagram():
    print("--- Instagram: creazione container carosello (NON pubblico) ---")
    child_ids = []
    for img in TEST_IMAGES:
        child = graph_post(f"{IG_ID}/media", image_url=raw_url(img), is_carousel_item="true")
        child_ids.append(child["id"])
        print(f"  slide {img} -> container {child['id']}")

    container = graph_post(
        f"{IG_ID}/media",
        media_type="CAROUSEL",
        children=",".join(child_ids),
        caption="[DRY RUN - mai pubblicato]",
    )
    print(f"  container carosello: {container['id']}")
    wait_until_finished(container["id"])
    print(f"OK Instagram: container {container['id']} pronto (FINISHED), media_publish NON chiamato.")


def test_facebook():
    print("--- Facebook: foto non pubblicata (published=false) ---")
    photo = graph_post(
        f"{PAGE_ID}/photos",
        url=raw_url(TEST_IMAGES[0]),
        caption="[DRY RUN - foto di test, verrà cancellata]",
        published="false",
    )
    photo_id = photo["id"]
    print(f"  foto creata (non pubblica): {photo_id}")

    check = graph_get(photo_id, fields="id,is_published")
    print(f"  verifica: {check}")

    graph_delete(photo_id)
    print(f"OK Facebook: foto {photo_id} creata, verificata e cancellata.")


def main():
    test_instagram()
    test_facebook()
    print("\nDRY RUN COMPLETATO: nessun contenuto è stato reso pubblico.")


if __name__ == "__main__":
    main()
