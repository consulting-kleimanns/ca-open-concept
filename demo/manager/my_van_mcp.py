"""MCP-Zugang für „Mein Master“ – Interessenten passen ihren Master mit Claude an.

Endpunkt ``https://<domain>/mcp`` (Streamable HTTP, JSON-Antworten). Anmeldung per OAuth 2.1
mit PKCE und dynamischer Client-Registrierung; die Identität kommt aus der Sitzung des Managers
(login.ca-camping.de). Tokens sind HMAC-signiert und zustandslos.

Freigegeben (alles mit der E-Mail bzw. ihrem Kürzel als Präfix):
  Dashboards, Automationen, Szenen, Skripte, Helfer anlegen, ändern, löschen; Geräte bedienen;
  Zustände lesen; Wünsche an CA Camping schicken.
Gesperrt: Integrationen, Apps, YAML, Benutzer, System, fremde Einträge, Dienste außerhalb der
Freigabeliste.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime
from types import ModuleType
from urllib.parse import urlencode, urlparse

from aiohttp import web

log = logging.getLogger("my-van.mcp")
core: ModuleType  # my_van_manager, gesetzt in setup()

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
REDIRECT_HOSTS = tuple(
    h.strip().lower()
    for h in os.environ.get("MYVAN_MCP_REDIRECT_HOSTS", "claude.ai,claude.com").split(",")
    if h.strip()
)
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400
BOARD_TITLE = os.environ.get("MYVAN_DECK_BOARD", "Mein E-Camper")

# Geräte, die bedient und in Szenen gesetzt werden dürfen
DEVICE_DOMAINS = {
    "light", "switch", "climate", "select", "number", "button", "text", "fan", "cover",
    "media_player", "water_heater", "input_boolean", "input_number", "input_select",
    "input_text", "input_datetime", "input_button", "counter", "timer", "scene", "script",
    "automation",
}
# Dienste, die Automationen und Skripte aufrufen dürfen
SERVICE_DOMAINS = DEVICE_DOMAINS | {"notify", "persistent_notification"}
SERVICE_EXTRA = {"homeassistant.turn_on", "homeassistant.turn_off", "homeassistant.toggle"}
BLOCKED_SERVICES = {"reload", "remove", "delete", "purge", "restart", "stop", "install"}
HELPER_TYPES = (
    "input_boolean", "input_number", "input_select", "input_text", "input_datetime",
    "input_button", "counter", "timer",
)
BASE_DASHBOARDS = ("camper", "camper-display", "camper-wall")
HIDDEN_DOMAINS = {"update", "person", "zone", "sun", "conversation", "tts", "event", "stt",
                  "wake_word", "assist_satellite", "todo", "tag", "backup"}

INSTRUCTIONS = """Du hilfst einem Interessenten von CA Camping, seinen künftigen Camper „Mein Master“ \
(Renault Master E-Tech, vollelektrisch) in Home Assistant einzurichten. Die Instanz ist eine \
Simulation; alles, was hier entsteht, wird bei der Auslieferung ins echte Fahrzeug übernommen.

So arbeitest du:
- Sprich Deutsch, einfach und ohne Fachjargon. Erkläre kurz, was du anlegst.
- Lies zuerst mit mein_master_status die Geräte und mit dashboard_lesen das Dashboard „camper“ \
(Präfix siehe Status), bevor du etwas baust. Nutze nur vorhandene entity_ids.
- Dashboards: Sections-Ansicht, Karten im Stil der vorhandenen Dashboards (custom:bubble-card ist \
installiert). Es gibt drei Oberflächen: Smartphone (camper), 15″-Touchdisplay am Kleiderschrank \
(camper-display) und Shelly Wall Display 4″ am Einstieg (camper-wall). Ändere die drei \
Standard-Dashboards nur, wenn der Interessent das ausdrücklich will – sonst lege ein neues an.
- Namen bekommen automatisch die E-Mail des Interessenten als Präfix; gib nur den Kurznamen an.
- Integrationen, Apps, YAML, Benutzer und Systemeinstellungen sind gesperrt. Wenn der Interessent \
so etwas braucht oder etwas technisch nicht geht, lege mit wunsch_an_ca_camping einen Wunsch an.
- Energie: Landstrom, V2L aus dem Fahrzeug und zwei Hausbatterien versorgen den Camper; der \
Energiemanager gibt Verbraucher (Kochfeld, Boiler, Dusche …) nach verfügbarer Leistung frei.
"""


# --- Tokens --------------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(kind: str, payload: str) -> str:
    return _b64(
        hmac.new(core.S.session_secret, f"mcp|{kind}|{payload}".encode(), hashlib.sha256).digest()
    )


def pack(kind: str, data: dict, ttl: int) -> str:
    payload = _b64(json.dumps({**data, "x": int(time.time()) + ttl}, separators=(",", ":")).encode())
    return f"{payload}.{_mac(kind, payload)}"


def unpack(kind: str, token: str) -> dict | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _mac(kind, payload)):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    return data if data.get("x", 0) > time.time() else None


_USED_CODES: dict[str, float] = {}


def _redirect_ok(uri: str) -> bool:
    try:
        u = urlparse(uri)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme == "http" and host in ("localhost", "127.0.0.1"):
        return True  # lokale Clients (Claude Desktop/Code)
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in REDIRECT_HOSTS)


# --- OAuth ---------------------------------------------------------------------------------


def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(
        data, status=status, headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"}
    )


async def protected_resource(request: web.Request) -> web.Response:
    base = core.S.base_url
    return _json(
        {
            "resource": base + "/mcp",
            "authorization_servers": [base],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["mein-master"],
            "resource_name": "CA Camping – Mein Master",
        }
    )


async def auth_server(request: web.Request) -> web.Response:
    base = core.S.base_url
    return _json(
        {
            "issuer": base,
            "authorization_endpoint": base + "/mcp/authorize",
            "token_endpoint": base + "/mcp/token",
            "registration_endpoint": base + "/mcp/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": ["mein-master"],
        }
    )


async def register(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except ValueError:
        return _json({"error": "invalid_client_metadata"}, 400)
    uris = body.get("redirect_uris") or []
    if not uris or not isinstance(uris, list) or not all(isinstance(u, str) and _redirect_ok(u) for u in uris):
        return _json(
            {"error": "invalid_redirect_uri", "error_description": "Rücksprungadresse nicht erlaubt"}, 400
        )
    name = str(body.get("client_name") or "MCP-Client")[:80]
    client_id = pack("client", {"r": uris, "n": name}, 10 * 365 * 86400)
    return _json(
        {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": name,
            "redirect_uris": uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
        201,
    )


def _consent(req: str, client: str, email: str) -> web.Response:
    return core.page("mcp-consent.html", REQ=req, CLIENT=_esc(client), EMAIL=_esc(email))


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


async def authorize(request: web.Request) -> web.Response:
    q = request.query if request.method == "GET" else await request.post()
    if request.method == "POST":
        if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            raise web.HTTPForbidden(text="Ungültige Anfrage")
        params = unpack("req", q.get("req", ""))
        if not params:
            raise web.HTTPBadRequest(text="Anfrage abgelaufen – bitte in Claude neu verbinden.")
    else:
        params = {k: q.get(k, "") for k in ("client_id", "redirect_uri", "code_challenge",
                                             "code_challenge_method", "state", "response_type")}
    client = unpack("client", params.get("client_id", ""))
    if not client or params.get("redirect_uri") not in client.get("r", []):
        raise web.HTTPBadRequest(text="Unbekannter Client oder Rücksprungadresse")
    if params.get("response_type") != "code" or params.get("code_challenge_method") != "S256" or not params.get("code_challenge"):
        raise web.HTTPBadRequest(text="PKCE (S256) erforderlich")

    email = core.read_session(request)
    if not email:
        resp = web.HTTPFound("/auth/login")
        resp.set_cookie("myvan_next", request.path_qs, max_age=600, secure=True, httponly=True, samesite="Lax")
        raise resp
    if not await core.allowed(email):
        return core.page("denied.html", EMAIL=email)

    if request.method == "GET" or q.get("ok") != "1":
        if request.method == "POST":  # abgelehnt
            sep = "&" if "?" in params["redirect_uri"] else "?"
            raise web.HTTPFound(
                params["redirect_uri"] + sep + urlencode({"error": "access_denied", "state": params.get("state", "")})
            )
        return _consent(pack("req", {**params, "e": email}, 600), client.get("n", "Claude"), email)

    if params.get("e") != email:
        raise web.HTTPForbidden(text="Sitzung hat sich geändert – bitte neu verbinden.")
    code = pack(
        "code",
        {
            "e": email,
            "c": hashlib.sha256(params["client_id"].encode()).hexdigest()[:32],
            "r": params["redirect_uri"],
            "ch": params["code_challenge"],
            "j": secrets.token_urlsafe(12),
        },
        300,
    )
    log.info("MCP verbunden: %s (%s)", core.slugify(email), client.get("n"))
    sep = "&" if "?" in params["redirect_uri"] else "?"
    raise web.HTTPFound(
        params["redirect_uri"]
        + sep
        + urlencode({"code": code, "state": params.get("state", ""), "iss": core.S.base_url})
    )


def _tokens(email: str) -> dict:
    return {
        "access_token": pack("access", {"e": email}, ACCESS_TTL),
        "token_type": "Bearer",
        "expires_in": ACCESS_TTL,
        "refresh_token": pack("refresh", {"e": email, "j": secrets.token_urlsafe(6)}, REFRESH_TTL),
        "scope": "mein-master",
    }


async def token(request: web.Request) -> web.Response:
    f = await request.post()
    grant = f.get("grant_type")
    now = time.time()
    for k, exp in list(_USED_CODES.items()):
        if exp < now:
            _USED_CODES.pop(k, None)
    if grant == "authorization_code":
        data = unpack("code", f.get("code", ""))
        if not data or data["j"] in _USED_CODES:
            return _json({"error": "invalid_grant"}, 400)
        if data["r"] != f.get("redirect_uri") or data["c"] != hashlib.sha256(
            (f.get("client_id") or "").encode()
        ).hexdigest()[:32]:
            return _json({"error": "invalid_grant"}, 400)
        verifier = f.get("code_verifier") or ""
        if _b64(hashlib.sha256(verifier.encode()).digest()) != data["ch"]:
            return _json({"error": "invalid_grant", "error_description": "PKCE"}, 400)
        _USED_CODES[data["j"]] = data["x"]
    elif grant == "refresh_token":
        data = unpack("refresh", f.get("refresh_token", ""))
        if not data:
            return _json({"error": "invalid_grant"}, 400)
    else:
        return _json({"error": "unsupported_grant_type"}, 400)
    if not await core.allowed(data["e"]):
        return _json({"error": "invalid_grant", "error_description": "kein Zugang"}, 400)
    return _json(_tokens(data["e"]))


# --- Werkzeuge -----------------------------------------------------------------------------


class ToolError(Exception):
    pass


def _short(name: str) -> str:
    return core.slugify(name)[:40].strip("-") or "eigen"


class Ctx:
    def __init__(self, email: str) -> None:
        self.email = email
        self.inst = core.M.get(email)
        self.slug = self.inst.slug
        self.key = self.slug.replace("-", "_")

    def label(self, name: str) -> str:
        name = name.strip()
        return name if name.lower().startswith(self.email) else f"{self.email} · {name}"

    def short(self, name: str) -> str:
        s = _short(name)
        return s[len(self.slug) + 1 :] if s.startswith(self.slug + "-") else s

    async def ready(self) -> None:
        inst = self.inst
        inst.last_seen = time.time()
        for _ in range(45):
            info = await core.M.docker.inspect(inst.name)
            if info and info["State"]["Running"] and inst.meta().get("provisioned") and not inst.lock.locked():
                return
            if not inst.lock.locked():
                asyncio.create_task(core._start(inst))
            await asyncio.sleep(2)
        raise ToolError("Dein Master startet gerade. Bitte in einer Minute noch einmal versuchen.")

    async def api(self, method: str, path: str, **kw):
        try:
            return await core.M._api(self.inst, method, path, self.inst.meta()["token"], **kw)
        except RuntimeError as err:
            raise ToolError(str(err)) from err

    async def ws(self, msg: dict):
        try:
            (res,) = await core.M._ws(self.inst, self.inst.meta()["token"], [msg])
        except RuntimeError as err:
            raise ToolError(str(err)) from err
        return res


def _check_services(node, path: str = "") -> None:
    """Prüft rekursiv alle Dienstaufrufe einer Automation oder eines Skripts."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("service", "action") and isinstance(v, str):
                if "{" in v:
                    raise ToolError(f"Dienst als Vorlage ({v}) ist nicht erlaubt")
                if "." not in v:
                    continue
                dom, svc = v.split(".", 1)
                if v not in SERVICE_EXTRA and (dom not in SERVICE_DOMAINS or svc in BLOCKED_SERVICES):
                    raise ToolError(
                        f"Dienst {v} ist im Demo-Modus gesperrt. Erlaubt sind Geräte, Szenen, "
                        "Skripte, Helfer und Benachrichtigungen."
                    )
            _check_services(v, f"{path}.{k}")
    elif isinstance(node, list):
        for item in node:
            _check_services(item, path)


async def t_status(c: Ctx, a: dict) -> str:
    states = await c.api("GET", "/api/states")
    such = (a.get("suche") or "").lower()
    lines = []
    for s in sorted(states, key=lambda s: s["entity_id"]):
        eid = s["entity_id"]
        if eid.split(".", 1)[0] in HIDDEN_DOMAINS:
            continue
        attr = s.get("attributes", {})
        name = attr.get("friendly_name", "")
        if such and such not in eid.lower() and such not in name.lower():
            continue
        unit = attr.get("unit_of_measurement", "")
        extra = ""
        if "options" in attr and eid.split(".")[0] in ("select", "input_select"):
            extra = f"  Optionen: {', '.join(map(str, attr['options']))}"
        lines.append(f"{eid} | {name} | {s['state']} {unit}".rstrip() + extra)
    head = (
        f"Mein Master von {c.email}\nPräfix für eigene Einträge: {c.slug}\n"
        f"Standard-Dashboards: {', '.join(f'{c.slug}-{b}' for b in BASE_DASHBOARDS)}\n\n"
    )
    return head + ("\n".join(lines[:400]) or "Keine passenden Geräte gefunden.")


async def t_bedienen(c: Ctx, a: dict) -> str:
    eid = a.get("entity_id", "")
    aktion = a.get("aktion", "")
    dom = eid.split(".", 1)[0]
    if dom not in DEVICE_DOMAINS or not aktion or "." in aktion or aktion in BLOCKED_SERVICES:
        raise ToolError(f"{eid} / {aktion} kann hier nicht bedient werden")
    states = {s["entity_id"] for s in await c.api("GET", "/api/states")}
    if eid not in states:
        raise ToolError(f"{eid} gibt es nicht")
    daten = {k: v for k, v in (a.get("daten") or {}).items() if k not in ("entity_id", "target")}
    await c.api("POST", f"/api/services/{dom}/{aktion}", json={"entity_id": eid, **daten})
    await asyncio.sleep(1)
    st = await c.api("GET", f"/api/states/{eid}")
    return f"{eid}: {aktion} ausgeführt, Zustand jetzt {st.get('state')}"


async def _dashboards(c: Ctx) -> list[dict]:
    return await c.ws({"type": "lovelace/dashboards/list"}) or []


async def t_dash_list(c: Ctx, a: dict) -> str:
    out = []
    for d in await _dashboards(c):
        own = d["url_path"].startswith(c.slug + "-")
        out.append(f"{d['url_path']} | {d.get('title')} | {'eigen' if own else 'nur lesen'}")
    return "\n".join(out) or "Keine Dashboards"


async def t_dash_read(c: Ctx, a: dict) -> str:
    path = a.get("url_path") or None
    if path and path not in {d["url_path"] for d in await _dashboards(c)}:
        raise ToolError(f"Dashboard {path} gibt es nicht")
    cfg = await c.ws({"type": "lovelace/config", "url_path": path, "force": True})
    return json.dumps(cfg, ensure_ascii=False, indent=1)


async def t_dash_save(c: Ctx, a: dict) -> str:
    cfg = a.get("config")
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except ValueError as err:
            raise ToolError("config ist kein gültiges JSON") from err
    if not isinstance(cfg, dict) or not (isinstance(cfg.get("views"), list) or "strategy" in cfg):
        raise ToolError("config braucht eine Liste views")
    if len(json.dumps(cfg)) > 600_000:
        raise ToolError("Dashboard ist zu groß")
    short = c.short(a.get("name", ""))
    url_path = f"{c.slug}-{short}"
    title = c.label(a.get("titel") or a.get("name") or short)
    existing = {d["url_path"]: d for d in await _dashboards(c)}
    if url_path not in existing:
        await c.ws(
            {
                "type": "lovelace/dashboards/create",
                "url_path": url_path,
                "title": title,
                "icon": a.get("icon") or "mdi:view-dashboard",
                "show_in_sidebar": True,
                "require_admin": False,
                "mode": "storage",
            }
        )
        neu = "angelegt"
    else:
        if a.get("titel"):
            await c.ws(
                {"type": "lovelace/dashboards/update", "dashboard_id": existing[url_path]["id"], "title": title}
            )
        neu = "aktualisiert"
    await c.ws({"type": "lovelace/config/save", "url_path": url_path, "config": cfg})
    log.info("MCP %s: Dashboard %s %s", c.slug, url_path, neu)
    return f"Dashboard „{title}“ {neu}. Adresse: {core.S.base_url}/{url_path}"


async def t_automation(c: Ctx, a: dict) -> str:
    cfg = copy.deepcopy(a.get("config") or {})
    if not isinstance(cfg, dict):
        raise ToolError("config muss ein Objekt sein")
    _check_services(cfg)
    oid = f"{c.slug}-{c.short(a.get('name', ''))}"
    cfg.pop("id", None)
    cfg["alias"] = c.label(a.get("name", oid))
    cfg.setdefault("description", "Angelegt mit Claude über Mein Master")
    await c.api("POST", f"/api/config/automation/config/{oid}", json=cfg)
    return f"Automation „{cfg['alias']}“ gespeichert (id {oid})."


async def t_szene(c: Ctx, a: dict) -> str:
    entities = a.get("entities") or {}
    if not isinstance(entities, dict) or not entities:
        raise ToolError("entities: Objekt entity_id → Zustand bzw. Attribute")
    for eid in entities:
        if eid.split(".", 1)[0] not in DEVICE_DOMAINS - {"scene", "script", "automation"}:
            raise ToolError(f"{eid} darf nicht in eine Szene")
    oid = f"{c.slug}-{c.short(a.get('name', ''))}"
    name = c.label(a.get("name", oid))
    await c.api("POST", f"/api/config/scene/config/{oid}", json={"id": oid, "name": name, "entities": entities})
    return f"Szene „{name}“ gespeichert (id {oid})."


async def t_skript(c: Ctx, a: dict) -> str:
    cfg = copy.deepcopy(a.get("config") or {})
    if not isinstance(cfg, dict) or not cfg.get("sequence"):
        raise ToolError("config braucht eine sequence")
    _check_services(cfg)
    key = f"{c.key}_{c.short(a.get('name', '')).replace('-', '_')}"
    cfg["alias"] = c.label(a.get("name", key))
    await c.api("POST", f"/api/config/script/config/{key}", json=cfg)
    return f"Skript „{cfg['alias']}“ gespeichert (script.{key})."


async def t_helfer(c: Ctx, a: dict) -> str:
    art = a.get("art")
    if art not in HELPER_TYPES:
        raise ToolError(f"art muss eins von {', '.join(HELPER_TYPES)} sein")
    opts = {k: v for k, v in (a.get("optionen") or {}).items() if k not in ("type", "id", "name")}
    name = c.label(a.get("name", art))
    item = await c.ws({"type": f"{art}/create", "name": name, **opts})
    return f"Helfer „{name}“ angelegt ({art}.{item.get('id')})."


async def t_eigene(c: Ctx, a: dict) -> str:
    out = ["Dashboards:"]
    out += [f"  {d['url_path']} | {d.get('title')}" for d in await _dashboards(c) if d["url_path"].startswith(c.slug + "-")]
    states = await c.api("GET", "/api/states")
    for dom, titel in (("automation", "Automationen"), ("scene", "Szenen"), ("script", "Skripte")):
        out.append(f"{titel}:")
        for s in states:
            if not s["entity_id"].startswith(dom + "."):
                continue
            oid = str(s.get("attributes", {}).get("id", ""))
            mine = (
                s["entity_id"].startswith(f"script.{c.key}_")
                if dom == "script"
                else oid.startswith(c.slug + "-")
            )
            if mine:
                ref = s["entity_id"].split(".", 1)[1] if dom == "script" else oid
                out.append(f"  {ref} | {s['attributes'].get('friendly_name')} | {s['state']}")
    out.append("Helfer:")
    for art in HELPER_TYPES:
        for item in await c.ws({"type": f"{art}/list"}) or []:
            if str(item.get("name", "")).startswith(c.email):
                out.append(f"  {art}.{item['id']} | {item['name']}")
    return "\n".join(out)


async def t_loeschen(c: Ctx, a: dict) -> str:
    art, ref = a.get("art"), str(a.get("id") or "")
    if art == "dashboard":
        if not ref.startswith(c.slug + "-") or ref[len(c.slug) + 1 :] in BASE_DASHBOARDS:
            raise ToolError("Nur eigene Dashboards löschen; die drei Standard-Dashboards bleiben")
        d = next((d for d in await _dashboards(c) if d["url_path"] == ref), None)
        if not d:
            raise ToolError(f"{ref} gibt es nicht")
        await c.ws({"type": "lovelace/dashboards/delete", "dashboard_id": d["id"]})
    elif art in ("automation", "szene"):
        if not ref.startswith(c.slug + "-"):
            raise ToolError("Nur eigene Einträge löschen")
        await c.api("DELETE", f"/api/config/{'automation' if art == 'automation' else 'scene'}/config/{ref}")
    elif art == "skript":
        ref = ref.removeprefix("script.")
        if not ref.startswith(c.key + "_"):
            raise ToolError("Nur eigene Skripte löschen")
        await c.api("DELETE", f"/api/config/script/config/{ref}")
    elif art == "helfer":
        dom, _, oid = ref.partition(".")
        if dom not in HELPER_TYPES:
            raise ToolError("id als z. B. input_boolean.xyz angeben")
        item = next((i for i in await c.ws({"type": f"{dom}/list"}) or [] if i.get("id") == oid), None)
        if not item or not str(item.get("name", "")).startswith(c.email):
            raise ToolError("Nur eigene Helfer löschen")
        await c.ws({"type": f"{dom}/delete", f"{dom}_id": oid})
    else:
        raise ToolError("art: dashboard, automation, szene, skript oder helfer")
    return f"{art} {ref} gelöscht."


async def t_wunsch(c: Ctx, a: dict) -> str:
    return await wunsch(c.email, a.get("titel", ""), a.get("beschreibung", ""), "Claude")


async def wunsch(email: str, titel: str, text: str, quelle: str) -> str:
    titel = " ".join(titel.split())[:120]
    if not titel:
        raise ToolError("Titel fehlt")
    beschreibung = (text or "").strip()[:4000]
    beschreibung += f"\n\n_Eingereicht über {quelle} am {datetime.now():%d.%m.%Y %H:%M}_"
    inst = core.M.get(email)
    inst.dir.mkdir(parents=True, exist_ok=True)
    with (inst.dir / "wuensche.jsonl").open("a") as fh:
        fh.write(json.dumps({"t": int(time.time()), "titel": titel, "text": text, "quelle": quelle}, ensure_ascii=False) + "\n")
    try:
        card = await _deck_card(email, f"Wunsch: {titel}", beschreibung)
    except Exception as err:  # noqa: BLE001 – Wunsch ist lokal gespeichert
        log.warning("Deck-Karte für %s fehlgeschlagen: %s", core.slugify(email), err)
        card = False
    log.info("Wunsch von %s (%s): %s", core.slugify(email), quelle, "Deck" if card else "lokal")
    if card:
        return f"Danke! Dein Wunsch „{titel}“ steht jetzt in deinem Board „{BOARD_TITLE}“. Wir melden uns dort."
    return f"Danke! Dein Wunsch „{titel}“ ist bei CA Camping angekommen."


async def _deck_card(email: str, title: str, description: str) -> bool:
    S = core.S
    if not (S.nc_user and S.nc_app_password):
        return False
    import aiohttp

    auth = aiohttp.BasicAuth(S.nc_user, S.nc_app_password)
    hdr = {"OCS-APIRequest": "true", "Accept": "application/json", "Content-Type": "application/json"}
    base = S.nc_url + "/index.php/apps/deck/api/v1.0"

    async def deck(method: str, path: str, **kw):
        async with core.M.http.request(method, base + path, auth=auth, headers=hdr, **kw) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    boards = await deck("GET", "/boards", params={"details": "true"})
    board = next(
        (
            b
            for b in boards
            if b.get("title") == BOARD_TITLE
            and not b.get("archived")
            and not b.get("deletedAt")
            and any(
                (acl.get("participant") or {}).get("uid", "").lower() == email
                for acl in b.get("acl") or []
            )
        ),
        None,
    )
    if not board:
        return False
    stacks = sorted(await deck("GET", f"/boards/{board['id']}/stacks"), key=lambda s: (s.get("order", 0), s["id"]))
    if not stacks:
        return False
    sid = stacks[0]["id"]
    card = await deck(
        "POST", f"/boards/{board['id']}/stacks/{sid}/cards",
        data=json.dumps({"title": title, "type": "plain", "order": 0, "description": description}),
    )
    label = next((lab for lab in board.get("labels") or [] if lab.get("title") == "Wunsch"), None)
    if not label:
        label = await deck(
            "POST", f"/boards/{board['id']}/labels", data=json.dumps({"title": "Wunsch", "color": "8b5cf6"})
        )
    await deck(
        "PUT", f"/boards/{board['id']}/stacks/{sid}/cards/{card['id']}/assignLabel",
        data=json.dumps({"labelId": label["id"]}),
    )
    return True


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


S_STR = {"type": "string"}
TOOLS = {
    "mein_master_status": (
        t_status, "Zeigt alle Geräte und Sensoren des Masters mit aktuellem Zustand (entity_id | Name | Zustand). "
        "Mit suche lässt sich filtern, z. B. 'licht' oder 'batterie'.",
        _obj({"suche": {**S_STR, "description": "Suchbegriff (optional)"}}), True,
    ),
    "geraet_bedienen": (
        t_bedienen, "Bedient ein Gerät, z. B. Licht an (light/turn_on, daten {brightness_pct: 50}), "
        "Schalter aus, Heizung auf Temperatur (climate/set_temperature), Auswahl setzen (select/select_option).",
        _obj({"entity_id": S_STR, "aktion": {**S_STR, "description": "Dienstname ohne Domain, z. B. turn_on"},
              "daten": {"type": "object", "description": "weitere Felder für den Dienst"}}, ["entity_id", "aktion"]),
        False,
    ),
    "dashboards_auflisten": (t_dash_list, "Listet die Dashboards; eigene tragen das Präfix.", _obj({}), True),
    "dashboard_lesen": (
        t_dash_read, "Liest die Konfiguration eines Dashboards als JSON (url_path aus dashboards_auflisten).",
        _obj({"url_path": S_STR}, ["url_path"]), True,
    ),
    "dashboard_speichern": (
        t_dash_save, "Legt ein eigenes Dashboard an oder überschreibt es. name ist der Kurzname (z. B. 'abend'); "
        "Adresse und Titel bekommen automatisch das Präfix. config ist die vollständige Lovelace-Konfiguration "
        "mit views (am besten type: sections).",
        _obj({"name": S_STR, "titel": S_STR, "icon": {**S_STR, "description": "z. B. mdi:weather-night"},
              "config": {"type": "object"}}, ["name", "config"]), False,
    ),
    "automation_speichern": (
        t_automation, "Legt eine eigene Automation an oder ändert sie (gleicher name = ändern). config wie in "
        "Home Assistant: triggers, conditions, actions. Erlaubt sind Dienste für Geräte, Szenen, Skripte, Helfer, Hinweise.",
        _obj({"name": S_STR, "config": {"type": "object"}}, ["name", "config"]), False,
    ),
    "szene_speichern": (
        t_szene, "Legt eine eigene Szene an oder ändert sie. entities: {entity_id: Zustand oder {state, brightness, …}}.",
        _obj({"name": S_STR, "entities": {"type": "object"}}, ["name", "entities"]), False,
    ),
    "skript_speichern": (
        t_skript, "Legt ein eigenes Skript an oder ändert es. config mit sequence (Liste von Schritten).",
        _obj({"name": S_STR, "config": {"type": "object"}}, ["name", "config"]), False,
    ),
    "helfer_anlegen": (
        t_helfer, "Legt einen eigenen Helfer an, z. B. input_boolean 'Urlaubsmodus' oder input_number mit "
        "optionen {min, max, step, unit_of_measurement}.",
        _obj({"art": {"type": "string", "enum": list(HELPER_TYPES)}, "name": S_STR, "optionen": {"type": "object"}},
             ["art", "name"]), False,
    ),
    "eigene_eintraege": (t_eigene, "Listet alles, was der Interessent selbst angelegt hat.", _obj({}), True),
    "eintrag_loeschen": (
        t_loeschen, "Löscht einen eigenen Eintrag. art: dashboard (url_path), automation/szene (id), "
        "skript (script.…), helfer (z. B. input_boolean.…).",
        _obj({"art": {"type": "string", "enum": ["dashboard", "automation", "szene", "skript", "helfer"]}, "id": S_STR},
             ["art", "id"]), False,
    ),
    "wunsch_an_ca_camping": (
        t_wunsch, "Schickt einen Wunsch an das CA-Camping-Team (landet im Board „Mein E-Camper“), z. B. wenn etwas "
        "gebraucht wird, das hier gesperrt ist oder fehlt.",
        _obj({"titel": S_STR, "beschreibung": S_STR}, ["titel"]), False,
    ),
}


# --- MCP-Endpunkt --------------------------------------------------------------------------


def _unauth() -> web.Response:
    return web.json_response(
        {"error": "unauthorized"},
        status=401,
        headers={
            "WWW-Authenticate": f'Bearer resource_metadata="{core.S.base_url}/.well-known/oauth-protected-resource"'
        },
    )


async def mcp(request: web.Request) -> web.StreamResponse:
    if request.method == "GET":
        return web.Response(status=405, headers={"Allow": "POST"})
    if request.method == "DELETE":
        return web.Response(status=204)
    auth = request.headers.get("Authorization", "")
    data = unpack("access", auth[7:]) if auth.lower().startswith("bearer ") else None
    if not data:
        return _unauth()
    email = data["e"]
    if not await core.allowed(email):
        return web.json_response({"error": "forbidden"}, status=403)
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
    batch = isinstance(body, list)
    out = [r for r in [await _rpc(email, m) for m in (body if batch else [body])] if r is not None]
    if not out:
        return web.Response(status=202)
    return web.json_response(out if batch else out[0])


async def _rpc(email: str, msg: dict) -> dict | None:
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if mid is None:
        return None  # Benachrichtigung
    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        ver = params.get("protocolVersion")
        return ok(
            {
                "protocolVersion": ver if ver in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "ca-camping-mein-master", "title": "CA Camping – Mein Master", "version": "1.0"},
                "instructions": INSTRUCTIONS,
            }
        )
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok(
            {
                "tools": [
                    {
                        "name": n,
                        "description": d,
                        "inputSchema": schema,
                        "annotations": {"readOnlyHint": ro, "destructiveHint": n == "eintrag_loeschen"},
                    }
                    for n, (_, d, schema, ro) in TOOLS.items()
                ]
            }
        )
    if method == "tools/call":
        name = params.get("name")
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unbekanntes Werkzeug {name}"}}
        fn = TOOLS[name][0]
        try:
            c = Ctx(email)
            if name != "wunsch_an_ca_camping":
                await c.ready()
            text, err = await fn(c, params.get("arguments") or {}), False
        except ToolError as e:
            text, err = str(e), True
        except Exception:  # noqa: BLE001
            log.exception("MCP %s: %s fehlgeschlagen", core.slugify(email), name)
            text, err = "Interner Fehler – bitte später noch einmal versuchen.", True
        return ok({"content": [{"type": "text", "text": text}], "isError": err})
    if method in ("resources/list", "prompts/list"):
        return ok({method.split("/")[0]: []})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Methode {method} unbekannt"}}


# --- Wunschfeld in „Mein Master“ -----------------------------------------------------------


async def wunsch_post(request: web.Request) -> web.Response:
    email = core.read_session(request)
    if not email or not await core.allowed(email) or request.headers.get("X-My-Van") != "1":
        raise web.HTTPForbidden()
    data = await request.json()
    try:
        text = await wunsch(email, data.get("titel", ""), data.get("beschreibung", ""), "Mein Master")
    except ToolError as err:
        raise web.HTTPBadRequest(text=str(err)) from err
    return web.json_response({"ok": True, "text": text})


def setup(app: web.Application, manager_module: ModuleType) -> None:
    global core
    core = manager_module
    r = app.router
    r.add_get("/.well-known/oauth-protected-resource", protected_resource)
    r.add_get("/.well-known/oauth-protected-resource/mcp", protected_resource)
    r.add_get("/.well-known/oauth-authorization-server", auth_server)
    r.add_post("/mcp/register", register)
    r.add_get("/mcp/authorize", authorize)
    r.add_post("/mcp/authorize", authorize)
    r.add_post("/mcp/token", token)
    r.add_route("*", "/mcp", mcp)
    r.add_post("/_my-van/wunsch", wunsch_post)
