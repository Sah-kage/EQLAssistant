"""Class data for spotting what classes your group members are.

Source: EQLWiki only (eqlwiki.com) - the class list (Classes page) and each
class's spell page (<Class>_Spells, Shadowknight_Spells, Bard_Spells), damage
and healing spells. Checked 13 October 2026.

EverQuest Legends characters have three classes, so a player can show spells
from up to three of these lists.
"""

CLASSES = ["Bard", "Beastlord", "Berserker", "Cleric", "Druid", "Enchanter", "Magician", "Monk", "Necromancer",
           "Paladin", "Ranger", "Rogue", "Shadow Knight", "Shaman", "Warrior", "Wizard"]

# /who shows a class, a short code, or (at high level) a title
ALIASES = {
    "war": "Warrior", "clr": "Cleric", "pal": "Paladin", "rng": "Ranger", "shd": "Shadow Knight",
    "sk": "Shadow Knight", "dru": "Druid", "mnk": "Monk", "brd": "Bard", "rog": "Rogue", "shm": "Shaman",
    "nec": "Necromancer", "wiz": "Wizard", "mag": "Magician", "enc": "Enchanter", "bst": "Beastlord",
    "ber": "Berserker", "shadowknight": "Shadow Knight", "mage": "Magician", "necro": "Necromancer",
    "ench": "Enchanter", "bl": "Beastlord", "zerker": "Berserker",
    # level titles
    "champion": "Warrior", "myrmidon": "Warrior", "warlord": "Warrior",
    "vicar": "Cleric", "templar": "Cleric", "high priest": "Cleric",
    "cavalier": "Paladin", "knight": "Paladin", "crusader": "Paladin",
    "pathfinder": "Ranger", "outrider": "Ranger", "warder": "Ranger",
    "reaver": "Shadow Knight", "revenant": "Shadow Knight", "grave lord": "Shadow Knight",
    "wanderer": "Druid", "preserver": "Druid", "hierophant": "Druid",
    "disciple": "Monk", "master": "Monk", "grandmaster": "Monk",
    "minstrel": "Bard", "troubadour": "Bard", "virtuoso": "Bard",
    "rake": "Rogue", "blackguard": "Rogue", "assassin": "Rogue",
    "mystic": "Shaman", "luminary": "Shaman", "oracle": "Shaman",
    "heretic": "Necromancer", "defiler": "Necromancer", "warlock": "Necromancer",
    "channeler": "Wizard", "evoker": "Wizard", "sorcerer": "Wizard",
    "elementalist": "Magician", "conjurer": "Magician", "arch mage": "Magician",
    "illusionist": "Enchanter", "beguiler": "Enchanter", "phantasmist": "Enchanter",
    "primalist": "Beastlord", "animist": "Beastlord", "savage lord": "Beastlord",
    "brawler": "Berserker", "vehement": "Berserker", "rager": "Berserker",
}
for _c in CLASSES:
    ALIASES[_c.lower()] = _c


def _split(s):
    return [x.strip() for x in s.split(",") if x.strip()]


SPELLS_BY_CLASS = {
    "Wizard": _split(
        "Frost Bolt, Blast of Cold, Numbing Cold, Shock of Fire, Fingers of Fire, Fire Bolt, Icestrike, "
        "Column of Frost, Shock of Ice, Shock of Lightning, Firestorm, Frost Spiral of Al`Kabor, Project Lightning, "
        "Pillar of Fire, Flame Shock, Lightning Bolt, Force Snap, Fire Spiral of Al`Kabor, "
        "Garrison's Mighty Mana Shock, Tishan's Clash, Lightning Storm, Cast Force, Column of Lightning, Frost Shock, "
        "Inferno Shock, Energy Storm, Shock Spiral of Al`Kabor, Thunder Strike, Thunderclap, Circle of Force, "
        "Lava Storm, Ice Shock, Force Spiral of Al`Kabor, Lightning Shock, Force Strike, Frost Storm, Gravity Flux, "
        "Conflagration, Supernova, Enticement of Flame, Mana Ignition, Elnerick's Entombment of Ice, Markar's Clash, "
        "Wrath of Al`Kabor, Ice Comet, Mana Detonation"),
    "Cleric": _split(
        "Strike, Minor Healing, Light Healing, Ward Undead, Furor, Echo of Health, Word of Pain, Healing, "
        "Expulse Undead, Smite, Echoing Light, Word of Shadow, Celestial Remedy, Greater Healing, Holy Might, "
        "Ward Summoned, Dismiss Undead, Renewing Echo, Sermon of the Righteous, Word of Spirit, Expulse Summoned, "
        "Wrath, Celestial Health, Superior Healing, Word of Health, Force, Expel Undead, Tremor, Celestial Echo, "
        "Dismiss Summoned, Turning of the Unnatural, Word of Souls, Sacred Word, Promised Renewal, Banish Undead, "
        "Sacred Echo, Earthquake, Retribution, Celestial Healing, Word of Healing, Healing Light, Sound of Force, "
        "Expel Summoned, Word Divine"),
    "Druid": _split(
        "Burst of Flame, Minor Healing, Flame Lick, Ward Summoned, Grasping Roots, Burst of Fire, Whirling Wind, "
        "Invoke Lightning, Budding Heal, Ignite, Light Healing, Stinging Swarm, Sprouting Heal, Cascade of Hail, "
        "Expulse Summoned, Careless Lightning, Dizzying Wind, Healing, Flowering Heal, Ensnaring Roots, Tremor, "
        "Pogonip, Dismiss Summoned, Creeping Crud, Immolate, Combust, Greater Healing, Blooming Heal, Fury of Air, "
        "Earthquake, Lightning Strike, Drones of Doom, Expel Summoned, Regeneration, Healing Water, "
        "Enveloping Roots, Avalanche, Firestrike, Pack Regeneration, Nature's Renewal, Drifting Death, "
        "Blossoming Heal, Chloroplast, Banish Summoned, Dustdevil, Superior Healing, Engulfing Roots, "
        "Pack Chloroplast, Lightning Blast, Ice, Fire, Starfire, Upheaval, Efflorescing Heal"),
    "Shaman": _split(
        "Burst of Flame, Minor Healing, Sicken, Frost Rift, Tainted Breath, Light Healing, Spirit Strike, "
        "Snails Healing, Infectious Cloud, Impassivity, Healing, Affliction, Poison Storm, Regeneration, "
        "Frost Strike, Envenomed Breath, Tortoises Healing, Greater Healing, Nonchalance, Scourge, Winter's Roar, "
        "Shock of the Tainted, Curse, Gale of Poison, Venom of the Snake, Chloroplast, Spirit Salve, "
        "Blast of Poison, Slugs Healing, Odium, Blizzard Blast, Stoicism, Superior Healing, Shock of Venom, Plague, "
        "Envenomed Bolt, Kragg's Salve"),
    "Enchanter": _split(
        "Shallow Breath, Suffocating Sphere, Chaotic Feedback, Choke, Sanity Warp, Chaos Flux, Suffocate, Anarchy, "
        "Gravity Flux, Discordant Mind, Gasping Embrace"),
    "Magician": _split(
        "Burst of Flame, Fire Flux, Burn, Flame Bolt, Shock of Blades, Ward Summoned, Rain of Blades, "
        "Column of Fire, Shock of Flame, Rain of Fire, Bolt of Flame, Expulse Summoned, Flame Flux, "
        "Shock of Spikes, Dismiss Summoned, Rain of Spikes, Expel Summoned, Blaze, Cinder Bolt, Rain of Lava, "
        "Flame Arc, Shock of Swords, Banish Summoned, Rain of Swords, Lava Bolt, Elemental Maelstrom, "
        "Renew Elements, Renew Summoning, Refresh Summoning, Primal Remedy"),
    "Necromancer": _split(
        "Disease Cloud, Lifetap, Lifespike, Clinging Darkness, Poison Bolt, Ward Undead, Dark Empathy, Mend Bones, "
        "Cancelling of Life, Heat Blood, Engulfing Darkness, Lifedraw, Heart Flutter, Infectious Cloud, "
        "Hungry Earth, Shadow Compact, Negation of Life, Expulse Undead, Word of Shadow, Siphon Life, "
        "Shock of Poison, Renew Bones, Spirit Tap, Word of Spirit, Dooming Darkness, Eternities Torment, "
        "Dismiss Undead, Boil Blood, Vampiric Curse, Torbas' Acid Blast, Venom of the Snake, Scourge, "
        "Word of Souls, Chilling Embrace, Cessation of Life, Expel Undead, Drain Spirit, Dark Soul, Asystole, "
        "Ignite Bones, Incinerate Bones, Corporeal Empathy, Pact of Shadow, Auspice, Banish Undead, "
        "Insidious Retrogression, Ignite Blood, Cascading Darkness, Drain Soul, Torbas' Poison Blast, "
        "Envenomed Bolt"),
    "Paladin": _split(
        "Strike, Minor Healing, Ward Undead, Furor, Light Healing, Smite, Healing, Greater Healing, Expulse Undead, "
        "Wrath, Wave of Life, Holy Might, Ethereal Cleansing, Superior Healing, Dismiss Undead, Retribution, "
        "Flame of Light"),
    "Ranger": _split(
        "Minor Healing, Flame Lick, Burst of Fire, Grasping Roots, Invoke Lightning, Searing Arrow, Light Healing, "
        "Ward Summoned, Ignite, Disrupting Shot, Stinging Swarm, Flaming Arrow, Healing, Dismiss Summoned, "
        "Burning Arrow, Careless Lightning, Greater Healing, Swarm of Pain, Immolate, Ensnaring Roots, "
        "Scorching Arrow, Call of Flame"),
    "Beastlord": _split(
        "Minor Healing, Sharik's Replenishing, Blast of Frost, Light Healing, Sicken, Keshuval's Rejuvenation, "
        "Tainted Breath, Frost Dagger, Healing, Spirit Strike, Herikol's Soothing, Ice Spear, Greater Healing, "
        "Envenomed Breath, Yekan's Recovery, Malaria, Frost Shard, Spirit Salve, Vigor of Zehkes"),
    "Shadow Knight": _split(
        "Lifetap, Disease Cloud, Siphon Strength, Leering Corpse, Lifespike, Despair, Clinging Darkness, Fear, "
        "Bone Walk, Vampiric Embrace, Lifedraw, Scream of Hate, Grim Aura, Ward Undead, Cancelling of Life, "
        "Spook the Dead, Engulfing Darkness, Dark Empathy, Convoke Shadow, Scream of Pain, Heat Blood, "
        "Strengthen Death, Siphon Life, Restless Bones, Negation of Life, Terror of Darkness, Spear of Disease, "
        "Shroud of Hate, Heart Flutter, Spirit Tap, Scream of Death, Animate Dead, Expulse Undead, "
        "Voice of Darkness, Blood of Pain, Terror of Shadows, Dooming Darkness, Word of Spirit, Breath of the Dead, "
        "Summon Dead, Voice of Shadows, Life Leech, Scythe of Darkness, Spear of Pain, Dismiss Undead, "
        "Drain Spirit, Harmshield, Shroud of Pain"),
    "Bard": _split(
        "Chant of Battle, Chant of Magic, Chant of Flame, Chant of Frost, Chant of Venom, Chant of Plague, "
        "Chant of Chaos, Chords of Dissonance, Jaxan's Jig o` Vigor, Selo's Accelerando, Hymn of Restoration, "
        "Jonthan's Whistling Warsong, Kelin's Lugubrious Lament, Elemental Rhythms, Magical Monologue, "
        "Anthem de Arms, Cinda's Charismatic Carillon, Brusco's Boastful Bellow, Purifying Rhythms, "
        "Kelin's Lucid Lullaby, Song of Sustenance, Tarew's Aquatic Ayre, Guardian Rhythms, "
        "Denon's Disruptive Discord, Shauri's Sonorous Clouding, Largo's Melodic Binding, "
        "Cassindra's Chant of Clarity, Melanie's Mellifluous Motion, Alenia's Disenchanting Melody, "
        "Selo's Consonant Chain, Lyssa's Veracious Concord, Psalm of Warmth, Selo's Rhythm of Speed, "
        "Angstlich's Appalling Screech, Solon's Song of the Sirens, Crission's Pixie Strike, Psalm of Vitality, "
        "Fufil's Curtailing Chant, Amplification, Agilmente's Aria of Eagles, Cassindra's Chorus of Clarity, "
        "Psalm of Cooling, Lyssa's Solidarity of Vision, Cantata of Soothing, Denon's Dissension, "
        "Vilia's Verses of Celerity, Psalm of Purity, Tuyen's Chant of Flame, Solon's Bewitching Bravura, "
        "Katta's Song of Sword Dancing, Syvelian's Anti-Magic Aria, Sionachie's Dreams, "
        "Psalm of Mystic Shielding, McVaxius' Berserker Crescendo, Tuyen's Chant of Disease, "
        "Denon's Desperate Dirge, Cassindra's Elegy, Jonthan's Provocation, Aria of Asceticism, Rizlona's Embers, "
        "Tuyen's Chant of Frost, Niv's Melody of Preservation, Selo's Chords of Cessation, Shield of Songs, "
        "Selo's Accelerating Chorus, Verses of Victory, Melody of Ervaj, Tuyen's Chant of Poison"),
}


def spell_key(name):
    return (name or "").lower().replace("`", "'").replace("’", "'").strip()


SPELL_CLASSES = {}
for _cls, _spells in SPELLS_BY_CLASS.items():
    for _s in _spells:
        SPELL_CLASSES.setdefault(spell_key(_s), set()).add(_cls)

# melee skills and other tells. Weak ones (shared by several classes) only count when nothing better shows up.
ABILITIES = {
    "backstab": {"Rogue"},
    "frenzy": {"Berserker"},
    "sing": {"Bard"},
    "warder": {"Beastlord"},
    "bash": {"Warrior", "Paladin", "Shadow Knight", "Cleric"},
    "kick": {"Warrior", "Monk", "Ranger", "Beastlord", "Berserker"},
}
