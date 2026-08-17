#!/usr/bin/env python3
"""
spotify_auth.py - eenmalige OAuth op de Mac, zodat de badge daarna alleen nog
een refresh token nodig heeft. Standaardbibliotheek, geen spotipy.

De badge is een publieke client: geen client secret, wel PKCE. Het refresh token
van Spotify verloopt niet vanzelf, dus je doet dit een keer en zet het resultaat
in de badge-config.

Eerst in het Spotify-dashboard (developer.spotify.com/dashboard) een app maken:
  Redirect URI : http://127.0.0.1:8888/callback
                 (loopback op http mag, "localhost" wordt geweigerd)
  API          : Web API

Daarna:
    ./spotify_auth.py auth <client_id>
    ./spotify_auth.py playlists <client_id> <refresh_token>
    ./spotify_auth.py token <client_id> <refresh_token>

`playlists` schrijft ook playlists.json weg. Dat bestand kan als cache mee naar
de badge, zodat het scherm meteen gevuld is voor het netwerk antwoordt.
"""

import base64
import hashlib
import http.server
import json
import os
import sys
import urllib.parse
import urllib.request
import webbrowser

REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = "playlist-read-private playlist-read-collaborative user-read-private"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"


def b64url(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def api_get(path, token):
    req = urllib.request.Request(API + path,
                                 headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def auth(client_id):
    verifier = b64url(os.urandom(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())

    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT,
        "scope": SCOPES,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    })

    holder = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            holder.update({k: v[0] for k, v in params.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h2>Klaar. Je kan dit tabblad sluiten.</h2>".encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 8888), Handler)
    print("Browser opent. Log in en geef toestemming.")
    print(url)
    webbrowser.open(url)
    server.handle_request()
    server.server_close()

    if "error" in holder:
        raise SystemExit("Spotify gaf: " + holder["error"])
    if "code" not in holder:
        raise SystemExit("Geen code ontvangen.")

    tokens = post_form(TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": holder["code"],
        "redirect_uri": REDIRECT,
        "client_id": client_id,
        "code_verifier": verifier,
    })

    print()
    print("Zet dit in de badge-config (niet in git):")
    print("SPOTIFY_CLIENT_ID  =", repr(client_id))
    print("SPOTIFY_REFRESH    =", repr(tokens["refresh_token"]))
    return tokens


def refresh(client_id, refresh_token):
    """Precies deze call moet de badge ook doen. Antwoord is klein, het access
    token leeft een uur."""
    return post_form(TOKEN_URL, {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    })


def playlists(client_id, refresh_token):
    token = refresh(client_id, refresh_token)["access_token"]
    out = []
    path = "/me/playlists?limit=50"
    while path:
        page = api_get(path, token)
        for item in page["items"]:
            out.append({
                "naam": item["name"],
                "uri": item["uri"],
                "aantal": item["tracks"]["total"],
            })
        nxt = page.get("next")
        path = nxt[len(API):] if nxt else None
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd, client_id = argv[1], argv[2]

    if cmd == "auth":
        auth(client_id)
    elif cmd == "token":
        print(refresh(client_id, argv[3])["access_token"])
    elif cmd == "playlists":
        items = playlists(client_id, argv[3])
        for p in items:
            print("{0:<45} {1:>5}  {2}".format(p["naam"][:45], p["aantal"], p["uri"]))
        with open("playlists.json", "w") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=1)
        print("\n{0} playlists, ook weggeschreven naar playlists.json".format(len(items)))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
