# What to say to Claude

A cheat sheet for playing with Claude Buddy: how to get help with the setup, how to start
playing, and what you can ask Claude to do in your world.

You can talk to Claude in any language. The examples are in English.

## Versions you need

| What | Version |
|---|---|
| Minecraft: Java Edition | 26.3 |
| Fabric Loader | 0.20.1 or newer |
| Fabric API | the build for 26.3 |
| Java | 25 |
| Python | 3.10 or newer |
| Python package `mcp` | 1.2 or newer |
| Claude | the Claude Desktop app (the website alone cannot reach the mod) |

## Let Claude help you set it up

Stuck during the setup? Paste the README into a chat with Claude and say for example:

- "Help me set up Claude Buddy step by step. I am on Windows."
- "I get this error when I run `gradlew build`:" (paste the error)
- "Here is my Claude Desktop config. Add the claude-minecraft server to it without removing
  anything." (paste your config)
- "The test with `--test` shows no players. What did I do wrong?"

## Start playing

1. Start Minecraft and open your world.
2. In Claude Desktop say: **"Come play Minecraft."**
3. Claude appears next to you. From now on you talk in the Minecraft chat (press `T`).
4. Type **"stop"** in the chat when you are done.

## Things you can say in the Minecraft chat

| You want Claude to... | Say something like |
|---|---|
| come to you | "come here" / "follow me" / "stop following" |
| look around | "what do you see?" / "look at my house" |
| gather things | "chop that tree" / "mine some stone" / "go hunting" |
| build | "build a small house here" / "put a torch on that wall" |
| craft | "make a crafting table" / "make a wooden pickaxe" / "what can you craft?" |
| use things | "open that chest" / "sleep in that bed" / "sit down" / "ride that horse" |
| fight | "attack that zombie" / "put your shield up" |
| share | "give me your cobblestone" |
| tell you things | "where are you?" / "how many hearts do you have?" / "what is in your inventory?" |

Claude also warns you by itself when a monster comes close, and defends itself.

## Settings you can ask for

| Say | What happens |
|---|---|
| "go into creative mode" (or type `/gamemodeclaude c`) | Claude can fly, takes no damage and can use every block |
| "go into survival mode" (or type `/gamemodeclaude s`) | Claude gets hungry, takes damage and can die |
| "turn on infinite blocks" | Claude builds without needing the blocks in its inventory |
| "run instead of walk" | Claude moves faster |
| "stop warning me about monsters" | no more "Watch out!" messages |
| "stop defending yourself" | Claude no longer hits monsters that come close |
| "you may hit me" | allows a friendly fight; it is off by default |

## Good to know

- Claude can only mine and place blocks close to itself, so it walks there first.
- In survival Claude can die and then loses its items. Say "come back" and it respawns next to you.
- Big builds take a while: Claude places them piece by piece and checks its work.
- Claude reads the chat only while a game session is running. If it stops answering, go back to
  Claude Desktop and say "Come play Minecraft" again.
