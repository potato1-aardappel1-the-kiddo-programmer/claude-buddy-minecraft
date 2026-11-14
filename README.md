# Claude Buddy — play Minecraft together with Claude

Claude Buddy gives Claude (the AI from Anthropic) its own character in your Minecraft world.
You type in the normal Minecraft chat, and Claude answers, walks around, mines, builds, fights
monsters and even looks at the world through its own eyes.

> Unofficial fan project. Not affiliated with or endorsed by Anthropic, Mojang or Microsoft.

## How it works

```
Claude Desktop  <->  MCP server (Python)  <->  Fabric mod (port 25599)  <->  Minecraft
```

- **The mod** (`claudebuddy.jar`, source in `mod.zip`, Java) spawns a player-like character and carries out commands such as
  "walk there", "place this block" or "say this in chat". It also reports back what happens
  in the game (chat messages, danger, damage).
- **The MCP server** (`mcp_server/`, Python) is the bridge. It turns those commands into tools
  Claude can use, and passes the answers (including screenshots) back to Claude.

The mod only listens on `127.0.0.1`, so nothing outside your own computer can reach it.

## What you need

| What | Version |
|---|---|
| Minecraft: Java Edition | 26.3 |
| Fabric Loader | 0.20.1 or newer |
| Fabric API | the build for 26.3 |
| Java | 25 (Minecraft 26.3 needs it anyway) |
| Python | 3.10 or newer |
| Claude Desktop | with local MCP servers enabled |

Python packages (installed in step 2 with `requirements.txt`):

| Package | Version | Used for |
|---|---|---|
| `mcp` | 1.2 or newer | the MCP server itself |
| `pillow` | any recent | shrinking the screenshots Claude looks at |
| `edge-tts` | any recent | the voice (optional, see [Settings](#settings)) |

Built and tested on Windows, in single-player worlds. The voice (text-to-speech) part uses
PowerShell, so on other systems turn the voice off (see [Settings](#settings)).

## Setup

### 1. Install the mod

Take the ready-made mod from this repository: `claudebuddy.jar`

Put that file in your Minecraft `mods` folder, together with **Fabric API for 26.3**.

<details>
<summary>Or build it yourself from the source</summary>

1. Unzip `mod.zip`. It contains the full source of the mod.
2. Open a terminal in the unzipped `mod` folder and run:

   ```
   .\gradlew build
   ```

   If Gradle complains about the Java version, open `mod/gradle.properties` and set
   `org.gradle.java.home` to your own JDK 25 folder.
3. The mod appears at `mod/build/libs/claudebuddy-1.0.0.jar`.

</details>

### 2. Install the MCP server

In the `mcp_server` folder:

```
pip install -r requirements.txt
```

Test it: start Minecraft, **open a world**, then run:

```
python claude_minecraft_mcp.py --test
```

You should see a list with `"spelers"` (players) and your own name in it.
To also test the voice: `python claude_minecraft_mcp.py --test --stem`

### 3. Connect it to Claude Desktop

1. In Claude Desktop go to **Settings → Developer → Edit Config**.
2. Add `claude-minecraft` to `mcpServers`:

   ```json
   {
     "mcpServers": {
       "claude-minecraft": {
         "command": "python",
         "args": ["C:\\Users\\example\\Desktop\\claude-buddy-minecraft\\mcp_server\\claude_minecraft_mcp.py"]
       }
     }
   }
   ```

   Change the path to where **your** copy of `claude_minecraft_mcp.py` is. On Windows every
   backslash must be doubled (`\\`). If you already have other servers in `mcpServers`, add
   this one next to them with a comma in between — do not remove the others.
   (The same snippet is in `mcp_server/claude_desktop_config.example.json`.)
3. Quit Claude Desktop completely (also from the system tray) and start it again.

### 4. Play

1. Start Minecraft and open your world.
2. Tell Claude: **"Come play Minecraft"**.
3. Claude appears next to you. Talk to it in the normal Minecraft chat (press `T`).

## What Claude can do

| Group | Tools |
|---|---|
| Sense and see | `status`, `kijk` (screenshot from Claude's eyes), `scan_blokken`, `bekijk_gebied`, `blok_op` |
| Move | `roep`, `loop_naar`, `loop_naar_speler`, `volg`, `spring`, `teleporteer`, `stop`, `verdwijn` |
| Mine and build | `hak`, `hak_gebied`, `plaats`, `vul` |
| Items and crafting | `maak`, `recepten`, `kist`, `geef`, `gebruik`, `gebruik_item`, `gebruik_op_dier` |
| Survive | `eet`, `drink`, `slaap`, `word_wakker`, `schild`, `val_aan`, `jaag`, `sla_speler` |
| Ride and sit | `rijd`, `stap_af`, `zit` |
| Talk and play | `zeg`, `speel`, `wacht_op_gebeurtenis`, `instelling` |

The tool names, their descriptions and Claude's in-game instructions are in **Dutch**, because
that is the language this project was made in. Claude understands them fine and will simply
talk to you in whatever language you use.

In-game command: `/gamemodeclaude c` (creative: fly, no damage, all blocks) or
`/gamemodeclaude s` (survival: hunger, damage, only blocks Claude collected itself).

## Settings

Optional environment variables, set with an `"env"` block next to `"args"` in the config:

| Variable | Default | What it does |
|---|---|---|
| `CLAUDE_MC_TTS` | `1` | `0` turns the voice off |
| `CLAUDE_MC_STEM` | `nl-NL-MaartenNeural` | which voice reads Claude's messages aloud |
| `CLAUDE_MC_URL` | `http://127.0.0.1:25599/` | where the mod is listening |

Example: `"env": {"CLAUDE_MC_TTS": "0"}`

See [WHAT_TO_SAY_TO_CLAUDE.md](WHAT_TO_SAY_TO_CLAUDE.md) for example sentences and all the settings you can ask for.

## Good to know

- Claude is a "mannequin" entity that looks like a player. It is not in the player list.
- The voice uses the `edge-tts` package, which sends the text Claude says to Microsoft's online
  speech service. Turn the voice off if you do not want that.
- Claude's inventory is empty again after you reopen the world.
- In survival Claude can die and loses its items; ask it to come back and it respawns next to you.

## License

[CC0 1.0](LICENSE) — do whatever you like with it.
