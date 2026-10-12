# EQL Assistant

A log-based DPS parser, overlay and Plane of Sky class-unlock tracker for **EverQuest Legends**.

It only reads the log file the game already writes. No injection, no memory reading, nothing touches the game client.

## What it does

- **In-game windows**, both always on top of EverQuest Legends:
  - **DPS overlay**: current-fight DPS (live), average DPS over your last 10 fights with a bar chart, and your next respawn timers.
  - **Motes window**: motes collected this session, split by tier (Lesser, Major, Greater, …), with a per-hour rate.
  - **Dungeon crawl timer**: the live crawl time against your best for that zone and difficulty, with kills, deaths and motes.
- **Respawn timers**: list the mobs you camp and their respawn times. A countdown starts automatically when one dies.
- **Dungeon crawls**: how long each crawl took, timed automatically, with personal bests per zone and difficulty, plus a live crawl timer on the DPS overlay.
- **Raids**: which raid bosses you've killed since the Tuesday reset, with the countdown to the next one.
- **Class quests**: item checklists for 115 class quests from EQLWiki: the epics, plus spell, weapon, armour and item quests such as Torrid Corruptor, Fiery Avenger, Tashania, SoulFire and Ice Comet. Add any other quest by importing it from the EQL wiki.
- **Factions**: every faction change from your log, what caused it, and your estimated standing.
- **DPS parser**: every fight, split into two sides.
  - **Players & group**: you, groupmates and pets, with damage, DPS, hits, average, max, crits and damage taken.
  - **NPCs**: what each mob took, what it dealt and who it hit most.
  - A **combat log** for each fight, filterable to All, Players & group, or NPCs. It includes misses, dodges, parries, blocks, ripostes, and your spell casts, resists, fizzles and interrupts.
  - **Click any row** (you, a groupmate, or an NPC) for a full breakdown with improvement suggestions. Double-clicking the in-game DPS overlay opens your own breakdown for the latest fight.
- **Plane of Sky tracker**: all 95 class tests across the 16 classes, grouped by class unlock.
  - Quest items and wind runes you've looted, per character.
  - Tests turned in, and tests still to do, with a progress bar per class.
  - Tests you can hand in right now are flagged **READY TO TURN IN**.
  - A "still needed" list of every boss drop and wind rune across your remaining tests, with where it drops.
  - A log of your Sky drops, plus Sky loot your group/raid picked up.

## Download

Grab **EQLAssistant.exe** from the [latest release](../../releases/latest) and double-click it. No install and no Python needed. Windows may say "Windows protected your PC" because the file isn't code-signed: click **More info → Run anyway**. Each release also has a `.sha256` checksum if you want to verify the download.

## Setup (Windows)

### Option A: build a single EQLAssistant.exe yourself

1. Install **Python 3.13** from python.org, and tick **"Add python.exe to PATH"**. You only need it for the build; the finished .exe doesn't need Python. (3.10–3.13 all work. On newer versions the app window library may not install yet, and the .exe then opens in your web browser instead.)
2. Double-click **Build EXE.bat**. After a minute or two, `EQLAssistant.exe` appears in this folder.
3. Move `EQLAssistant.exe` anywhere you like and double-click it. It opens as its own app window (no console, no web browser), and the in-game overlay opens with it. Everything is inside that one file.

Windows may show a blue "Windows protected your PC" screen the first time, because the .exe isn't signed. Click **More info → Run anyway**. Some antivirus tools also flag self-built Python .exes; that's a known false alarm with PyInstaller.

### Publishing a release on GitHub

The workflow in `.github/workflows/build-exe.yml` builds the .exe on GitHub's Windows machines:
- every push: the .exe is attached to the run (Actions tab → the run → **Artifacts**);
- to publish a new version, change `__version__` in `eqlc/__init__.py` (e.g. to `"1.0.1"`) and push to `main`: the build creates the `v1.0.1` tag and a **Release** with `EQLAssistant.exe` and its checksum. The version shows at the bottom of Settings;
- pushing a version tag yourself (e.g. `git tag v1.0.1` then `git push origin v1.0.1`) does the same.

### Option B: run from source

1. Install Python as above.
2. Double-click **Start EQL Assistant.bat**.

### Then

1. In game, type `/log on`.
2. In the app window, go to **Settings**, click **Browse…** and pick your EverQuest Legends `Logs` folder (the one containing `eqlog_<Name>_<server>.txt`).
3. The in-game overlay opens on its own. Run the game in **borderless windowed** mode so it stays on top.
4. To quit, close the app window. The overlay closes with it. (In the browser fallback, use **Quit EQL Assistant** at the bottom of Settings.)

### The in-game windows (Overlays tab)

The **Overlays** tab has a card for each in-game window (DPS overlay, Motes window, Dungeon crawl timer):
- **On/off switch:** shows or closes the window straight away. An overlay that's on opens again next time you start the app; one that's off stays closed.
- **Size** (60–250%) and **Opacity** (20–100%) sliders.
- **Lock position and size**, and **Reset size and position**.
- DPS overlay only: show or hide the **respawn timers**, and choose whether it also shows the crawl timer (handy if you'd rather not run the separate crawl window).

On the windows themselves:
- Drag to move; each remembers its own position.
- Drag the **◢ corner grip** (bottom-right) to resize, or hold **Ctrl** and use the mouse wheel. Everything scales together.
- Right-click for size, opacity, lock, reset, and **Turn off**. Changes made here show on the Overlays tab too.
- Run EverQuest Legends in **borderless windowed** mode (not exclusive fullscreen), otherwise the game draws over them.

## Fight breakdown and suggestions

Click a name in a fight (or **My breakdown & tips** on the DPS Parser tab, or double-click the in-game DPS overlay). The panel shows:

- **Tiles**: DPS, accuracy (melee hits ÷ swings), crit rate, uptime (share of the fight you were dealing damage), max hit and damage taken.
- **Your melee swings**: hit, miss, dodge, parry, block, riposte, absorbed, invulnerable, as counts and percentages.
- **Attacks on you**: how often mobs hit, missed or were avoided.
- **Spells** (your own): casts, landed, DoT ticks, resisted, interrupted, fizzled, damage, plus which mobs resisted what, and enemy spells you resisted.
- **Suggestions**: red **fix** items, gold **tips**, green **good** notes. Each shows the numbers behind it. For example:
  - lots of parries and ripostes → attack from behind;
  - high resist rate on a spell → debuff resists or switch resist type;
  - frequent interrupts → cast from range and let the tank build aggro;
  - low uptime → engage sooner;
  - DoTs on short fights → use direct damage.

  Tips only appear with enough data (about 30 swings or 5 casts). Switch to **Last 10 fights** for a bigger sample.

Clicking an NPC shows the other side: how often it hit your group, how much it avoided, and which of your spells it resisted.

What the log can and can't show:
- Spell casts, resists, fizzles and interrupts only appear for **your own** character, so spell numbers aren't available for other players or NPCs.
- Other players' misses only appear if your in-game chat filters show them. Turn on "Others misses" and "Others hits" for the fullest group picture.

## Motes

The motes counter uses the same matching rules as `scroll-bridge.js`:

- It counts `--You have looted a Mote of ... Potential` as 1, and `--You have looted 4 Motes of ... Potential` as 4.
- Only your own loot counts, not other players'.
- It counts **this session only**: motes looted since you opened the app. Closing and reopening the app starts again from 0. There's no timed reset.

### Motes by tier

Motes are split by the tier word in the loot line: Lesser, Major, Greater, Superior, Grand, Ascendant, Infinite, and plain "Mote of Potential" with no tier. The lines that count, and the totals, are exactly the same as scroll-bridge; the tier word is just recorded as well.

## Dungeon crawls

The **Dungeon Crawls** tab times every crawl from the log.

- **Start:** "`<ZONE NAME>` is now available to you." sets up the run for that zone. The timer then starts on the **first kill** inside that zone's instance (yours or your group's); travel, buffing and anything before that first kill isn't counted. When you zone in, the run picks up the instance's number and difficulty, e.g. `Lower Guk 7 (Fused)`. Difficulty shows as D0–D4 (D1 Awakened, D2 Adaptive, D3 Fused, D4 Refined).
- **End:** the run ends on the first line containing "from Reward Chest", which is the first item looted from the chest by you or anyone in your group.
- **Fallbacks:**
  - If you enter an instance without an "is now available" line, it's still timed from the first kill, but marked "start unknown" and never counted as a personal best. The same goes for a chest looted without any kill.
  - If the crawl completes ("You have completed the Dungeon Crawl…") but nobody loots the chest, the run ends at the completion line once you leave.
  - An instance that's offered but never entered within 30 minutes is dropped.
- **Porting out:** Gate, Succor and other ports drop you out of the instance. Coming back into the same instance continues the same run. The time spent outside is included in the duration and shown separately.
- **Not completed:** if you leave and don't come back within 30 minutes, the run is kept as "not completed". This also covers normal farming instances, since the log can't tell those apart from a crawl until one finishes. These are hidden unless you tick **Show not completed**. Use **Not a crawl** to stop timing an instance straight away, or **Restart timer** if you buffed for ages before starting.

For each run you get:
- duration, time inside the instance, time ported out and time from "is now available" to the first kill;
- time in combat vs downtime (for runs within the recent fight history);
- kills, deaths, motes by tier, motes per hour and XP gained;
- what the Reward Chest gave you, and whether your instance charge was refunded.

**Personal bests** show your best, average and last time for each zone and difficulty. The run history shows how far each run was from your best.

While a crawl is running, the **Dungeon crawl timer** window shows the zone, difficulty and live time against your best. It shows "READY · starts on first kill" until the first mob dies, and "NOT ENTERED YET" or "OUTSIDE" when you are not in the instance. The time turns red once you are behind your best, and shows **NEW BEST!** when you beat it. The DPS overlay can show the same timer too; turn either on or off on the Overlays tab.

The first time you run this version, the app looks back through your existing logs for past crawls. **Settings → Rescan logs for past dungeon crawls** does it again.

## Raids

The **Raids** tab lists raid bosses and ticks each one when your log shows it die. Counts run from the last weekly reset, Tuesday 8am Pacific (4pm UK time for most of the year), and the tab counts down to the next.

- **Bosses:** Classic is shown by default: Nagafen, Vox, Phinigel, Master Yael, Plane of Fear, and Plane of Hate. Tick **Kunark** or **Velious** to show those lists when they open. **+ Add boss** adds any named mob you want counted.
- **Each kill shows:** when it died, who landed the killing blow, and the difficulty. After a kill, "repeat in…" counts down the 18-hour window for the extra-loot repeat clear.
- **Past weeks:** switch to **Last week** or **2 weeks ago** to see earlier lockout weeks.

You need to be in the zone for the kill to appear in your log.

## Class quests

The **Class Quests** tab has item checklists for:
- **the epics** listed on EQLWiki (all classes except Beastlord, which has no epic page there yet), from the EQL wiki's "Epic Items To Keep" checklist; items the wiki marks unverified show ⚠;
- **Coin of Tash (Tashania)** for Enchanters, **Zimel's Blades (SoulFire)** for Paladins and **Tarton's Wheel (Ice Comet)** for Wizards, step by step;
- about 100 more class quests, all taken from EQLWiki (eqlwiki.com) and listed in its class quest categories, including:
  - **weapons**: Torrid Corruptor, Fiery Avenger, Sword of Nobility, Harvester, Rogue Redemption (Burning Rapier), Rain Caller, Langseax, Eye of Stormhammer, the Iksar warrior pikes;
  - **spells**: the cleric/shaman/druid symbol quests, the Summoning of Dread/Fright/Terror, Ilanic's Scroll, Brain Bite, Cannibalize II;
  - **armour sets**: Armor of Ro, Darkforge, ShadowBound, Incandescent, Lambent, Totemic, Ivy Etched, Trooper Scale and others, listed piece by piece;
  - **items**: Robe of the Elements, Mystic Cloak, Monk headbands and sashes, mage summoned-item quests and more.

Velious quests are left out for now.

Every epic is marked **"Not available pre-Kunark"**, and so is any other quest that needs Kunark zones. You'll see the label on the quest row and a banner inside it.

Tick the classes you play to filter the list. You can also filter by type (spells, weapons, armour, items, epics), hide completed quests, and hide everything that isn't available before Kunark.

**How items tick off:**
- Items you **loot** or **receive** tick themselves, along with how many you hold.
- `/outputfile inventory` gives exact counts.
- Ground pick-ups (like the Tash coins and Tarton's rods), combines and hand-ins usually don't show in the log, so tick those yourself.
- A quest marks itself completed when its reward turns up in your items, or you can tick it.

**Adding quests:**
- **Import from EQL wiki:** paste any EQLWiki quest page link (e.g. from the `<Class> Quests` category pages linked on the tab). Links to other wikis, such as Project 1999, are refused. The app reads the page, lists every item it links to, lets you untick the ones you don't need, and saves it as a checklist.
- **Add by hand:** type the items in yourself.

Items you looted before adding a quest still count.

## Factions

The **Factions** tab records every `Your faction standing with … has been adjusted by …` line.

- **Per faction:** net change, the last 24 hours, number of hits, the last change, and what caused it (e.g. "killing a Freeport militiaman ×8: −80"). It also flags factions that "could not possibly get any better" or "any worse".
- **Absolute standing:** the log never shows this. Click **Set** and enter a faction's current value once. From then on the app keeps an estimated value and standing name (Ally, Warmly, Kindly…), using classic EQ thresholds.
- **/consider results:** every NPC you /con is listed with how they see you.

The first time you run this version, the app also reads your older log history for raid kills, faction changes and looted items.

## Respawn timers

1. Open the **Respawn Timers** tab and add the mobs you want timed: name, respawn time in minutes, and optionally:
   - **± Window**: extra minutes the spawn can be late. The timer then shows a spawn window instead of one time.
   - **Zone**: only start the timer when you're in that zone (matched against "You have entered …").
2. Click **Save list**. Recently killed mobs appear as one-click buttons to add.
3. When one of those mobs dies in your log, by you or anyone else, its countdown starts. The next five show on the DPS overlay, turning red in the last minute and green **UP** when due.
4. Missed a kill, or want to time something not on the list? Type the name (and minutes) and click **Start now**.

Names aren't case-sensitive, and `*` is a wildcard: `a spiroc *` times every spiroc. Running timers survive restarting the app.

## How Plane of Sky tracking works

- **Drops**: every `--You have looted ... --` line for a Sky quest item or wind rune is counted for that character. Loot by other people is listed separately and does not count as yours.
- **Turn-ins** are picked up three ways:
  1. Any log line showing you got the test's reward, e.g. `You receive Amulet of the Fae from Nomaad.`, `Nomaad gives you Amulet of the Fae.`, `You have been given …` or `--You have looted …--`. Chat lines and other people's loot are ignored. Older logs are checked once too, so tests you finished before using the app tick themselves.
  2. A reward item showing up in an inventory export.
  3. Ticking the box yourself.
  Ticks you make yourself are treated as "done before tracking started", so they don't use up items you're holding.
- **Exact counts**: type `/outputfile inventory` in game now and then. The app reads the export from your game folder and uses it as the true count of what you hold, then adds later loot on top.
- Items you looted before logging was on can be added with the `+` / `−` buttons in the "Still needed" list.
- If you unlocked a class with a Primary Class Unlock Token, tick **unlocked via token** on that class.

The quest data comes from the EverQuest Legends wiki (eqlwiki.com) and lives in `eqlc/sky_data.py`. If the wiki changes, edit that file and restart the app.

## How fights and DPS are measured

- A fight starts at the first damage and ends when every mob you were fighting has died, or after 10 seconds with no damage. The idle time is adjustable in Settings.
- **Players vs NPCs**: anything you attack, or that attacks you, is an NPC. Anyone hitting an NPC is on your side. Names in your pet list are labelled as pets.
- **DPS** is your damage divided by the fight's length. **SDPS** is damage divided by that combatant's own active time.
- **Last 10 average** is the mean of your DPS across your last 10 fights. Fights shorter than 5 seconds, or where you did no damage, are skipped. Both numbers are adjustable.
- Pet damage can be counted as yours: tick the option in Settings and enter your pet's name.
- On start, the app re-reads the last 8 MB of each log to rebuild recent fight history. Sky progress is saved and picks up exactly where it left off.

## The app window

The app window uses pywebview, which draws the window with Microsoft Edge WebView2. WebView2 is built into Windows 11 and most up-to-date Windows 10 PCs.

If the window can't start, EQL Assistant opens in your web browser instead and works the same way. To force browser mode, run it with `--browser`.

## Files

- Settings and Sky progress are saved in `%APPDATA%\EQLAssistant\`. If you used the app under its old name (EQL Companion), your data in `%APPDATA%\EQLCompanion\` moves across automatically the first time you run it.
- Run the tests with `python -m unittest discover tests`.
- If you put the project on GitHub, `.github/workflows/build-exe.yml` builds the .exe on GitHub's Windows machines on every push.

## Icon

The wizard icon (`assets/icon.ico`) is used for `EQLAssistant.exe`, the app window's title bar and taskbar button, and the logo inside the app.

If Windows still shows an old icon for the .exe after you rebuild it, that's Windows' icon cache. Move or rename the .exe, or press Win+R and run `ie4uinit.exe -show`. Re-pin it to the taskbar if you'd pinned the old one.

## Known limits

- The log doesn't say who cast a spell on a mob unless it's you (classic "non-melee" lines are counted as yours). Other players' spell damage can be under-counted. This is the same limit every EQ log parser has.
- The exact wording EQL uses when a quest NPC hands you a reward hasn't been confirmed. If turn-ins aren't being picked up, use `/outputfile inventory` or tick them, and send me a sample line so the pattern can be added.

## License

EQL Assistant is free software, licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE).
You can use, share and change it; if you distribute a modified version, it must also be under the GPL v3 with its source available.
