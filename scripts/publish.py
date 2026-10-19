#!/usr/bin/env python3
"""
Pubblica il carosello in pending/ su Instagram e Facebook.

Convenzione cartella pending/:
  pending/01-xxx.webp, 02-xxx.webp, ... (ordine alfabetico = ordine slide)
  pending/caption_ig.txt   (caption per Instagram, carosello completo)
  pending/caption_fb.txt   (caption per Facebook, "carosello in prosa")

La prima immagine in ordine alfabetico è anche quella usata per il post Facebook
(deve essere la variante cover senza "Scorri ->", vedi reference_carosello_instagram_template).
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

PENDING_DIR = "pending"


def raw_url(filename):
    return f"https://raw.githubusercontent.com/{REPO}/{SHA}/{PENDING_DIR}/{filename}"


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


def wait_until_finished(creation_id, timeout_s=120):
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


def main():
    images = sorted(
        f for f in os.listdir(PENDING_DIR)
        if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png"))
    )
    if not images:
        fail(f"Nessuna immagine trovata in {PENDING_DIR}/")

    caption_ig_path = os.path.join(PENDING_DIR, "caption_ig.txt")
    caption_fb_path = os.path.join(PENDING_DIR, "caption_fb.txt")
    if not os.path.exists(caption_ig_path) or not os.path.exists(caption_fb_path):
        fail("Servono pending/caption_ig.txt e pending/caption_fb.txt")

    caption_ig = open(caption_ig_path, encoding="utf-8").read().strip()
    caption_fb = open(caption_fb_path, encoding="utf-8").read().strip()

    print(f"Immagini trovate ({len(images)}): {images}")

    # --- Instagram: carosello ---
    if len(images) == 1:
        creation = graph_post(f"{IG_ID}/media", image_url=raw_url(images[0]), caption=caption_ig)
        ig_container_id = creation["id"]
    else:
        child_ids = []
        for img in images:
            child = graph_post(f"{IG_ID}/media", image_url=raw_url(img), is_carousel_item="true")
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
    print(f"Instagram pubblicato: media id {published['id']}")

    # --- Facebook: solo la prima immagine (cover), caption in prosa ---
    fb_post = graph_post(f"{PAGE_ID}/photos", url=raw_url(images[0]), caption=caption_fb)
    print(f"Facebook pubblicato: post id {fb_post.get('post_id', fb_post.get('id'))}")

    print("OK")


if __name__ == "__main__":
    main()
