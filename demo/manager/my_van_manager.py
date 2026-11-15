"""my-van-manager – „Mein Master“ für Interessenten.

- Anmeldung über login.ca-camping.de (OAuth 2, WP OAuth Server; /oauth/me liefert E-Mail)
- je Interessent eine Home-Assistant-Instanz aus dem Image my-van-ha (Docker), angelegt beim ersten Login
- Start beim Login, Stopp beim Logout bzw. nach Ruhezeit ohne offene Verbindung
- Weiterleitung (HTTP + WebSocket) zur Instanz; Home Assistant meldet den Interessenten per
  trusted_networks an (die Instanz vertraut nur dem Manager)
- Dashboards mit der E-Mail als Präfix (Camper, Camper Display, Camper Wall)

Alle Einstellungen kommen aus Umgebungsvariablen (siehe ``Settings``). Keine Secrets im Code.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
from aiohttp import WSMsgType, web

import my_van_mcp

log = logging.getLogger("my-van")
STATIC = Path(__file__).with_name("static")
HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "x-real-ip",
    "forwarded",
    "cookie",
}


@dataclass
class Settings:
    domain: str = os.environ.get("MYVAN_DOMAIN", "my-van.ca-camping.de")
    oauth_base: str = os.environ.get("MYVAN_OAUTH_BASE", "https://login.ca-camping.de")
    client_id: str = os.environ.get("MYVAN_OAUTH_CLIENT_ID", "")
    client_secret: str = os.environ.get("MYVAN_OAUTH_CLIENT_SECRET", "")
    session_secret: bytes = os.environ.get("MYVAN_SESSION_SECRET", "").encode()
    image: str = os.environ.get("MYVAN_HA_IMAGE", "ghcr.io/consulting-kleimanns/my-van-ha:latest")
    data_dir: Path = Path(os.environ.get("MYVAN_DATA_DIR", "/data"))
    host_data_dir: str = os.environ.get("MYVAN_HOST_DATA_DIR", "/opt/my-van/instances")
    network: str = os.environ.get("MYVAN_NETWORK", "my-van")
    manager_ip: str = os.environ.get("MYVAN_MANAGER_IP", "172.31.60.2")
    memory: int = int(os.environ.get("MYVAN_MEMORY_MB", "650")) * 1024 * 1024
    idle_min: float = float(os.environ.get("MYVAN_IDLE_MINUTES", "30"))
    max_running: int = int(os.environ.get("MYVAN_MAX_RUNNING", "4"))
    session_days: int = int(os.environ.get("MYVAN_SESSION_DAYS", "14"))
    # Zugang: E-Mail-Domains (Team) immer, sonst Mitglied einer dieser Nextcloud-Gruppen
    allowed_domains: tuple[str, ...] = tuple(
        d.strip().lower()
        for d in os.environ.get("MYVAN_ALLOWED_DOMAINS", "ca-camping.de").split(",")
        if d.strip()
    )
    allowed_groups: tuple[str, ...] = tuple(
        g.strip()
        for g in os.environ.get("MYVAN_ALLOWED_GROUPS", "Interessent").split(",")
        if g.strip()
    )
    nc_url: str = os.environ.get("MYVAN_NC_URL", "https://nc.ca-camping.de")
    nc_user: str = os.environ.get("MYVAN_NC_USER", "")
    nc_app_password: str = os.environ.get("MYVAN_NC_APP_PASSWORD", "")
    # Nextcloud-Container für occ (Konten anlegen verlangt über OCS eine Passwortbestätigung)
    nc_container: str = os.environ.get("MYVAN_NC_CONTAINER", "nc-ca-camping-app")

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}"


S = Settings()


def slugify(email: str) -> str:
    """E-Mail -> Präfix für Container, Ordner und Dashboards (nur a–z, 0–9, Bindestrich)."""
    slug = re.sub(r"[^a-z0-9]+", "-", email.lower()).strip("-")
    return slug[:48].strip("-")


# --- Sitzung (signiertes Cookie) ----------------------------------------------------------------


def _sign(data: bytes) -> str:
    return hmac.new(S.session_secret, data, hashlib.sha256).hexdigest()


def make_session(email: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"e": email, "x": int(time.time()) + S.session_days * 86400}).encode()
    )
    return f"{payload.decode()}.{_sign(payload)}"


def read_session(request: web.Request) -> str | None:
    raw = request.cookies.get("myvan")
    if not raw or "." not in raw:
        return None
    payload, sig = raw.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(payload.encode())):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except ValueError:
        return None
    return data["e"] if data.get("x", 0) > time.time() else None


# --- Zugang ------------------------------------------------------------------------------------

_ACCESS: dict[str, tuple[float, str | None]] = {}


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


async def resolve(login: str) -> str | None:
    """Ordnet eine Login-E-Mail dem Konto in nc.ca-camping.de zu.

    Das Login-Konto auf login.ca-camping.de trägt die E-Mail des Nextcloud-Kontos; dessen
    Kennung kann anders lauten (Kennung name@ca-camping.de, E-Mail privat@beispiel.de).
    Zurück kommt die Kennung, unter der der Master geführt wird, oder None ohne Zugang.
    Zugang: Team-Domain (Kennung oder E-Mail) oder Mitglied einer freigegebenen Gruppe.
    """
    login = login.strip().lower()
    hit = _ACCESS.get(login)
    if hit and hit[0] > time.time():
        return hit[1]
    if not (S.nc_user and S.nc_app_password):
        return login if _domain(login) in S.allowed_domains else None
    best: tuple[int, str] | None = None
    try:
        data = await _ocs("GET", "/cloud/users/details", params={"search": login, "limit": "50"})
        users = data.get("users", {}) or {}
        if isinstance(users, list):
            users = {}
        for uid, user in users.items():
            uid_l = (user.get("id") or uid or "").lower()
            mail = (user.get("email") or "").lower()
            if login not in (uid_l, mail) or user.get("enabled") is False:
                continue
            ident = uid_l if "@" in uid_l else mail
            if not ident:
                continue
            if _domain(uid_l) in S.allowed_domains or _domain(mail) in S.allowed_domains:
                rank = 2
            elif set(user.get("groups", []) or []) & set(S.allowed_groups):
                rank = 1
            else:
                continue
            if best is None or rank > best[0]:
                best = (rank, ident)
    except (aiohttp.ClientError, KeyError, ValueError, asyncio.TimeoutError, web.HTTPException) as err:
        log.warning("Zugangspruefung fehlgeschlagen: %s", err)
        if hit:
            return hit[1]
        return login if _domain(login) in S.allowed_domains else None
    ident = best[1] if best else None
    if ident is None and _domain(login) in S.allowed_domains:
        ident = login  # Team-Konto, das (noch) nicht in Nextcloud steht
    _ACCESS[login] = (time.time() + 300, ident)
    return ident


async def allowed(ident: str) -> bool:
    return await resolve(ident) is not None


def is_team(email: str | None) -> bool:
    return bool(email) and email.rsplit("@", 1)[-1] in S.allowed_domains


async def _ocs(method: str, path: str, **kw) -> dict:
    auth = aiohttp.BasicAuth(S.nc_user, S.nc_app_password)
    hdr = {"OCS-APIRequest": "true", "Accept": "application/json"}
    async with M.http.request(
        method, S.nc_url + "/ocs/v2.php" + path, auth=auth, headers=hdr, **kw
    ) as r:
        data = await r.json(content_type=None)
    meta = data.get("ocs", {}).get("meta", {})
    if meta.get("statuscode") not in (100, 200):
        raise web.HTTPBadRequest(text=meta.get("message") or "Nextcloud hat die Anfrage abgelehnt")
    return data["ocs"]["data"]


# --- Docker -----------------------------------------------------------------------------------


class Docker:
    """Schlanker Client für die Docker-Engine-API über den Unix-Socket."""

    def __init__(self) -> None:
        self._s = aiohttp.ClientSession(
            connector=aiohttp.UnixConnector(path="/var/run/docker.sock"), base_url="http://docker"
        )

    async def call(self, method: str, path: str, **kw):
        async with self._s.request(method, "/v1.43" + path, **kw) as r:
            text = await r.text()
            if r.status >= 400 and r.status != 304:
                raise RuntimeError(f"Docker {method} {path}: {r.status} {text[:200]}")
            try:
                return json.loads(text) if text else None
            except ValueError:
                return None

    async def inspect(self, name: str) -> dict | None:
        try:
            return await self.call("GET", f"/containers/{name}/json")
        except RuntimeError:
            return None

    async def image_id(self, image: str) -> str | None:
        try:
            return (await self.call("GET", f"/images/{image}/json"))["Id"]
        except RuntimeError:
            return None

    async def pull(self, image: str) -> None:
        repo, _, tag = image.rpartition(":")
        await self.call("POST", "/images/create?" + urlencode({"fromImage": repo, "tag": tag}))

    async def exec(self, container: str, cmd: list[str], env: list[str] | None = None,
                   user: str = "") -> tuple[int, str]:
        """Befehl in einem Container ausführen; liefert (Exit-Code, Ausgabe)."""
        ex = await self.call(
            "POST",
            f"/containers/{container}/exec",
            json={"Cmd": cmd, "Env": env or [], "User": user, "AttachStdout": True, "AttachStderr": True},
        )
        async with self._s.post(
            f"/v1.43/exec/{ex['Id']}/start", json={"Detach": False, "Tty": False}
        ) as r:
            raw = await r.read()
        out, i = [], 0
        while i + 8 <= len(raw):  # gemultiplexter Strom: 8 Byte Kopf je Block
            n = int.from_bytes(raw[i + 4 : i + 8], "big")
            out.append(raw[i + 8 : i + 8 + n])
            i += 8 + n
        info = await self.call("GET", f"/exec/{ex['Id']}/json")
        return info.get("ExitCode", 1), b"".join(out).decode(errors="replace").strip()

    async def running(self) -> list[dict]:
        flt = json.dumps({"label": ["my-van.instance"], "status": ["running"]})
        return await self.call("GET", "/containers/json?" + urlencode({"filters": flt})) or []


# --- Instanzen --------------------------------------------------------------------------------


@dataclass
class Instance:
    email: str
    slug: str = ""
    last_seen: float = field(default_factory=time.time)
    sockets: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self.slug = slugify(self.email)

    @property
    def name(self) -> str:
        return f"my-van-{self.slug}"

    @property
    def dir(self) -> Path:
        return S.data_dir / self.slug

    @property
    def url(self) -> str:
        return f"http://{self.name}:8123"

    @property
    def meta_file(self) -> Path:
        return self.dir / "manager.json"

    def meta(self) -> dict:
        return json.loads(self.meta_file.read_text()) if self.meta_file.exists() else {}

    def save_meta(self, data: dict) -> None:
        self.meta_file.write_text(json.dumps(data, indent=1))
        self.meta_file.chmod(0o600)

    @property
    def dashboard(self) -> str:
        return f"{self.slug}-camper"


class Manager:
    def __init__(self) -> None:
        self.docker = Docker()
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_read=None))
        self.proxy = aiohttp.ClientSession(
            auto_decompress=False, timeout=aiohttp.ClientTimeout(total=None, sock_read=None)
        )
        self.instances: dict[str, Instance] = {}

    def get(self, email: str) -> Instance:
        if email not in self.instances:
            self.instances[email] = Instance(email)
        return self.instances[email]

    # Container -------------------------------------------------------------------------------

    async def ensure_running(self, inst: Instance) -> None:
        """Container anlegen bzw. starten; bei neuem Image neu erstellen (Daten bleiben)."""
        async with inst.lock:
            info = await self.docker.inspect(inst.name)
            image_id = await self.docker.image_id(S.image)
            if info and image_id and info["Image"] != image_id:
                log.info("%s: neues Image – Container wird neu erstellt", inst.name)
                await self.docker.call("DELETE", f"/containers/{inst.name}?force=true")
                info = None
            if info is None:
                await self._create(inst)
                info = await self.docker.inspect(inst.name)
            if not info["State"]["Running"]:
                await self._make_room()
                await self.docker.call("POST", f"/containers/{inst.name}/start")
            await self._wait_ready(inst)
            if not inst.meta().get("provisioned"):
                await self._provision(inst)
            else:
                try:
                    await self._sync_views(inst)
                except Exception as err:  # noqa: BLE001 – Start nicht blockieren
                    log.warning("%s: Ansichten nicht aktualisiert: %s", inst.name, err)

    async def stop(self, inst: Instance) -> None:
        async with inst.lock:
            info = await self.docker.inspect(inst.name)
            if info and info["State"]["Running"]:
                log.info("%s: wird gestoppt", inst.name)
                await self.docker.call("POST", f"/containers/{inst.name}/stop?t=20")

    async def _create(self, inst: Instance) -> None:
        (inst.dir / "config").mkdir(parents=True, exist_ok=True)
        body = {
            "Image": S.image,
            "Env": ["TZ=Europe/Berlin"],
            "Labels": {"my-van.instance": inst.slug, "my-van.email": inst.email},
            "HostConfig": {
                "Binds": [f"{S.host_data_dir}/{inst.slug}/config:/config"],
                "Memory": S.memory,
                "RestartPolicy": {"Name": "no"},
                "NetworkMode": S.network,
            },
        }
        await self.docker.call(
            "POST", "/containers/create?" + urlencode({"name": inst.name}), json=body
        )

    async def _make_room(self) -> None:
        running = await self.docker.running()
        if len(running) < S.max_running:
            return
        by_slug = {i.slug: i for i in self.instances.values()}
        running.sort(
            key=lambda c: by_slug.get(c["Labels"]["my-van.instance"], Instance("x")).last_seen
        )
        oldest = running[0]["Names"][0].lstrip("/")
        log.info("Höchstzahl laufender Instanzen erreicht – stoppe %s", oldest)
        await self.docker.call("POST", f"/containers/{oldest}/stop?t=20")

    async def _wait_ready(self, inst: Instance, timeout: float = 180) -> None:
        end = time.time() + timeout
        while time.time() < end:
            try:
                async with self.http.get(
                    inst.url + "/manifest.json", timeout=aiohttp.ClientTimeout(total=3)
                ) as r:
                    if r.status == 200:
                        return
            except aiohttp.ClientError:
                pass
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(2)
        raise RuntimeError(f"{inst.name} startet nicht")

    # Home Assistant einrichten ---------------------------------------------------------------

    async def _api(self, inst: Instance, method: str, path: str, token: str, **kw):
        async with self.http.request(
            method, inst.url + path, headers={"Authorization": f"Bearer {token}"}, **kw
        ) as r:
            text = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"HA {method} {path}: {r.status} {text[:200]}")
            return json.loads(text) if text else None

    async def _ws(self, inst: Instance, token: str, messages: list[dict]) -> list[dict]:
        out = []
        async with self.http.ws_connect(inst.url + "/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            if (await ws.receive_json()).get("type") != "auth_ok":
                raise RuntimeError("WebSocket-Anmeldung fehlgeschlagen")
            for i, msg in enumerate(messages, 1):
                await ws.send_json({"id": i, **msg})
                while True:
                    res = await ws.receive_json()
                    if res.get("id") == i and res.get("type") == "result":
                        if not res.get("success"):
                            raise RuntimeError(f"WS {msg['type']}: {res.get('error')}")
                        out.append(res.get("result"))
                        break
        return out

    async def _flow(
        self, inst: Instance, token: str, handler: str, steps: list[dict], options: bool = False
    ) -> dict:
        base = (
            "/api/config/config_entries/options/flow"
            if options
            else "/api/config/config_entries/flow"
        )
        res = await self._api(inst, "POST", base, token, json={"handler": handler})
        for data in steps:
            if res.get("type") in ("create_entry", "abort"):
                break
            res = await self._api(inst, "POST", f"{base}/{res['flow_id']}", token, json=data)
        return res

    async def _provision(self, inst: Instance) -> None:
        """Erstes Einrichten: Onboarding, Benutzer, Simulation, Energiemanager, Dashboards, SSO."""
        log.info("%s: wird eingerichtet", inst.name)
        meta = inst.meta()
        client = S.base_url + "/"
        if "token" not in meta:
            pw = secrets.token_urlsafe(24)
            async with self.http.post(
                inst.url + "/api/onboarding/users",
                json={
                    "client_id": client,
                    "name": "CA Camping",
                    "username": "ca-admin",
                    "password": pw,
                    "language": "de",
                },
            ) as r:
                code = (await r.json())["auth_code"]
            async with self.http.post(
                inst.url + "/auth/token",
                data={"grant_type": "authorization_code", "code": code, "client_id": client},
            ) as r:
                access = (await r.json())["access_token"]
            for step, body in (
                ("core_config", {}),
                ("analytics", {"preferences": {}}),
                ("integration", {"client_id": client, "redirect_uri": client}),
            ):
                try:
                    await self._api(inst, "POST", f"/api/onboarding/{step}", access, json=body)
                except RuntimeError as err:
                    log.warning("Onboarding %s: %s", step, err)
            (llat,) = await self._ws(
                inst,
                access,
                [
                    {
                        "type": "auth/long_lived_access_token",
                        "client_name": "my-van-manager",
                        "lifespan": 3650,
                    }
                ],
            )
            meta.update({"token": llat, "admin_password": pw})
            inst.save_meta(meta)
        token = meta["token"]

        if "user_id" not in meta:
            (res,) = await self._ws(
                inst,
                token,
                [
                    {
                        "type": "config/auth/create",
                        "name": inst.email,
                        "group_ids": ["system-users"],
                        "local_only": False,
                    }
                ],
            )
            meta["user_id"] = res["user"]["id"]
            inst.save_meta(meta)

        # Simulation und Energiemanager
        await self._flow(inst, token, "ca_camper_sim", [{}])
        await asyncio.sleep(3)
        entry = await self._flow(inst, token, "ca_camper", [CA_CAMPER_SOURCES])
        if entry.get("type") == "create_entry":
            entry_id = entry["result"]["entry_id"]
            for load in CA_CAMPER_LOADS:
                await self._flow(
                    inst, token, entry_id, [{"next_step_id": "add_load"}, load], options=True
                )

        # Dashboards mit E-Mail-Präfix
        seed = inst.dir / "config" / "my-van" / "seed"
        msgs = []
        for name, title, icon in (
            ("camper", "Camper", "mdi:van-utility"),
            ("camper-display", "Camper Display", "mdi:monitor-dashboard"),
            ("camper-wall", "Camper Wall", "mdi:tablet-dashboard"),
        ):
            cfg = json.loads(
                (seed / f"{name}.json").read_text().replace("__DASH_CAMPER__", inst.dashboard)
            )
            url_path = f"{inst.slug}-{name}"
            msgs.append(
                {
                    "type": "lovelace/dashboards/create",
                    "url_path": url_path,
                    "title": f"{title} · {inst.email}",
                    "icon": icon,
                    "show_in_sidebar": True,
                    "require_admin": False,
                    "mode": "storage",
                }
            )
            msgs.append({"type": "lovelace/config/save", "url_path": url_path, "config": cfg})
        await self._ws(inst, token, msgs)

        # SSO: Instanz vertraut nur dem Manager und meldet ihn als diesen Interessenten an
        (inst.dir / "config" / "myvan_auth.yaml").write_text(
            "# Verwaltet vom my-van-manager\n"
            "- type: trusted_networks\n"
            f"  trusted_networks: [{S.manager_ip}/32]\n"
            "  trusted_users:\n"
            f"    {S.manager_ip}/32: [{meta['user_id']}]\n"
            "  allow_bypass_login: true\n"
            "- type: homeassistant\n"
        )
        meta["provisioned"] = True
        inst.save_meta(meta)
        await self.docker.call("POST", f"/containers/{inst.name}/restart?t=20")
        await asyncio.sleep(5)
        await self._wait_ready(inst)
        log.info("%s: fertig eingerichtet", inst.name)

    # Ansichten aus dem Image nachziehen -------------------------------------------------------

    SYNC_VIEWS = {"camper": ("umgebung",), "camper-display": ("umgebung",)}

    async def _sync_views(self, inst: Instance) -> None:
        """Bringt einzelne Ansichten der Standard-Dashboards auf den Stand des Images.

        Nur die in SYNC_VIEWS genannten Ansichten, und nur wenn sie sich im Image geändert
        haben; alles andere, was der Interessent angepasst hat, bleibt unberührt.
        """
        meta = inst.meta()
        done = meta.setdefault("views", {})
        seed = inst.dir / "config" / "my-van" / "seed"
        for name, paths in self.SYNC_VIEWS.items():
            f = seed / f"{name}.json"
            if not f.exists():
                continue
            cfg = json.loads(f.read_text().replace("__DASH_CAMPER__", inst.dashboard))
            new = {v.get("path"): v for v in cfg.get("views", []) if v.get("path") in paths}
            digest = hashlib.sha256(json.dumps(new, sort_keys=True).encode()).hexdigest()[:16]
            if done.get(name) == digest:
                continue
            url_path = f"{inst.slug}-{name}"
            (cur,) = await self._ws(inst, meta["token"], [{"type": "lovelace/config", "url_path": url_path}])
            views = cur.get("views", [])
            have = {v.get("path") for v in views}
            views = [new.get(v.get("path"), v) for v in views] + [
                v for p, v in new.items() if p not in have
            ]
            await self._ws(
                inst, meta["token"],
                [{"type": "lovelace/config/save", "url_path": url_path, "config": {**cur, "views": views}}],
            )
            done[name] = digest
            inst.save_meta(meta)
            log.info("%s: Ansicht %s in %s aktualisiert", inst.name, ", ".join(new), name)

    # Ruhezeit --------------------------------------------------------------------------------

    async def idle_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            for inst in list(self.instances.values()):
                if inst.sockets == 0 and time.time() - inst.last_seen > S.idle_min * 60:
                    try:
                        await self.stop(inst)
                    except RuntimeError as err:
                        log.warning("Stoppen fehlgeschlagen: %s", err)


# Standardkonfiguration des Energiemanagers für die Demo (Entity-Vertrag, Musterwerte)
CA_CAMPER_SOURCES = {
    "landstrom_entity": "binary_sensor.landstrom",
    "v2l_entity": "binary_sensor.v2l",
    "generator_soc_entity": "sensor.hausbatterie_ladestand",
    "generator_min_soc": 20,
    "limit_landstrom_w": 3600,
    "limit_v2l_w": 3700,
    "limit_generator_w": 4800,
    "release_margin_w": 200,
    "release_delay_off_s": 2,
    "release_delay_on_s": 30,
    "charge_switch_entity": "switch.ac_03_generator_1",
    "v2l_charge_start_soc": 30,
    "v2l_charge_stop_soc": 80,
}


def _load(name: str, key: str, bus: str, nominal: float, flexible: bool = False) -> dict:
    return {
        "name": name,
        "switch_entity": f"switch.{key}",
        "power_entity": f"sensor.{key}_leistung",
        "bus": bus,
        "nominal_w": nominal,
        "flexible": flexible,
    }


CA_CAMPER_LOADS = [
    _load("Kochfeld", "ac_01_induktion", "primaer", 3000),
    _load("Boiler-Heizstab", "ac_02_boiler_heizstab", "primaer", 1000, True),
    _load("Laden Hausbatterie 1", "ac_03_generator_1", "primaer", 1000, True),
    _load("Laden Hausbatterie 2", "ac_03_generator_2", "primaer", 1000, True),
    _load("Dusche", "ac_05_dusche", "komfort", 2400),
    _load("Kühlschrank", "ac_06_kuehlschrank", "komfort", 70),
    _load("Steckdose Heck", "ac_07_steckdose_heck", "komfort", 0),
    _load("Steckdose Trennwand", "ac_08_steckdose_trennwand", "komfort", 0),
]


# --- Web --------------------------------------------------------------------------------------

M: Manager


def page(name: str, **values: str) -> web.Response:
    html = (STATIC / name).read_text()
    for k, v in values.items():
        html = html.replace("{{" + k + "}}", v)
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})


async def auth_login(request: web.Request) -> web.Response:
    state = secrets.token_urlsafe(16)
    url = (
        S.oauth_base
        + "/oauth/authorize?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": S.client_id,
                "redirect_uri": S.base_url + "/auth/callback",
                "state": state,
            }
        )
    )
    resp = web.HTTPFound(url)
    resp.set_cookie("myvan_state", state, max_age=600, secure=True, httponly=True, samesite="Lax")
    raise resp


async def auth_callback(request: web.Request) -> web.Response:
    if request.query.get("state") != request.cookies.get("myvan_state"):
        raise web.HTTPBadRequest(text="Anmeldung abgelaufen – bitte noch einmal versuchen.")
    async with M.http.post(
        S.oauth_base + "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": request.query.get("code", ""),
            "redirect_uri": S.base_url + "/auth/callback",
            "client_id": S.client_id,
            "client_secret": S.client_secret,
        },
    ) as r:
        tok = await r.json(content_type=None)
    async with M.http.get(
        S.oauth_base + "/oauth/me",
        headers={"Authorization": f"Bearer {tok.get('access_token', '')}"},
    ) as r:
        me = await r.json(content_type=None)
    email = (me.get("email") or me.get("user_email") or "").strip().lower()
    if "@" not in email:
        raise web.HTTPForbidden(text="Anmeldung fehlgeschlagen.")
    ident = await resolve(email)
    if not ident:
        log.info("Kein Zugang: %s", slugify(email))
        return page("denied.html", EMAIL=email)
    log.info("Anmeldung: %s -> %s", slugify(email), slugify(ident))
    email = ident
    nxt = request.cookies.get("myvan_next", "")
    resp = web.HTTPFound(nxt if nxt.startswith("/mcp/authorize?") else "/")
    resp.del_cookie("myvan_next")
    resp.set_cookie(
        "myvan",
        make_session(email),
        max_age=S.session_days * 86400,
        secure=True,
        httponly=True,
        samesite="Lax",
    )
    resp.del_cookie("myvan_state")
    raise resp


async def auth_logout(request: web.Request) -> web.Response:
    email = read_session(request)
    if email:
        asyncio.create_task(M.stop(M.get(email)))
    resp = web.HTTPFound("/")
    resp.del_cookie("myvan")
    raise resp


async def status(request: web.Request) -> web.Response:
    email = read_session(request)
    if not email or not await allowed(email):
        return web.json_response({"state": "anonymous"})
    inst = M.get(email)
    info = await M.docker.inspect(inst.name)
    ready = bool(
        info
        and info["State"]["Running"]
        and inst.meta().get("provisioned")
        and not inst.lock.locked()
    )
    if not ready and not inst.lock.locked():
        asyncio.create_task(_start(inst))
    return web.json_response(
        {"state": "ready" if ready else "starting", "dashboard": inst.dashboard, "email": email}
    )


async def _start(inst: Instance) -> None:
    try:
        await M.ensure_running(inst)
    except Exception:  # noqa: BLE001 – im Log sichtbar, Seite fragt erneut
        log.exception("%s: Start fehlgeschlagen", inst.name)


async def handler(request: web.Request) -> web.StreamResponse:
    email = read_session(request)
    path = request.path
    if path.startswith("/_my-van/"):
        f = STATIC / path.removeprefix("/_my-van/")
        if f.is_file() and STATIC in f.resolve().parents:
            return web.FileResponse(f, headers={"Cache-Control": "no-cache"})
        raise web.HTTPNotFound()
    if not email:
        return page("landing.html")
    if not await allowed(email):
        resp = page("denied.html", EMAIL=email)
        resp.del_cookie("myvan")
        return resp
    inst = M.get(email)
    inst.last_seen = time.time()
    if path == "/" and request.method == "GET":
        admin = '<a class="out" href="/admin">Interessenten verwalten</a>' if is_team(email) else ""
        return page("app.html", EMAIL=email, DASH=inst.dashboard, ADMIN=admin)
    info = await M.docker.inspect(inst.name)
    if not (info and info["State"]["Running"]) or inst.lock.locked():
        if not inst.lock.locked():
            asyncio.create_task(_start(inst))
        return page("starting.html")
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await _proxy_ws(request, inst)
    return await _proxy_http(request, inst)


async def _proxy_http(request: web.Request, inst: Instance) -> web.StreamResponse:
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
    async with M.proxy.request(
        request.method,
        inst.url + request.path_qs,
        headers=headers,
        data=request.content if request.body_exists else None,
        allow_redirects=False,
    ) as r:
        resp = web.StreamResponse(
            status=r.status,
            headers={k: v for k, v in r.headers.items() if k.lower() not in HOP_HEADERS},
        )
        await resp.prepare(request)
        async for chunk in r.content.iter_any():
            await resp.write(chunk)
        await resp.write_eof()
        return resp


async def _proxy_ws(request: web.Request, inst: Instance) -> web.WebSocketResponse:
    client = web.WebSocketResponse(max_msg_size=0, heartbeat=30)
    await client.prepare(request)
    inst.sockets += 1
    try:
        async with M.http.ws_connect(inst.url + request.path_qs, max_msg_size=0) as backend:

            async def pump(src, dst) -> None:
                async for msg in src:
                    inst.last_seen = time.time()
                    if msg.type == WSMsgType.TEXT:
                        await dst.send_str(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await dst.send_bytes(msg.data)
                    else:
                        break

            tasks = [
                asyncio.create_task(pump(client, backend)),
                asyncio.create_task(pump(backend, client)),
            ]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in tasks:
                t.cancel()
    finally:
        inst.sockets -= 1
        inst.last_seen = time.time()
    return client


# --- Admin: Interessenten anlegen (nur Team) ------------------------------------------------------


def _team(request: web.Request) -> str:
    email = read_session(request)
    if not is_team(email):
        raise web.HTTPForbidden(text="Nur für Konten von ca-camping.de")
    return email


async def admin_page(request: web.Request) -> web.Response:
    email = read_session(request)
    if not email:
        raise web.HTTPFound("/auth/login")
    _team(request)
    return page("admin.html", EMAIL=email, GROUP=S.allowed_groups[0])


async def admin_list(request: web.Request) -> web.Response:
    _team(request)
    users = (await _ocs("GET", f"/cloud/groups/{S.allowed_groups[0]}/users/details")).get(
        "users", {}
    ) or {}
    running = {c["Labels"].get("my-van.email") for c in await M.docker.running()}
    out = []
    for uid, u in users.items():
        mail = (u.get("email") or "").lower()
        ident = uid.lower() if "@" in uid else mail
        inst = Instance(ident) if ident else None
        meta = inst.meta() if inst and inst.meta_file.exists() else {}
        out.append(
            {
                "uid": uid,
                "name": u.get("displayname") or uid,
                "email": mail,
                "enabled": u.get("enabled", True),
                "lastLogin": u.get("lastLogin", 0),
                "instance": bool(meta.get("provisioned")),
                "running": ident in running,
            }
        )
    out.sort(key=lambda x: x["name"].lower())
    return web.json_response(out)


async def admin_create(request: web.Request) -> web.Response:
    _team(request)
    if request.headers.get("X-My-Van") != "1":
        raise web.HTTPForbidden()
    data = await request.json()
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", email) or not name:
        raise web.HTTPBadRequest(text="Name und gültige E-Mail angeben")
    found = (await _ocs("GET", "/cloud/users/details", params={"search": email})).get(
        "users", {}
    ) or {}
    uid = next(
        (
            k
            for k, u in found.items()
            if email in ((u.get("id") or k).lower(), (u.get("email") or "").lower())
        ),
        None,
    )
    group = S.allowed_groups[0]
    if uid is None:
        uid = email
        code, out = await M.docker.exec(
            S.nc_container,
            ["php", "occ", "user:add", "--password-from-env", f"--display-name={name}",
             f"--group={group}", f"--email={email}", uid],
            env=[f"OC_PASS={secrets.token_urlsafe(24)}"],
            user="www-data",
        )
        if code != 0:
            log.warning("occ user:add: %s", out[-300:])
            raise web.HTTPBadRequest(text=f"Konto konnte nicht angelegt werden: {out[-200:]}")
        await M.docker.exec(S.nc_container, ["php", "occ", "user:setting", uid, "core", "lang", "de"],
                            user="www-data")
        result = "angelegt"
    else:
        code, out = await M.docker.exec(
            S.nc_container, ["php", "occ", "group:adduser", group, uid], user="www-data"
        )
        if code != 0:
            raise web.HTTPBadRequest(text=f"Gruppe konnte nicht zugeordnet werden: {out[-200:]}")
        result = "der Gruppe zugeordnet"
    _ACCESS.clear()
    log.info("Admin %s: Interessent %s", slugify(_team(request)), result)
    return web.json_response({"ok": True, "result": result})


async def on_startup(app: web.Application) -> None:
    global M
    M = Manager()
    if not (S.client_id and S.client_secret and len(S.session_secret) >= 32):
        raise SystemExit(
            "MYVAN_OAUTH_CLIENT_ID/-SECRET und MYVAN_SESSION_SECRET (≥ 32 Zeichen) setzen"
        )
    try:
        await M.docker.pull(S.image)
    except RuntimeError as err:
        log.warning("Image-Pull: %s", err)
    # laufende Instanzen nach einem Neustart des Managers wieder in die Ruhezeit-Überwachung nehmen
    for c in await M.docker.running():
        if email := c.get("Labels", {}).get("my-van.email"):
            M.get(email)
    app["idle"] = asyncio.create_task(M.idle_loop())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.on_startup.append(on_startup)
    app.router.add_get("/auth/login", auth_login)
    app.router.add_get("/auth/callback", auth_callback)
    app.router.add_get("/auth/logout", auth_logout)
    app.router.add_get("/_my-van/status", status)
    app.router.add_get("/admin", admin_page)
    app.router.add_get("/admin/api/interessenten", admin_list)
    app.router.add_post("/admin/api/interessenten", admin_create)
    my_van_mcp.setup(app, sys.modules[__name__])
    app.router.add_route("*", "/{tail:.*}", handler)
    web.run_app(app, host="0.0.0.0", port=8080, access_log=None)


if __name__ == "__main__":
    main()
