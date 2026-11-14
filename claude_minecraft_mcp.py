"""
Claude Minecraft MCP server
===========================
Praat met de Fabric mod "Claude Buddy" (poort 25599 op deze pc) en geeft Claude
tools om in Minecraft te lopen, kijken, hakken, bouwen en chatten.

Starten doet Claude Desktop zelf (zie LEESMIJ.md). Zelf testen kan met:
    python claude_minecraft_mcp.py --test
"""

import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

try:  # mcp versie 2 en nieuwer
    from mcp.server.mcpserver import MCPServer as FastMCP, Image
except ImportError:  # mcp versie 1
    from mcp.server.fastmcp import FastMCP, Image

MOD_URL = os.environ.get("CLAUDE_MC_URL", "http://127.0.0.1:25599/")
TTS_AAN = os.environ.get("CLAUDE_MC_TTS", "1") != "0"

SPEEL_UITLEG = """Je bestuurt je eigen poppetje ("Claude") in de Minecraft-wereld van de speler.

Zo speel je samen:
1. Begin met `roep` (je verschijnt bij de speler) en daarna `status`.
2. Roep `speel` aan en blijf daarna in een lus `wacht_op_gebeurtenis` aanroepen, zonder je beurt te beeindigen
   en zonder in de Claude-app te antwoorden: de speler leest alleen de Minecraft-chat. Daar komen chatberichten van de speler,
   gevaar-meldingen (monsters) en 'aangekomen'-meldingen binnen. Reageer en roep hem daarna weer aan.
   Stop pas met de lus als de speler zegt dat je mag stoppen.
3. Praat ALTIJD via `zeg` (dat komt in de Minecraft-chat en wordt hardop voorgelezen). Houd het kort.
4. In bijna elk antwoord zit een veld `gevaar` als er monsters in de buurt zijn. Check dat altijd:
   waarschuw de speler, loop weg of gebruik `val_aan`.
5. Gebruik `kijk` om een echte screenshot vanuit je ogen te krijgen, en `scan_blokken` /
   `bekijk_gebied` voor precieze coordinaten. Coordinaten zijn altijd hele blokken x y z.
6. Hakken en bouwen kan alleen dichtbij (ongeveer 5 blokken): loop er eerst heen met `loop_naar`.
   Je speelt volgens de regels van de wereld: je bouwt alleen met blokken die je zelf gehakt hebt (zie inventaris in `status`).
7. Richtingen: noord = -z, zuid = +z, oost = +x, west = -x.
   HONGER: in survival (niet op vredig, niet in creatief) krijg je honger van lopen, hakken en vechten. Kijk naar
   `honger` in status (20 = vol). Je eet vanzelf als je eten bij je hebt; heb je niks, zoek dan eten (jaag, bessen,
   brood maken) of vraag de speler. De speler zet jouw spelmodus met /gamemodeclaude c of s.
8. OVERLEVEN: je bent kwetsbaar en kunt dood (dan ben je je spullen kwijt en moet je `roep` doen). Houd `levens`
   in `status` in de gaten en `eet` als je laag zit. Hakken geeft echte drops die op de grond vallen: loop erheen,
   je pakt ze vanzelf op binnen 1,5 blok. Steen en ertsen geven alleen iets met de goede houweel. Volgorde om te
   beginnen: boom hakken -> `maak` planks -> crafting_table (neerzetten met `plaats`) -> stick -> wooden_pickaxe.
   Je kunt zwemmen (langzaam) en loopt vanzelf door houten deuren.
"""

mcp = FastMCP("claude-minecraft", instructions=SPEEL_UITLEG)


# ---------------------------------------------------------------- verbinding

# De mod draait op deze pc zelf, dus nooit via een proxy gaan.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def mod(cmd: str, timeout: float = 12.0, **args) -> dict:
    """Stuur 1 opdracht naar de mod en geef het antwoord terug."""
    payload = {"cmd": cmd}
    payload.update({k: v for k, v in args.items() if v is not None})
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(MOD_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        return {
            "ok": False,
            "fout": "Ik kan de Minecraft mod niet bereiken. Staat Minecraft aan, met de Claude Buddy mod, "
                    "en zit de speler IN een wereld? (" + str(e) + ")",
        }


def tekst(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------- stem (TTS)

import asyncio
import ctypes
from ctypes import wintypes
import tempfile
import uuid

_spreek_rij: "queue.Queue[str]" = queue.Queue(maxsize=32)
STEM = os.environ.get("CLAUDE_MC_STEM", "nl-NL-MaartenNeural")
TTS_LOG = os.path.join(tempfile.gettempdir(), "claude_minecraft_tts.log")


def _tts_log(bericht: str):
    """Alleen stderr en een logbestand; nooit het MCP-kanaal stdout."""
    regel = time.strftime("%Y-%m-%d %H:%M:%S") + " [TTS] " + bericht + "\n"
    try:
        sys.stderr.write(regel)
        sys.stderr.flush()
    except Exception:
        pass
    try:
        with open(TTS_LOG, "a", encoding="utf-8") as bestand:
            bestand.write(regel)
    except OSError:
        pass


def _speel_mp3(pad: str):
    """Alle MCI-aanroepen op dezelfde worker-thread, met foutcontrole."""
    winmm = ctypes.WinDLL("winmm")
    send = winmm.mciSendStringW
    send.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HWND]
    send.restype = wintypes.DWORD
    error_string = winmm.mciGetErrorStringW
    error_string.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.UINT]
    error_string.restype = wintypes.BOOL

    def opdracht(command: str):
        antwoord = ctypes.create_unicode_buffer(512)
        code = send(command, antwoord, len(antwoord), None)
        if code:
            fout = ctypes.create_unicode_buffer(512)
            error_string(code, fout, len(fout))
            raise RuntimeError(f"MCI {command.split()[0]}: {code}: {fout.value}")
        return antwoord.value

    pad = os.path.abspath(pad)
    if '"' in pad:
        raise ValueError("Ongeldig aanhalingsteken in audiopad")
    naam = "claude_tts_" + uuid.uuid4().hex
    opdracht(f'open "{pad}" type mpegvideo alias {naam}')
    try:
        opdracht(f"set {naam} time format milliseconds")
        duur = int(opdracht(f"status {naam} length"))
        if duur <= 0:
            raise RuntimeError("Windows meldt een lege mp3")
        _tts_log(f"Afspelen gestart: {duur} ms")
        opdracht(f"play {naam} from 0 wait")
        _tts_log("Afspelen voltooid volgens Windows")
    finally:
        try:
            opdracht(f"close {naam}")
        except Exception as fout:
            _tts_log(f"Afsluiten speler mislukt: {fout}")


# Alleen een werkelijk geinstalleerde Nederlandse stem als offline noodoplossing.
# Geen stille terugval op een Engelse stem.
_POWERSHELL_TTS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $nl = $s.GetInstalledVoices() | Where-Object {
    $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'nl'
  } | Select-Object -First 1
  if (-not $nl) { throw 'Geen Nederlandse Windows-stem geinstalleerd.' }
  $s.SelectVoice($nl.VoiceInfo.Name)
  $s.SetOutputToDefaultAudioDevice()
  $s.Speak($env:CLAUDE_TTS_TEKST)
} finally {
  $s.Dispose()
}
"""


def _powershell(script: str, extra_env: dict):
    env = dict(os.environ)
    env.update(extra_env)
    resultaat = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        env=env, timeout=90, capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if resultaat.returncode:
        detail = resultaat.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Nederlandse Windows-TTS mislukt: {detail[:1000]}")


def _maak_mp3(zin: str):
    """Online synthese met timeout; gedeeltelijke bestanden altijd opruimen."""
    import edge_tts
    if not STEM.lower().startswith(("nl-nl-", "nl-be-")):
        raise ValueError("CLAUDE_MC_STEM moet een Nederlandse stem zijn")
    fd, pad = tempfile.mkstemp(prefix="claude_tts_", suffix=".mp3")
    os.close(fd)  # Windows: bestand sluiten voordat edge-tts het opent.

    async def maak():
        await asyncio.wait_for(edge_tts.Communicate(zin, STEM).save(pad), timeout=45)

    try:
        asyncio.run(maak())
        grootte = os.path.getsize(pad)
        if grootte == 0:
            raise RuntimeError("edge-tts heeft een lege mp3 gemaakt")
        _tts_log(f"Mp3 gemaakt: stem={STEM}, bytes={grootte}")
        return pad
    except BaseException:
        try:
            os.remove(pad)
        except OSError:
            pass
        raise


def _spreek_werker():
    while True:
        zin = _spreek_rij.get()
        mp3 = None
        try:
            if sys.platform != "win32":
                raise RuntimeError("Deze audiospeler vereist Windows")
            try:
                mp3 = _maak_mp3(zin)
            except Exception as fout:
                _tts_log(f"Mp3 maken mislukt: {type(fout).__name__}: {fout}")
                _powershell(_POWERSHELL_TTS, {"CLAUDE_TTS_TEKST": zin})
            else:
                try:
                    _speel_mp3(mp3)
                except Exception as fout:
                    _tts_log(f"Mp3 afspelen mislukt: {type(fout).__name__}: {fout}")
                    _powershell(_POWERSHELL_TTS, {"CLAUDE_TTS_TEKST": zin})
        except Exception as fout:
            _tts_log(f"Spraak niet beschikbaar: {type(fout).__name__}: {fout}")
        finally:
            if mp3:
                try:
                    os.remove(mp3)
                except OSError as fout:
                    _tts_log(f"Tijdelijk bestand opruimen mislukt: {fout}")
            _spreek_rij.task_done()


threading.Thread(target=_spreek_werker, name="claude-tts", daemon=True).start()


def spreek(zin: str):
    """Niet-blokkerend, ook wanneer de begrensde wachtrij vol is."""
    if TTS_AAN and zin.strip():
        try:
            _spreek_rij.put_nowait(zin.strip())
        except queue.Full:
            pass  # Achterstallige spraak overslaan; MCP nooit laten wachten.


# ---------------------------------------------------------------- sensoren

@mcp.tool()
def status() -> str:
    """Alles wat je 'voelt': je positie, waar de spelers staan (afstand, richting, waar ze naar kijken,
    wat ze vasthouden), monsters in de buurt (gevaar), dieren, licht, regen, je inventaris en instellingen."""
    return tekst(mod("status"))


@mcp.tool()
def scan_blokken(straal: int = 6) -> str:
    """Tel alle blokken om je heen (straal 1-10) per soort, met de dichtstbijzijnde plek van elke soort.
    Handig om hout, ertsen, water of een kist te vinden."""
    return tekst(mod("scan", straal=straal))


@mcp.tool()
def blok_op(x: int, y: int, z: int) -> str:
    """Welk blok staat er op deze plek?"""
    return tekst(mod("blok", x=x, y=y, z=z))


@mcp.tool()
def bekijk_gebied(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> str:
    """Geef precies alle blokken (behalve lucht) in een doos tussen twee hoeken. Max 4096 blokken.
    Gebruik dit om een bouwwerk van de speler exact te bekijken of je eigen bouwwerk te controleren."""
    return tekst(mod("gebied", x1=x1, y1=y1, z1=z1, x2=x2, y2=y2, z2=z2))


@mcp.tool()
def kijk(speler: str = "", x: int | None = None, y: int | None = None, z: int | None = None,
         richting: str = "", omhoog: float = 0.0):
    """Maak een echte screenshot vanuit jouw ogen, zodat je de wereld ZIET.
    Kies waar je naar kijkt: `speler` (naam), of een blok `x y z`, of `richting` (noord/oost/zuid/west,
    met `omhoog` in graden: positief = omhoog, negatief = omlaag). Niks invullen = kijk waar je al naar keek.
    De speler merkt hier niks van: zijn eigen beeld blijft gewoon staan."""
    args = {}
    if speler:
        args["speler"] = speler
    elif x is not None and y is not None and z is not None:
        args.update(x=x, y=y, z=z)
    elif richting:
        args.update(richting=richting, omhoog=omhoog)
    result = mod("screenshot", timeout=20.0, **args)
    pad = result.pop("bestand", None)
    if not result.get("ok") or not pad:
        return tekst(result)
    try:
        from PIL import Image as PILImage
        with PILImage.open(pad) as foto:
            foto = foto.convert("RGB")
            foto.thumbnail((1024, 1024))
            buffer = io.BytesIO()
            foto.save(buffer, format="JPEG", quality=80)
        return [Image(data=buffer.getvalue(), format="jpeg"), tekst(result)]
    except Exception as e:
        result["foto_fout"] = "Screenshot gemaakt maar kon hem niet openen: " + str(e)
        return tekst(result)


# ---------------------------------------------------------------- bewegen

def _wacht_tot_aangekomen(max_seconden: float) -> dict:
    einde = time.time() + max_seconden
    laatste = {}
    while time.time() < einde:
        time.sleep(0.4)
        laatste = mod("status")
        if not laatste.get("ok") or laatste.get("bezig") != "lopen":
            break
    return {
        "bezig": laatste.get("bezig"),
        "pos": laatste.get("blokpos"),
        "gevaar": laatste.get("gevaar", []),
    }


@mcp.tool()
def loop_naar(x: int, y: int, z: int, wacht: bool = True) -> str:
    """Loop naar een plek. Je zoekt zelf een pad (1 blok omhoog stappen, max 3 naar beneden, niet door water).
    Met wacht=True wacht de tool (max 20 seconden) tot je er bent."""
    result = mod("loop", x=x, y=y, z=z)
    if wacht and result.get("ok"):
        result["na_lopen"] = _wacht_tot_aangekomen(20)
    return tekst(result)


@mcp.tool()
def loop_naar_speler(speler: str = "", wacht: bool = True) -> str:
    """Loop naar een speler toe (leeg = de dichtstbijzijnde speler)."""
    result = mod("loop_speler", speler=speler)
    if wacht and result.get("ok"):
        result["na_lopen"] = _wacht_tot_aangekomen(20)
    return tekst(result)


@mcp.tool()
def volg(speler: str = "") -> str:
    """Blijf een speler volgen (leeg = dichtstbijzijnde). Je loopt mee en teleporteert als hij te ver weg raakt.
    Stoppen doe je met `stop`."""
    return tekst(mod("volg", speler=speler))


@mcp.tool()
def stop() -> str:
    """Stop met lopen en met volgen."""
    return tekst(mod("stop"))


@mcp.tool()
def teleporteer(x: int, y: int, z: int) -> str:
    """Noodgreep: teleporteer naar een plek als lopen echt niet lukt."""
    return tekst(mod("tp", x=x, y=y, z=z))


@mcp.tool()
def roep(speler: str = "") -> str:
    """Verschijn in de wereld naast een speler (leeg = de eerste speler). Sta je er al, dan teleporteer je naar hem toe.
    Dit is altijd je eerste stap."""
    return tekst(mod("roep", speler=speler))


@mcp.tool()
def verdwijn() -> str:
    """Haal je poppetje uit de wereld."""
    return tekst(mod("verwijder"))


# ---------------------------------------------------------------- hakken en bouwen

@mcp.tool()
def hak(x: int, y: int, z: int) -> str:
    """Hak 1 blok weg (moet binnen ~5 blokken zijn). Het blok komt in je inventaris."""
    return tekst(mod("hak", x=x, y=y, z=z))


@mcp.tool()
def hak_gebied(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> str:
    """Hak alle blokken in een doos weg (max 125 blokken, alleen wat binnen bereik is)."""
    return tekst(mod("hak_gebied", x1=x1, y1=y1, z1=z1, x2=x2, y2=y2, z2=z2))


@mcp.tool()
def plaats(x: int, y: int, z: int, blok: str) -> str:
    """Plaats 1 blok, bijvoorbeeld 'minecraft:oak_planks' of 'minecraft:oak_stairs[facing=north]'.
    De plek moet leeg zijn en binnen ~5 blokken.
    Een bed (bijv. 'minecraft:orange_bed') zet je in 1 keer helemaal neer: x y z is het voeteneind, het hoofdeind
    komt vanzelf op een vrije plek ernaast. Harnas hoef je niet te plaatsen: dat trek je automatisch aan."""
    return tekst(mod("plaats", x=x, y=y, z=z, blok=blok))


@mcp.tool()
def vul(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int, blok: str, modus: str = "keep") -> str:
    """Bouw een hele doos in 1 keer (max 1000 blokken, binnen 12 blokken van jou). Zo bouw je snel muren, vloeren en daken.
    modus: 'keep' = alleen lege plekken vullen, 'replace' = alles vervangen, 'hollow' = holle doos (binnenin lucht),
    'outline' = alleen de buitenkant. Werkt alleen als de instelling oneindig_blokken aan staat."""
    return tekst(mod("vul", x1=x1, y1=y1, z1=z1, x2=x2, y2=y2, z2=z2, blok=blok, modus=modus))


@mcp.tool()
def geef(item: str, aantal: int = 1, speler: str = "") -> str:
    """Geef iets uit je inventaris aan een speler die dichtbij staat."""
    return tekst(mod("geef", item=item, aantal=aantal, speler=speler))


@mcp.tool()
def val_aan() -> str:
    """Sla het dichtstbijzijnde monster (moet binnen 4 blokken zijn)."""
    return tekst(mod("val_aan"))


# ---------------------------------------------------------------- overleven: springen, craften, eten, kisten

@mcp.tool()
def spring() -> str:
    """Spring 1 keer op de plek (een echt sprongetje)."""
    return tekst(mod("spring"))


@mcp.tool()
def gebruik(x: int, y: int, z: int) -> str:
    """Gebruik een blok met een lege hand (rechtsklik): deur, luik, hekje, hendel, knop, nootblok, bel, taart (eten),
    repeater, comparator, bessenstruik (plukken), kampvuur/kaars (doven) of bed (slapen). Moet binnen ~5 blokken zijn.
    Houten deuren op je looproute doe je vanzelf open. Met een item in je hand: zie `gebruik_item`."""
    return tekst(mod("gebruik", x=x, y=y, z=z))


@mcp.tool()
def maak(item: str, aantal: int = 1) -> str:
    """Craft of smelt iets uit je inventaris, bijvoorbeeld 'planks', 'stick', 'crafting_table', 'wooden_pickaxe',
    'furnace', 'torch', 'iron_ingot'. `aantal` = hoe vaak het recept. Grote recepten hebben een werkbank binnen
    4 blokken nodig, smelten een oven plus brandstof. Zie `recepten` voor alles wat kan."""
    return tekst(mod("maak", item=item, aantal=aantal))


@mcp.tool()
def recepten() -> str:
    """Lijst van alles wat je kunt craften en smelten, met wat je ervoor nodig hebt."""
    return tekst(mod("recepten"))


@mcp.tool()
def eet(item: str = "") -> str:
    """Eet iets uit je inventaris (leeg = het beste eten dat je hebt). In survival vult dit je hongerbalk
    (`honger` in status, 20 = vol); met honger 18+ genees je vanzelf, bij 0 verlies je levens. Op vredig en in
    creatief heb je geen honger. Je eet ook vanzelf als je trek hebt (instelling zelf_eten)."""
    return tekst(mod("eet", item=item))


@mcp.tool()
def jaag(soort: str) -> str:
    """Sla het dichtstbijzijnde dier of wezen van een soort, bijvoorbeeld 'cow', 'pig', 'sheep', 'chicken', 'zombie'.
    Moet binnen 4 blokken zijn; anders krijg je de positie terug om er eerst heen te lopen. Wat het laat vallen
    pak je vanzelf op als je erbij staat. Je slaat nooit spelers."""
    return tekst(mod("val_aan", soort=soort))


@mcp.tool()
def kist(x: int, y: int, z: int, actie: str = "bekijk", item: str = "", aantal: int = 1) -> str:
    """Kist (of ton/oven) op x y z: actie 'bekijk' = wat zit erin, 'pak' = item eruit halen, 'stop' = item erin doen.
    Moet binnen ~5 blokken zijn."""
    return tekst(mod("kist", x=x, y=y, z=z, actie=actie, item=item or None, aantal=aantal))


@mcp.tool()
def slaap() -> str:
    """Ga slapen in een vrij bed binnen 5 blokken (je kiest het oranje bed als dat er is). Doe dit als je het event
    'speler_slaapt' krijgt of als de speler vraagt om te gaan slapen. Je wordt vanzelf wakker als de speler opstaat."""
    return tekst(mod("slaap"))


@mcp.tool()
def word_wakker() -> str:
    """Sta op uit bed. (Elke andere actie zoals lopen of hakken maakt je ook wakker.)"""
    return tekst(mod("word_wakker"))


# ---------------------------------------------------------------- praten en luisteren

@mcp.tool()
def zeg(tekst_bericht: str, hardop: bool = True) -> str:
    """Zeg iets in de Minecraft-chat (als <Claude>). Wordt ook hardop voorgelezen op de pc van de speler.
    Houd het kort: max 240 tekens."""
    result = mod("zeg", tekst=tekst_bericht)
    if hardop and result.get("ok"):
        spreek(tekst_bericht)
    return tekst(result)


STOP_WOORDEN = {"stop", "pauze", "stop claude", "claude stop", "claude pauze", "stop maar"}

SPEEL_REGELS = """SPEEL-LUS GESTART. Zo werkt het vanaf nu:
1. Roep `wacht_op_gebeurtenis` aan. Komt er een chatbericht: doe wat de speler vraagt en antwoord kort met `zeg`.
2. Roep daarna METEEN weer `wacht_op_gebeurtenis` aan. Ook als er niks gebeurde. Blijf dit herhalen.
3. Schrijf GEEN antwoord in de Claude-app en beeindig je beurt NIET. Alles wat je wilt zeggen gaat via `zeg`.
4. Stop pas als het antwoord `stop_gevraagd: true` bevat (de speler typte stop of pauze), of als de mod onbereikbaar is.
   Zeg dan gedag met `zeg` en schrijf pas daarna een korte samenvatting in de Claude-app.
5. Check bij elk antwoord het veld `gevaar` en je `levens`."""


@mcp.tool()
def speel() -> str:
    """Start de speel-lus: je blijft continu in de Minecraft-chat luisteren en antwoorden tot de speler 'stop' typt.
    Roep dit aan zodra de speler wil gaan spelen ('kom je', 'kom spelen', 'ga luisteren'). Volg daarna de regels
    die je terugkrijgt: steeds `wacht_op_gebeurtenis`, antwoorden via `zeg`, en je beurt niet beeindigen."""
    result = mod("status")
    if result.get("ok") and not result.get("claude_in_wereld"):
        mod("roep")
        result = mod("status")
    result["regels"] = SPEEL_REGELS
    return tekst(result)


@mcp.tool()
def wacht_op_gebeurtenis(max_seconden: int = 50) -> str:
    """Wacht tot er iets gebeurt: een chatbericht van een speler, gevaar (monster), au (geraakt), dood, aangekomen
    of vastgelopen. Komt terug zodra er iets is, of na max_seconden (max 110; krijg je een timeout-fout, gebruik dan 50).
    In de speel-lus roep je dit na elk antwoord METEEN opnieuw aan, zonder je beurt te beeindigen."""
    max_seconden = max(1, min(110, max_seconden))
    einde = time.time() + max_seconden
    while True:
        result = mod("events")
        if not result.get("ok"):
            return tekst(result)
        gebeurtenissen = result.get("gebeurtenissen") or []
        if gebeurtenissen:
            for g in gebeurtenissen:
                if g.get("type") == "chat" and str(g.get("tekst", "")).strip().lower().rstrip(".!") in STOP_WOORDEN:
                    result["stop_gevraagd"] = True
            if not result.get("stop_gevraagd"):
                result["hierna"] = "Reageer via `zeg` en roep daarna meteen weer wacht_op_gebeurtenis aan."
            return tekst(result)
        if time.time() >= einde:
            result["bericht"] = "Er gebeurde niks. Roep wacht_op_gebeurtenis METEEN opnieuw aan en beeindig je beurt niet."
            return tekst(result)
        time.sleep(0.4)


@mcp.tool()
def instelling(naam: str, waarde: bool) -> str:
    """Zet een instelling aan of uit:
    - oneindig_blokken: bouwen zonder dat je de blokken hoeft te hebben (standaard UIT: houd je aan de regels van de wereld,
      zet dit alleen aan als de speler er zelf om vraagt)
    - verdedigen: sla automatisch monsters die binnen 3,5 blok komen (standaard aan)
    - waarschuwen: roep automatisch 'Pas op!' in de chat bij een monster (standaard aan)
    - rennen: sneller lopen
    - creatief: spelmodus van Claude. Aan = vliegen (loop_naar vliegt dan in een rechte lijn), onkwetsbaar en alle
      blokken gebruiken. Uit = survival. De speler kan dit ook zelf doen met /gamemodeclaude c of s.
    - zelf_eten: eet vanzelf als je honger hebt en eten bij je hebt (standaard aan)
    - spelers_slaan: mag je een speler slaan? Standaard UIT. Zet dit alleen aan als de speler er zelf om vraagt
      ('sla me eens'), en zet het daarna weer uit (bijvoorbeeld tijdens mijnen of bouwen)."""
    return tekst(mod("instelling", naam=naam, waarde=waarde))


@mcp.tool()
def sla_speler() -> str:
    """Sla de dichtstbijzijnde speler 1 keer (binnen 4 blokken). Werkt alleen als de instelling 'spelers_slaan'
    aan staat. Doe dit alleen als de speler er zelf om vraagt."""
    return tekst(mod("val_aan", soort="speler"))


# ---------------------------------------------------------------- ULTRA: drinken, zitten, rijden, schild, items gebruiken

@mcp.tool()
def drink(item: str = "") -> str:
    """Drink iets uit je inventaris: 'potion' (waterfles), 'milk_bucket' (haalt effecten weg) of 'honey_bottle'.
    Leeg = wat je hebt."""
    return tekst(mod("drink", item=item))


@mcp.tool()
def zit(soort: str = "cushion") -> str:
    """Ga zitten op het dichtstbijzijnde kussen (cushion) binnen 6 blokken. Opstaan doe je met `stap_af`."""
    return tekst(mod("rijd", soort=soort))


@mcp.tool()
def rijd(soort: str = "") -> str:
    """Stap op iets dat binnen 6 blokken staat: 'boat', 'minecart', 'horse', 'pig', 'camel', 'nautilus', 'strider'...
    Leeg = het dichtstbijzijnde waar je op kunt. Je zit er dan op, maar sturen kun je zelf niet: de speler stuurt
    (boot, of het dier aan een touw). Afstappen met `stap_af`; lopen of teleporteren stapt ook af."""
    return tekst(mod("rijd", soort=soort))


@mcp.tool()
def stap_af() -> str:
    """Sta op van een kussen, of stap af van een boot, karretje of dier."""
    return tekst(mod("stap_af"))


@mcp.tool()
def schild(omhoog: bool = True) -> str:
    """Houd je schild omhoog (True) of omlaag (False). Omhoog = klappen en pijlen van wezens en spelers doen je niks.
    Je moet een schild in je inventaris hebben. Zet het weer omlaag als het gevaar weg is."""
    return tekst(mod("schild", omhoog=omhoog))


@mcp.tool()
def gebruik_item(item: str, x: int, y: int, z: int) -> str:
    """Gebruik een item uit je inventaris op een blok (rechtsklik met iets in je hand). Moet binnen ~5 blokken zijn.
    - water_bucket / lava_bucket: leeggieten; bucket: bronblok water of lava opscheppen; glass_bottle: vullen in water
    - flint_and_steel: vuur maken, kampvuur of kaars aansteken, TNT aansteken
    - bone_meal: plant laten groeien
    - een schoffel (bv. iron_hoe): van aarde/gras een akker maken; daarna zaadjes (wheat_seeds, carrot, potato,
      beetroot_seeds, melon_seeds, pumpkin_seeds) op de akker planten
    - een schep: paadje maken of kampvuur doven; een bijl: schors van een stam halen; shears: pompoen uitsnijden"""
    return tekst(mod("gebruik_item", item=item, x=x, y=y, z=z))


@mcp.tool()
def gebruik_op_dier(item: str, soort: str = "") -> str:
    """Gebruik een item op het dichtstbijzijnde dier (binnen 5 blokken; soort bv. 'sheep', 'cow', 'nautilus'):
    shears op schaap (wol), bucket op koe/geit (melk), bowl op mooshroom (soep), saddle op een rijdier,
    pufferfish op nautilus (temmen voor de speler, 1 op 3 kans), of het lievelingseten van een dier om te fokken
    (wheat voor koe/schaap, carrot voor varken, wheat_seeds voor kip...)."""
    return tekst(mod("gebruik_dier", item=item, soort=soort))


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("Test: ik vraag de status op bij de mod...")
        print(json.dumps(mod("status"), indent=2, ensure_ascii=False))
        if "--stem" in sys.argv:
            spreek("Hoi, ik ben Claude. Mijn stem werkt.")
            time.sleep(8)
    else:
        mcp.run()
