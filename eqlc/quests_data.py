"""Built-in class quests for EverQuest Legends.

Sources (eqlwiki.com, checked October 2026):
  - Epic item checklists: "User:Manlaan/Epic Items To Keep" (items marked
    unverified there have u=True) and the per-class "<Class> Epic Quest" pages.
  - Coin of Tash (Tashania), Zimel's Blades (SoulFire), Tarton's Wheel (Ice Comet).

Plus ~100 class spell, weapon, armour and item quests in quests_more.py
(Torrid Corruptor, Fiery Avenger, Armor of Ro, symbol quests, ...).

Any other class quest can be added in the app (Quests tab -> Add quest), or
imported straight from its eqlwiki page.

Item fields: n = exact item name, q = quantity (default 1), src = where it
comes from, how = drop | forage | buy | craft | collect | quest | turnin,
g = optional group heading (a sub-quest to finish first), u = unverified.
"""

from .quests_more import QUESTS_MORE

WIKI = "https://eqlwiki.com/"


def _i(n, src, how="drop", q=1, g=None, u=False):
    d = {"n": n, "src": src, "how": how, "q": q}
    if g:
        d["g"] = g
    if u:
        d["u"] = True
    return d


EPIC_NOTE = ("Items worth collecting before or during the epic, from the community "
             "\"Epic Items To Keep\" checklist. See the wiki page for the full walkthrough.")

QUESTS = [
    # ------------------------------------------------------------------ examples asked for
    {
        "id": "enc-tashania", "cls": ["Enchanter"], "kind": "spell",
        "name": "Coin of Tash (Tashania)", "reward": "Spell: Tashania", "level": "35 to start, 41 to use",
        "giver": "Romar Sunto, Temple of Solusek Ro (+395, +95)", "wiki": WIKI + "Coin_of_Tash_(Tashania)",
        "notes": "Borrow the Coin Pouch from Romar Sunto (he also sells the Tome of Tash, 50gp, listing the "
                 "coin spots). Coins are ground spawns in city pools and fountains: tick them as you pick them up. "
                 "Don't hand items in while invisible (sneak is fine).",
        "items": [
            _i("Coin Pouch", "Romar Sunto, Temple of Solusek Ro (lent to you)", "quest"),
            _i("Old Silver Coin (Azia)", "Ak'Anon, west side of the water wheel (1990, -260)", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Beza)", "Erudin Palace, rock fountain one level above the zone-in teleporter", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Caza)", "Northern Felwithe, fishing pond (-110, -790)", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Dena)", "West Freeport, pool under the Academy of Arcane Science (129, -750)", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Ena)", "Grobb, small pool near a bar after the first bridge (197, -261)", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Fana)", "Halas, underwater ledge in the lake by the far dock (-138, 179)", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Geza)", "South Kaladim, pool by the Warriors' Guild (75, 360)", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Heda)", "Neriak Commons, water by the glass windows past the big bridge (0, -795)", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Izah)", "Oggok, lake near the Warriors' Guild, north end (109, 101)", "collect", g="10 Old Silver Coins"),
            _i("Old Silver Coin (Jaka)", "North Qeynos, Koalindl Fish Pool under the Temple of Life (-90, -445)", "collect", g="10 Old Silver Coins"),
            _i("Coin of Tash", "Combine the 10 coins in the Coin Pouch", "craft", g="Turn-ins"),
            _i("Glowing Coin of Tash", "Give Coin of Tash to Tarn Visilin, High Keep library (+75, -220)", "turnin", g="Turn-ins"),
            _i("Gleaming Coin of Tash", "Give Glowing Coin to Mizr N'Mar, Neriak Third Gate library", "turnin", g="Turn-ins"),
            _i("Radiant Coin of Tash", "Give Gleaming Coin to Raine Beteria, Erudin library (may need Erudite illusion)", "turnin", g="Turn-ins"),
        ],
    },
    {
        "id": "pal-soulfire", "cls": ["Paladin"], "kind": "weapon",
        "name": "Zimel's Blades (SoulFire)", "reward": "SoulFire", "level": "Any (50 recommended for the kills)",
        "giver": "Kalatrina Plossen, North Freeport", "wiki": WIKI + "Zimel's_Blades_(SoulFire)",
        "notes": "Needs Warmly with Knights of Truth (Valeron Dushire) and Warmly with Priests of Life "
                 "(Brother Hayle, Splitpaw jail cells: bring invis, the cell locks from outside). "
                 "Turn the Sealed Note in to Brother Hayle alone first.",
        "items": [
            _i("Bottle", "Vendor", "buy", g="Part 1: A Sealed Note"),
            _i("Snake Scales", "Drop or vendor", "drop", g="Part 1: A Sealed Note"),
            _i("Water Flask", "Vendor", "buy", g="Part 1: A Sealed Note"),
            _i("Bog Juice", "Brewing (trivial 21): Bottle + Snake Scales + Water Flask", "craft", g="Part 1: A Sealed Note"),
            _i("Fire Beetle Eye", "Fire beetles", "drop", g="Part 1: A Sealed Note"),
            _i("Rat Ears", "Rats, or vendor", "drop", g="Part 1: A Sealed Note"),
            _i("Edible Goo", "Baking (trivial 21): Fire Beetle Eye + Rat Ears (don't eat it)", "craft", g="Part 1: A Sealed Note"),
            _i("Drom's Champagne", "Bartender, Seafarer's Roost, East Freeport", "buy", q=4, g="Part 1: A Sealed Note"),
            _i("Bunker Cell #1", "Give 4 Drom's Champagne to Tykar Renlin (East Freeport)", "turnin", g="Part 1: A Sealed Note"),
            _i("H. K. 102", "Give Bog Juice, Edible Goo, Bunker Cell #1 to a prisoner, West Freeport Arena prison", "turnin", g="Part 1: A Sealed Note"),
            _i("A Sealed Note", "Give H. K. 102 to Assistant Kiolna, Highpass Keep bank", "turnin", g="Part 1: A Sealed Note"),
            _i("A Spider Venom Sac", "Any ordinary giant spider", "drop", g="Part 2: The Testimony"),
            _i("Cloth Shirt", "Vendor (medium size)", "buy", g="Part 2: The Testimony"),
            _i("Token of Generosity", "Give Cloth Shirt to Altunic Jartin, East Commons (needs Knights of Truth above Indifferent)", "turnin", g="Part 2: The Testimony"),
            _i("Token of Bravery", "Give Spider Venom Sac to Merko Quetalis, Hall of Truth courtyard", "turnin", g="Part 2: The Testimony"),
            _i("Token of Truth", "Guard Willia, Freeport sewers (spawned by giving Merko both tokens; kill fast)", "drop", g="Part 2: The Testimony"),
            _i("Testimony", "Return Token of Truth to Merko Quetalis", "turnin", g="Part 2: The Testimony"),
            _i("Glowing Sword Hilt", "Xicotl (rare), pool room, Mistmoore Castle — 100% drop", "drop", g="Part 3: The Hilt"),
            _i("Testimony of Truth", "Undead Sir Lucan D'Lere, West Freeport (kill Sir Lucan first)", "drop", g="Part 4: The Brilliant Sword"),
            _i("Brilliant Sword of Faith", "Give Testimony of Truth to Valeron Dushire, Hall of Truth balcony (Warmly with Knights of Truth)", "turnin", g="Part 4: The Brilliant Sword"),
        ],
    },
    {
        "id": "wiz-icecomet", "cls": ["Wizard"], "kind": "spell",
        "name": "Tarton's Wheel (Ice Comet)", "reward": "Spell: Ice Comet", "level": "35+ (spell is level 49)",
        "giver": "Sulgar, northern wall of Everfrost Peaks", "wiki": WIKI + "Tarton's_Wheel",
        "notes": "Collect the ten rods and combine them in the temporary Glowing Chest. Items stored in the "
                 "chest are lost if you camp. Give the Staff of the Wheel and the Star of Eyes to Sulgar.",
        "items": [
            _i("Glowing Chest", "Sulgar, Everfrost Peaks (temporary container)", "quest"),
            _i("Rod of Azia", "Underwater shipwreck, Erud's Crossing (zombie sailors and sharks)", "collect", g="The ten rods"),
            _i("Rod of Beza", "House in the caves of Everfrost Peaks, through the frozen river", "collect", g="The ten rods"),
            _i("Rod of Caza", "Underwater stone tower, Lake Rathetear", "collect", g="The ten rods"),
            _i("Rod of Dena", "Lake gully in Dagnor's Cauldron, west of Kedge Keep", "collect", g="The ten rods"),
            _i("Rod of Ena", "A room in Lower Guk", "collect", g="The ten rods"),
            _i("Rod of Fana", "Underwater tower, Oasis of Marr", "collect", g="The ten rods"),
            _i("Rod of Geza", "Beneath the waterfall, Highpass Hold", "collect", g="The ten rods"),
            _i("Rod of Heda", "Shark pit, Qeynos Aqueducts", "collect", g="The ten rods"),
            _i("Rod of Izah", "River floor outside The Blind Fish, Neriak", "collect", g="The ten rods"),
            _i("Rod of Jaka", "Hidden cavern in Unrest", "collect", g="The ten rods"),
            _i("Staff of the Wheel", "Combine the rods in the Glowing Chest", "craft", g="Combine and turn in"),
            _i("Star of Eyes", "Combine the rods in the Glowing Chest", "craft", g="Combine and turn in"),
        ],
    },

    # ------------------------------------------------------------------ epics
    {"id": "brd-epic", "cls": ["Bard"], "kind": "epic", "name": "Bard Epic Quest", "reward": "Singing Short Sword",
     "wiki": WIKI + "Bard_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("White Dragon Scales", "Lady Vox (raid), Permafrost"),
         _i("Amygdalan Tendril", "Amygdalan warrior, Plane of Fear"),
         _i("Red Dragon Scales", "Lord Nagafen (raid), Nagafen's Lair"),
         _i("Kedge Backbone", "Phinigel Autropos (raid), Kedge Keep", u=True),
         _i("Onyx Drake Gut", "Blackwing, Rathe Mountains", u=True),
         _i("Alluring Horn", "Quag Maelstrom, Ocean of Tears"),
     ]},
    {"id": "bst-epic", "cls": ["Beastlord"], "kind": "epic", "name": "Beastlord Epic Quest", "reward": "Beastlord epic",
     "wiki": WIKI + "Beastlord_Epic_Quest",
     "notes": "The EQL wiki has no Beastlord epic page yet, so there's nothing confirmed to collect. "
              "Add items here as they're found.", "items": []},
    {"id": "ber-epic", "cls": ["Berserker"], "kind": "epic", "name": "Berserker Epic Quest", "reward": "Berserker epic",
     "wiki": WIKI + "Berserker_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Gnashing Kobold Paw", "Gnashing Kobold, Stonebrunt Mountains (+1900, +2350)", u=True),
         _i("Skunk Scent Gland", "a skunk, Toxxulia Forest"),
     ]},
    {"id": "clr-epic", "cls": ["Cleric"], "kind": "epic", "name": "Cleric Epic Quest", "reward": "Water Sprinkler of Nem Ankh",
     "wiki": WIKI + "Cleric_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Lord Bergurgle's Crown", "Lord Bergurgle, Lake Rathetear"),
         _i("Lord Gimblox's Signet Ring", "Lord Gimblox, Solusek's Eye"),
     ]},
    {"id": "dru-epic", "cls": ["Druid"], "kind": "epic", "name": "Druid Epic Quest", "reward": "Nature Walker's Scimitar",
     "wiki": WIKI + "Druid_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Clean Lakewater", "Tainted Aquagoblin / Corrupted Shaman, Lake Rathetear", g="Cleansed Spirit of Antonica"),
         _i("Chunk of Tundra", "Tainted / Corrupted wooly mammoth, Everfrost", g="Cleansed Spirit of Antonica"),
         _i("Ancient Rock", "Tainted / Corrupted hill giant, Rathe Mountains", g="Cleansed Spirit of Antonica"),
         _i("Kedge Cave Crystals", "Tainted / Corrupted seahorse, Kedge Keep", g="Cleansed Spirit of Faydwer"),
         _i("Ocean of Tears Seavines", "Tainted / Corrupted seafury cyclops, Ocean of Tears", g="Cleansed Spirit of Faydwer"),
         _i("Green Heartwood Branch", "3 Brownie Scouts, then Corrupted brownie, Lesser Faydark", g="Cleansed Spirit of Faydwer"),
         _i("Chilled Tundra Root", "Forage, Everfrost", "forage", g="Forage"),
         _i("Ripened Heartfruit", "Forage, Greater Faydark", "forage", g="Forage"),
         _i("Speckled Molded Mushroom", "Forage, Innothule Swamp", "forage", g="Forage"),
         _i("Sweetened Mudroot", "Forage, Misty Thicket", "forage", g="Forage"),
     ]},
    {"id": "enc-epic", "cls": ["Enchanter"], "kind": "epic", "name": "Enchanter Epic Quest", "reward": "Staff of the Serpent",
     "wiki": WIKI + "Enchanter_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Shining Metallic Robes", "The ghoul arch magi, Lower Guk"),
         _i("Spoon", "Cazel, Oasis of Marr", u=True),
         _i("Charm", "Pick up in the Plane of Sky quest room (+1300, +560)", "collect"),
         _i("Sacrifice", "Pick up in the Plane of Sky quest room (+1300, +560)", "collect"),
         _i("Head of the Serpent", "Wraith of a Shissir, Plane of Fear", u=True),
         _i("Essence of a Vampire", "a forsaken revenant, Plane of Hate"),
     ]},
    {"id": "mag-epic", "cls": ["Magician"], "kind": "epic", "name": "Magician Epic Quest", "reward": "Orb of Mastery",
     "wiki": WIKI + "Magician_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Torn Page of Magi`kot pg. 1", "enraged dread wolf, Kithicor Forest", g="Words of Magi`kot"),
         _i("Torn Page of Magi`kot pg. 2", "a tentacle terror, Estate of Unrest", g="Words of Magi`kot"),
         _i("Torn Page of Magi`kot pg. 3", "a bloodthirsty ghoul, Lower Guk", g="Words of Magi`kot"),
         _i("Torn Page of Mastery Earth", "A magician or an alligator, Najena / Temple of Cazic-Thule", g="Words of Mastery"),
         _i("Torn Page of Mastery Fire", "A magician or an alligator, Najena / Temple of Cazic-Thule", g="Words of Mastery"),
         _i("Torn Page of Mastery Water", "A magician or an alligator, Najena / Temple of Cazic-Thule", g="Words of Mastery"),
         _i("Torn Page of Mastery Wind", "A magician or an alligator, Najena / Temple of Cazic-Thule", g="Words of Mastery"),
         _i("A Shovel", "A magician or an alligator, Najena / Temple of Cazic-Thule", g="Shovel of Ponz"),
         _i("Ruby", "Vendor", "buy", g="Shovel of Ponz"),
         _i("Gargoyle Eye", "Any gargoyle", g="Shovel of Ponz"),
         _i("Hill Giant Toes", "Any hill giant", g="Shovel of Ponz"),
         _i("A Broom", "A magician or an alligator, Najena / Temple of Cazic-Thule", g="Broom of Trilon"),
         _i("Star Ruby", "Vendor", "buy", g="Broom of Trilon"),
         _i("Griffon Feathers", "Any griffon", g="Broom of Trilon"),
         _i("Cyclops Toes", "Any cyclops", g="Broom of Trilon"),
         _i("Power of Wind", "a gypsy dancer, Mistmoore Castle"),
         _i("Power of Earth", "A Fairy Guard, Lesser Faydark"),
         _i("Power of Fire", "Lava / Blazing elemental, Solusek's Eye", u=True),
         _i("Blazing Wand", "Undertow, Kedge Keep"),
         _i("Staff of Elemental Mastery: Earth", "Magi P`Tasa (raid), Plane of Hate"),
         _i("Staff of Elemental Mastery: Water", "Phinigel Autropos (raid), Kedge Keep"),
         _i("Crown of Elemental Mastery", "Island 7 trash, Plane of Sky"),
         _i("Elemental Binder", "Elementals, The Hole"),
         _i("Pegasus Feather Cloak", "Quillmane, South Karana"),
     ]},
    {"id": "mnk-epic", "cls": ["Monk"], "kind": "epic", "name": "Monk Epic Quest", "reward": "Celestial Fists",
     "wiki": WIKI + "Monk_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Needle of the Void", "Monks of the Whistling Fist quest", "quest", g="Monks of the Whistling Fist"),
         _i("Rare Robe Pattern", "Monks of the Whistling Fist quest", "quest", g="Monks of the Whistling Fist"),
         _i("Code of Zan Fi", "Targin the Rock, Nagafen's Lair"),
         _i("The Idol", "Raster of Guk, Lower Guk"),
         _i("Purple Headband", "Monk headband quests", "quest", g="Headband"),
         _i("Gnoll Pup Scalp", "a gnoll pup", q=4, g="Headband"),
         _i("Putrid Rib Bone", "a putrid skeleton, Qeynos Hills", q=3, g="Headband"),
         _i("Blackburrow Gnoll Pelt", "Gnolls, Blackburrow", q=2, g="Headband"),
         _i("Blackburrow Gnoll Skin", "Gnolls, Blackburrow", g="Headband"),
         _i("Dareb's Skull", "High Shaman Phido, South Karana", g="Headband"),
         _i("Head of Shen", "High Shaman Grisok, South Karana", g="Headband"),
         _i("Head of Ghanex Drah", "Ghanex Drah, South Karana", g="Headband"),
         _i("Skull of Jhen`Tra", "a gnoll embalmer, Lake Rathetear", g="Headband"),
         _i("Dagger of Marnek", "the thaumaturgist, Befallen", g="Headband"),
         _i("Zaharn's Coronet", "High Priest Zaharn, Permafrost", g="Headband"),
         _i("Red Sash of Order", "Monk sash quests (Velan Torresk / Reyia Beslin, West Freeport)", "quest", g="Sash"),
         _i("Deathfist Pawn Scalp", "a deathfist pawn, West Freeport", q=2, g="Sash"),
         _i("Snake Fang", "Any snake", g="Sash"),
         _i("Bone Chips", "Any skeleton", g="Sash"),
         _i("Deathfist Slashed Belt", "Orc centurion (Deathfist), East Commons", g="Sash"),
         _i("Giant Snake Rattle", "a darkweed snake, East Commons", g="Sash"),
         _i("Desert Tarantula Chitin", "a desert tarantula, North Ro", g="Sash"),
         _i("Legionnaire's Bracer", "orc legionnaire, Crushbone", g="Sash"),
         _i("Greater Lightstone", "a will-o-wisp", g="Sash"),
         _i("Cutthroat Insignia Ring", "a Dervish cutthroat, North Ro", g="Sash"),
         _i("Blackened Sapphire", "Ekeros, Najena", g="Sash"),
         _i("Blackened Wand", "Priest Amiaz, Befallen", g="Sash"),
         _i("Shadow Wolf Pelt", "Shadow wolves", g="Robe of the Lost Circle"),
         _i("Silk Swatch", "Spiders / vendor", g="Robe of the Lost Circle"),
         _i("Gather Shadows", "Spell scroll", "buy", g="Robe of the Lost Circle"),
         _i("Shadow Silk", "Tailoring 36: Shadow Wolf Pelt + Silk Swatch + Gather Shadows", "craft", g="Robe of the Lost Circle"),
         _i("Jonthan's Whistling Warsong", "Monk quest item", "quest", g="Robe of the Lost Circle"),
         _i("Robe of the Lost Circle", "Tailoring (no fail): Shadow Silk + Warsong + Rare Robe Pattern + Needle of the Void", "craft", g="Robe of the Lost Circle"),
     ]},
    {"id": "nec-epic", "cls": ["Necromancer"], "kind": "epic", "name": "Necromancer Epic Quest", "reward": "Scythe of the Shadowed Soul",
     "wiki": WIKI + "Necromancer_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Flowing Black Robe", "Najena, Najena"),
         _i("Head of Sir Edwin Motte", "Sir Edwin Motte, Qeynos Hills"),
         _i("Eye of Innoruuk", "Dread, Fright or Terror (raid), Plane of Fear"),
         _i("Slime Blood of Cazic Thule", "Dread, Fright or Terror (raid), Plane of Fear"),
         _i("Silver Disc", "Island 2, Plane of Sky"),
         _i("Spiroc Feathers", "Island 3, Plane of Sky"),
         _i("Black Silk Cape", "Keeper of Souls, Plane of Sky"),
     ]},
    {"id": "pal-epic", "cls": ["Paladin"], "kind": "epic", "name": "Paladin Epic Quest", "reward": "Fiery Defender",
     "wiki": WIKI + "Paladin_Epic_Quest", "notes": EPIC_NOTE + " SoulFire has its own checklist (Zimel's Blades).", "items": [
         _i("Fiery Avenger", "The Fiery Avenger quest (finish first)", "quest"),
         _i("Ghoulbane", "The froglok shin lord, Upper Guk"),
         _i("SoulFire", "Zimel's Blades (SoulFire) quest", "quest"),
         _i("Torn, Burnt Book", "Lord Nagafen (raid), Nagafen's Lair"),
         _i("Torn, Frost Covered Book", "Lady Vox (raid), Permafrost"),
     ]},
    {"id": "rng-epic", "cls": ["Ranger"], "kind": "epic", "name": "Ranger Epic Quest", "reward": "Earthcaller and Swiftwind",
     "wiki": WIKI + "Ranger_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Swirling Sphere of Color", "An essence tamer, Plane of Sky"),
         _i("Shattered Emerald of Corruption", "Mini bosses (raid), Plane of Hate"),
         _i("Sweetened Mudroot", "Forage, Misty Thicket", "forage"),
         _i("Ripened Heartfruit", "Forage, Greater Faydark", "forage"),
         _i("Speckled Molded Mushroom", "Forage, Innothule Swamp", "forage"),
         _i("Chilled Tundra Root", "Forage, Everfrost", "forage"),
     ]},
    {"id": "rog-epic", "cls": ["Rogue"], "kind": "epic", "name": "Rogue Epic Quest", "reward": "Ragebringer",
     "wiki": WIKI + "Rogue_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Robe of the Kedge", "Phinigel Autropos (raid), Kedge Keep"),
         _i("Shining Metallic Robes", "The ghoul arch magi, Lower Guk"),
         _i("Mithril Two-Handed Sword", "The froglok king, Lower Guk"),
         _i("Fleshripper", "Solusek kobold king, Nagafen's Lair"),
         _i("Painbringer", "Kobold champion, Nagafen's Lair"),
         _i("Robe of the Ishva", "The Ishva Mal, Splitpaw"),
         _i("Robe of the Oracle", "Oracle of K`Arnon, Ocean of Tears"),
         _i("Gigantic Zweihander", "Karg Icebear, Everfrost Peaks"),
         _i("Stained Parchment Top", "Pickpocket Founy Jestands, North Kaladim", "quest", u=True),
         _i("Stained Parchment Bottom", "Pickpocket Tani N`Mar, Neriak Third Gate", "quest", u=True),
         _i("Book of Souls", "Pick up in Plane of Hate (-60, +325, 56)", "collect"),
     ]},
    {"id": "shd-epic", "cls": ["Shadow Knight"], "kind": "epic", "name": "Shadow Knight Epic Quest", "reward": "Innoruuk's Curse",
     "wiki": WIKI + "Shadow_Knight_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Decayed Chainmail", "Lizard crusader / ritualist, Temple of Cazic-Thule", g="Darkforge Breastplate"),
         _i("Decayed Breastplate", "Lizard crusader / ritualist, Temple of Cazic-Thule", g="Darkforge Breastplate"),
         _i("Enchanted Platinum Bar", "Buy and enchant", "craft", q=2, g="Darkforge Breastplate"),
         _i("Decayed Left Legplate", "Lizard crusader / ritualist, Temple of Cazic-Thule", g="Darkforge Greaves"),
         _i("Decayed Right Legplate", "Lizard crusader / ritualist, Temple of Cazic-Thule", g="Darkforge Greaves"),
         _i("Melatite", "Clockworks, Solusek's Eye", q=2, g="Darkforge Greaves"),
         _i("Decayed Helm", "Lizard crusader / ritualist, Temple of Cazic-Thule", g="Darkforge Helm"),
         _i("Decayed Visor", "Lizard crusader / ritualist, Temple of Cazic-Thule", g="Darkforge Helm"),
         _i("Damaged Militia Helm", "Freeport guards", q=2, g="Darkforge Helm"),
         _i("Ghoulbane", "The froglok shin lord, Upper Guk"),
         _i("Soul Leech", "Cazic Thule (raid), Plane of Fear"),
         _i("Dark Sword of Blood", "Cazic Thule (raid), Plane of Fear"),
         _i("Blade of Abrogation", "Various, Plane of Sky"),
         _i("Drake Spine", "Rharzar, Rathe Mountains", u=True),
         _i("Decrepit Hide", "an ashenbone drake, Plane of Hate"),
         _i("Cell Key", "A mimic, The Hole"),
     ]},
    {"id": "shm-epic", "cls": ["Shaman"], "kind": "epic", "name": "Shaman Epic Quest", "reward": "Spear of Fate",
     "wiki": WIKI + "Shaman_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Envy", "Glaron the Wicked, Rathe Mountains", u=True),
         _i("Woe", "Glaron the Wicked, Rathe Mountains", u=True),
         _i("Marr's Promise", "Tabien the Goodly, Rathe Mountains", u=True),
         _i("Black Dire Pelt", "Black Dire, Mistmoore Castle", u=True),
     ]},
    {"id": "war-epic", "cls": ["Warrior"], "kind": "epic", "name": "Warrior Epic Quest", "reward": "Jagged Blade of War",
     "wiki": WIKI + "Warrior_Epic_Quest", "notes": EPIC_NOTE, "items": [
         _i("Unjeweled Dragon Head Hilt", "Pick up in Lake Rathetear (+2513, +920)", "collect"),
         _i("Ball of Everliving Golem", "Fright, Dread or Terror (raid), Plane of Fear"),
         _i("Block of Permafrost", "An ice giant (raid), Permafrost"),
         _i("Red Dragon Scales", "Lord Nagafen (raid), Nagafen's Lair"),
         _i("Spiroc Wingblade", "The Spiroc Lord, Plane of Sky"),
         _i("Heart of Frost", "A goblin wizard, Permafrost"),
         _i("Hand of the Maestro", "Hand of the Maestro, Plane of Hate"),
     ]},
    {"id": "wiz-epic", "cls": ["Wizard"], "kind": "epic", "name": "Wizard Epic Quest", "reward": "Staff of the Four",
     "giver": "Solomen, Temple of Solusek Ro", "level": "46+",
     "wiki": WIKI + "Wizard_Epic_Quest",
     "notes": "Post-revamp route from the EQL wiki. The checklist page notes the Blue Crystal Staff "
              "may not be dropping yet.", "items": [
         _i("Ro's Breath", "Buy from Dargon, Halas, outside the Shaman guild (~900-1100pp)", "buy"),
         _i("Arantir's Ring", "From Arantir/Dargon; give to Challice, Felwithe Paladin guild basement", "quest"),
         _i("Blue Crystal Staff", "Phinigel Autropos (raid), Kedge Keep"),
         _i("Gnarled Staff", "Venril Sathir, Karnor's Castle"),
         _i("Golem Sprocket", "Kandin Firepot, Butcherblock (say \"what oil?\"); give to the broken golem in Fear", "quest"),
         _i("Green Oil", "The enraged golem, Plane of Fear"),
         _i("Staff of Gabstik", "Kandin Firepot, after giving him the Green Oil", "turnin"),
         _i("Note to Arantir", "Kandin Firepot, with the Staff of Gabstik", "turnin"),
         _i("Magically Sealed Bag", "Arantir, after handing him the three staves; give to Solomen", "turnin"),
     ]},
]

# ------------------------------------------------------------------ era notes
# Epics came out with Ruins of Kunark, and so do the quests that start in or need
# Kunark zones. They get a banner in the app.
PRE_KUNARK = "Not available pre-Kunark"

QUESTS[3:3] = QUESTS_MORE          # after the three hand-picked examples, before the epics
for _q in QUESTS:
    if _q.get("kind") == "epic":
        _q["era"] = "Kunark"
    _q.setdefault("era", "Classic")
    if _q["era"] == "Kunark":
        _q["banner"] = PRE_KUNARK

CLASSES = ["Bard", "Beastlord", "Berserker", "Cleric", "Druid", "Enchanter", "Magician", "Monk", "Necromancer",
           "Paladin", "Ranger", "Rogue", "Shadow Knight", "Shaman", "Warrior", "Wizard"]

# Wiki category of every class's quests, for browsing / importing more.
def class_category(cls):
    return WIKI + "Category:" + cls.replace(" ", "_") + "_Quests"
