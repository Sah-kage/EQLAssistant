"""Race unlocks for EverQuest Legends.

Source: EQLWiki only - each race's page on eqlwiki.com ("Unlock Conditions",
starting city, class choices), the "Aid the Kerrans of Kerra Isle" task page, the Lake Nerius
quest pages for the Half Dark Elf (Something Fishy ... Unfortunate News),
and the community "Alanna's Race Unlock Guide" (User:Alanna on EQLWiki) for
the suggested ways to raise each faction. Checked 12 October 2026.

General rules (from EQLWiki):
  - A race unlocks through its achievement in the Races section of Untapped Potential.
  - Faction races need maximum faction with each listed faction (the guide says
    +2000 personal faction). They don't all have to be maxed at the same time.
  - Starting a character as a race unlocks it.
  - A Race Unlock Token (store) skips the faction requirements.
"""

WIKI = "https://eqlwiki.com/"
GUIDE = WIKI + "User:Alanna/Alanna%27s_Race_Unlock_Guide"

# name, wiki page, starting city, primary class choices,
# unlock: {"factions": [...]} | {"options": {label: [factions]}} | {"any_race": [...]} | {"task": ...}
# tip: suggested way to raise the factions (Alanna's Race Unlock Guide, EQLWiki)
RACES = [
    {"name": "Barbarian", "page": "Barbarian", "city": "Halas",
     "classes": ["Beastlord", "Berserker", "Rogue", "Shaman", "Warrior"],
     "unlock": {"factions": ["Rogues of the White Rose", "Wolves of the North", "Merchants of Halas"]},
     "tip": "Lion Meat Shipment quest 200 times, then turn the 200 Lion Delight in to Iceberg in Everfrost Peaks. "
            "Alternatives: Gnoll Bounty (Lysbith McNaff, Halas), Mammoth Calf Hides (Cappi McTarnigal, Halas)."},
    {"name": "Dark Elf", "page": "Dark_Elf", "city": "Neriak",
     "classes": ["Cleric", "Enchanter", "Magician", "Necromancer", "Rogue", "Shadow Knight", "Warrior", "Wizard"],
     "unlock": {"factions": ["Dreadguard Inner", "Dreadguard Outer", "Dark Bargainers"]},
     "tip": "Bottle of Red Wine quest 400 times, turned in to Lokar To`Biath in Neriak Third Gate. "
            "Alternative: Book of Turmoil Quest (about 1400pp)."},
    {"name": "Dwarf", "page": "Dwarf", "city": "Kaladim",
     "classes": ["Berserker", "Cleric", "Paladin", "Rogue", "Warrior"],
     "unlock": {"factions": ["Storm Guard", "Merchants of Kaladim", "Kazon Stormhammer"]},
     "tip": "Tumpy Tonics quest 400 times (Kiola Nuts from Cleonae Kalen plus Flasks of Water, to Trantor Everhot). "
            "Alternatives: Crushbone Shoulderpads, Crushbone Belts, Runnyeye Warbeads, Rat Pelts."},
    {"name": "Erudite", "page": "Erudite", "city": "Erudin and Paineel",
     "classes": ["Cleric", "Enchanter", "Magician", "Necromancer", "Paladin", "Shadow Knight", "Wizard"],
     "unlock": {"factions": ["Deepwater Knights", "High Council of Erudin", "Heretics"]},
     "tip": "Kobold Molars (Good) to Tiam Khonsir, kill Heretics in Paineel for Deepwater Knights, then The Painting. "
            "Alternatives: Sentinels (Heretics), Catman Alliance, Erud's Tonic, Sealed Letters, Wooden Shards."},
    {"name": "Froglok", "page": "Froglok", "city": "Lake Rathe",
     "classes": ["Cleric", "Monk", "Necromancer", "Paladin", "Rogue", "Shadow Knight", "Shaman", "Warrior",
                 "Wizard"],
     "unlock": {"factions": ["Protectors of Gukta", "Guktan Elders", "Guktan Suppliers"]},
     "tip": "800 Phosphorous Powder (high-level ghouls, Ruins of Old Guk) to Zok Zribb in Rathe Mountains. "
            "Alternative: Bone Chips to Dar Collector Reokar (everything except Guktan Suppliers)."},
    {"name": "Gnome", "page": "Gnome", "city": "Ak'Anon",
     "classes": ["Cleric", "Enchanter", "Magician", "Necromancer", "Paladin", "Shadow Knight", "Rogue", "Warrior",
                 "Wizard"],
     "unlock": {"factions": ["King Ak'Anon", "Gem Choppers", "Eldritch Collective"]},
     "tip": "Series C Black Boxes (first part) 400 times; needs Amiable with Gem Choppers to start. "
            "Alternatives: Necromancer Hunting, Minotaur Horns (Larkon Theardor), Vasty Deep Ale (Shondo Billin)."},
    {"name": "Half-Elf", "page": "Half-Elf", "city": "Freeport, Kelethin, Surefall Glade, Qeynos, Felwithe",
     "classes": ["Bard", "Druid", "Paladin", "Ranger", "Rogue", "Warrior"],
     "unlock": {"any_race": ["Human", "Wood Elf"]},
     "tip": "Unlocks with Human or Wood Elf."},
    {"name": "Half Dark Elf", "page": "Unfortunate_News", "city": "The Nektropos Undercroft",
     "classes": [],
     "unlock": {"task": {"name": "The Lake Nerius quest line", "page": "Something_Fishy",
                         "start": "Hail Nikko Canti in Lake Nerius",
                         "note": "Five quests in a row, tracked in your quest log. The last one, Unfortunate News, "
                                 "unlocks the race (achievement \"Race Unlock - Half Dark Elves\").",
                         "steps": [
                             ("Something Fishy",
                              "Nikko Canti, Lake Nerius: fish up 3 Fresh Fish, kill 2 large piranha (river south of "
                              "the lake) and a ghost gill for Defiled Fish Scales"),
                             ("Alchemical Solution",
                              "Dorian G`Wyn, Lake Nerius: Imp Blood and lava drake bile (Lavastorm), the Dusty "
                              "Scroll Case (West Freeport guard house), Ty'Klerr's Encoded Missive (Neriak Foreign "
                              "Quarter), then fish up a Fetid Lake Muck"),
                             ("What's going on here?",
                              "Lake Nerius: talk to Yelayna, Konro Strongfoot, Blergagh, Neuven F`Lok, "
                              "The Great Zultor and Nikko Canti"),
                             ("Call for Aid",
                              "Dorian G`Wyn: take his three letters to Sir Mollin (North Freeport), Pishtian F`Lok "
                              "(Neriak Commons bank) and Lord Lyfyx of Burwood (Temple of Solusek Ro)"),
                             ("Unfortunate News",
                              "Dorian G`Wyn: hand in A Curt Dismissal, Exorbitant Commission and Ordination of Might"),
                         ]}},
     "tip": "Newly added races start at level 1. Don't be kill-on-sight in Neriak and Freeport (invisibility, "
            "Guise of the Deceiver or sneak help). Binding near Dorian G`Wyn saves travel."},
    {"name": "Halfling", "page": "Halfling", "city": "Rivervale",
     "classes": ["Cleric", "Druid", "Paladin", "Ranger", "Rogue", "Warrior"],
     "unlock": {"factions": ["Guardians of the Vale", "Merchants of Rivervale", "Priests of Mischief"]},
     "tip": "Bandages for Honeybugger 400 times (Joogl Honeybugger, Misty Thicket) and 400 goblin kills in "
            "Runnyeye. Alternatives: Jillin's Stew, The Acolyte."},
    {"name": "High Elf", "page": "High_Elf", "city": "Felwithe",
     "classes": ["Cleric", "Enchanter", "Magician", "Paladin", "Wizard"],
     "unlock": {"factions": ["Keepers of the Art", "Merchants of Felwithe", "Clerics of Tunare"]},
     "tip": "Muffin for Pandos, Hogcaller's Inn (first step) and Bat Wings (Niola Impholder, South Felwithe), "
            "400 times each. Alternatives: Necromancer Hunting, Small Lanterns, Shark Meat."},
    {"name": "Human", "page": "Human", "city": "Freeport, Qeynos",
     "classes": ["Bard", "Cleric", "Druid", "Enchanter", "Magician", "Monk", "Necromancer", "Paladin", "Ranger",
                 "Rogue", "Shadow Knight", "Warrior", "Wizard"],
     "unlock": {"options": {
         "Freeport": ["Coalition of Tradefolk", "Freeport Militia", "Knights of Truth"],
         "Qeynos": ["Merchants of Qeynos", "Guards of Qeynos", "Corrupt Qeynos Guards"]}},
     "tip": "Freeport: Tonics for Groflah (Groflah Steadirt) and Message Intercept (Sir Lucan D`Lere). "
            "Qeynos: Rohand's Brandy (Captain Rohand) and Honey Mead for Trumpy (Trumpy Irontoe)."},
    {"name": "Iksar", "page": "Iksar", "city": "New Sebilis Expedition",
     "classes": ["Beastlord", "Monk", "Necromancer", "Shadow Knight", "Shaman", "Warrior"],
     "unlock": {"factions": ["New Sebilisian Expedition"]},
     "tip": "Metal Bits to Crusader Iktra in North Ro until Amiable, then Small Pieces of High Quality Ore until maxed."},
    {"name": "Kerran", "page": "Kerran", "city": "Kerra Isle",
     "classes": ["Bard", "Berserker", "Beastlord", "Druid", "Rogue", "Shaman", "Warrior"],
     "unlock": {"task": {"name": "Aid the Kerrans of Kerra Isle", "page": "Aid_the_Kerrans_of_Kerra_Isle",
                         "start": "Hail any class guild master",
                         "note": "Accept the task first: quests done before it is accepted don't count.",
                         "steps": [
                             ("The Luck of Allix", "Allix: an Ajrah Leaf"),
                             ("Health Potion", "Errrak Thickshank: Tiger Skin, Odd Kobold Paw, Snake Fang"),
                             ("Razortooth", "Feren: Razortooth's remains and 3 Scrrrumptious Fish Meat"),
                             ("Feskr's Supplies", "Feskr Drinkmaker: Kerran Fish Oil and a Fire Beetle Leg"),
                             ("Heretic's Toy", "Kerran tseq: smash a heretic's pet, bring the toy"),
                             ("Fish Dinner", "Roary Fishpouncer: a Raw Darkwater Piranha"),
                             ("First Test of Kejaar", "Shazda Asad: Erudin Emissary's head, Toxxulia Forest"),
                             ("Second Test of Kejaar", "Shazda Asad: Sentinel Creot's head, Toxxulia Forest"),
                             ("Fang Tooth", "Thalith Mamluk: 2 wharf rats and Fang Tooth, a Sharp Tooth"),
                             ("Something is Wrrrong", "The Kerran Sha`rr: the Desecrated Kejaar Totem"),
                             ("This Means Warrr", "The Kerran Sha`rr: a Heretic's orders, Tiger Training Pits"),
                             ("Skunk Scent Gland", "Urkath Greyface: a Skunk Scent Gland, Toxxulia Forest"),
                         ]}},
     "tip": ""},
    {"name": "Ogre", "page": "Ogre", "city": "Oggok",
     "classes": ["Beastlord", "Berserker", "Shadow Knight", "Shaman", "Warrior"],
     "unlock": {"factions": ["Oggok Guards", "Clurg", "Merchants of Ogguk"]},
     "tip": "Very slow. About 4000 muffins (Muffin Crates via Gretta Mottle, South Kaladim) to an innkeeper in "
            "The Feerrott or Oggok. Alternatives: Bags of Bread Loaves, Stein of Moggok."},
    {"name": "Troll", "page": "Troll", "city": "Grobb",
     "classes": ["Beastlord", "Berserker", "Shadow Knight", "Shaman", "Warrior"],
     "unlock": {"factions": ["Da Bashers", "Grobb Merchants", "Dark Ones"]},
     "tip": ""},
    {"name": "Wood Elf", "page": "Wood_Elf", "city": "Kelethin",
     "classes": ["Bard", "Druid", "Ranger", "Rogue", "Warrior"],
     "unlock": {"factions": ["Emerald Warriors", "Soldiers of Tunare", "Kelethin Merchants"]},
     "tip": ""},
]

for _r in RACES:
    _r["wiki"] = WIKI + _r["page"]
    t = _r["unlock"].get("task")
    if t:
        t["wiki"] = WIKI + t["page"]
