"""Plane of Sky class tests for EverQuest Legends.

Source: EQLWiki only - each class's "<Class> Plane of Sky Tests" page on eqlwiki.com,
checked 12 October 2026 (see PAGES below). Nothing here comes from other wikis.
Completing every test for a class unlocks that class as a Primary Class.

Format per quest:  (quest name, trigger word, reward, wind rune, [items])
Each item is "Item Name@source" where source is a key of SOURCES.
Edit freely if the wiki changes - the app reloads this on start.
"""

SOURCES = {
    "2": "Island 2 - Protector of Sky",
    "3": "Island 3 - Gorgalosk",
    "4": "Island 4 - Keeper of Souls",
    "5": "Island 5 - The Spiroc Lord",
    "6": "Island 6 - Bazzt Zzzt",
    "7": "Island 7 - Sister of the Spire",
    "7t": "Island 7 - trash mobs",
    "8": "Island 8 - Eye of Veeshan",
    "E": "Efreeti cycle (Noble Dojorn / Overseer of Air / Hand of Veeshan)",
    "rune": "Any Plane of Sky mob (random)",
}

WIND_RUNES = ["Azia", "Beza", "Caza", "Dena", "Ena", "Fana", "Geza", "Heda",
              "Izah", "Jaka", "Kala", "Lena", "Meda", "Neza", "Ozah"]

CLASSES = {
    'Bard': ('BRD', 'Cilin Spellsinger', [
        ('Test of Tone', 'tone', 'Mask of Song', 'Meda', ['Light Woolen Mask@3']),
        ('Test of Voice', 'voice', 'Mantle of the Songweaver', 'Kala', ['Light Woolen Mantle@4']),
        ('Test of Pitch', 'pitch', "Ervaj's Flute of Flight", 'Azia', ['Crude Wooden Flute@5']),
        ('Test of Wind', 'wind', 'Amulet of the Fae', 'Caza', ['Amulet of Woven Hair@6']),
        ('Test of Brass', 'brass', "Denon's Horn of Disaster", 'Fana', ['Glowing Diamond@7', 'Efreeti War Horn@E']),
        ('Test of Harmony', 'harmony', 'Spear of Harmony', 'Heda', ['Nebulous Diamond@8', 'Efreeti War Spear@E']),
    ]),
    'Beastlord': ('BST', 'Animist Kratho', [
        ('Test of Aviak', 'aviak', 'Spiroc Beak Earcuff', 'Beza', ["Spiroc Elder's Totem@5"]),
        ('Test of Azarack', 'azarack', 'Azarack Skin Wristwraps', 'Heda', ['Azarack Skin@2']),
        ('Test of Claw', 'claw', 'Windhowl', 'Izah', ['Sphinx Claw@7', 'Mithril Bands@8', 'Brass Knuckles@E']),
        ('Test of Harpy', 'harpy', 'Griffon-Hide Armguards', 'Kala', ['Leather Cord@3']),
        ('Test of Wind', 'wind', 'Diaphonous Waistband', 'Geza', ['Silken Wrap@6']),
    ]),
    'Berserker': ('BER', 'Stragen The Hewer', [
        ('Test of Sharpness', 'sharpness', 'Skycleaver', 'Jaka', ['Djinni War Blade@7', 'Efreeti Standard@E']),
        ('Test of Will', 'will', 'Molten Coil', 'Ena', ['Pulsating Ruby@6']),
        ('Test of Ferocity', 'ferocity', 'Sash of Ferocity', 'Ozah', ['High Quality Raiment@5']),
        ('Test of Burden', 'burden', 'Shroud of the Sky', 'Azia', ['Feathered Cape@3']),
        ('Test of Blood', 'blood', 'Blood-Drawn Runes', 'Lena', ['Azarack Blood@2']),
        ('Test of Fools Errand', 'fools errand', 'Cudgel of the Fool', 'Dena', ["Jester's Mask@4", 'Efreeti Great Staff@8']),
    ]),
    'Cleric': ('CLR', 'Josin Faithbringer', [
        ('Test of Courage', 'courage', 'Truewind Earring', 'Lena', ['Silver Hoop@3']),
        ('Test of Skill', 'skill', 'Aegis of the Wind', 'Meda', ['Small Shield@4']),
        ('Test of Protection', 'protection', 'Pauldrons of Piety', 'Caza', ['Shiny Pauldrons@5']),
        ('Test of Resolution', 'resolution', 'Necklace of Resolution', 'Neza', ['Silvered Spiroc Necklace@6']),
        ('Test of Theurgy', 'theurgy', "Theurgist's Star", 'Kala', ['Djinni Aura@7', 'Efreeti Mace@E']),
        ('Test of The Weak', 'weak', 'Baton of the Sky', 'Ena', ['Mithril Bands@8', 'Efreeti Standard@E']),
    ]),
    'Druid': ('DRU', 'Strandar Pinemist', [
        ('Test of Wolf', 'wolf', 'Drake-Hide Mask', 'Meda', ['Worn Leather Mask@3']),
        ('Test of Bear', 'bear', "Nature Walker's Mantle", 'Kala', ['Mantle of Woven Grass@4']),
        ('Test of Tree', 'tree', 'Shillelagh', 'Azia', ['Spiroc Battle Staff@5', 'Efreeti Statuette@E']),
        ('Test of The Bee', 'bee', 'Honeycomb Belt', 'Dena', ['Divine Honeycomb@6']),
        ('Test of Eagle', 'eagle', 'Spiroc Banisher Focus', 'Ena', ['Ethereal Ruby@7', "Spiroc Elder's Totem@5"]),
        ('Test of Nature', 'nature', 'Espri', 'Izah', ['Storm Sky Opal@8', 'Efreeti Scimitar@E']),
    ]),
    'Enchanter': ('ENC', 'Enchanter Jolas', [
        ('Test of Illusion', 'illusion', 'Sphinx Hair Cord', 'Meda', ['Finely Woven Cloth Cord@3']),
        ('Test of Dislocation', 'dislocation', 'Earring of Displacement', 'Caza', ['Adamantium Earring@6']),
        ('Test of Metamorphism', 'metamorphism', "Wind Walker's Mantle", 'Ozah', ['Light Cloth Mantle@4']),
        ('Test of Deception', 'deception', 'Ivory Mask', 'Beza', ['Silken Mask@5']),
        ('Test of Memorization', 'memorization', 'Necklace of Whispering Winds', 'Fana', ['Glowing Necklace@7']),
        ('Test of Incapacitation', 'incapacitation', 'Rod of the Protecting Winds', 'Izah', ['Large Sky Sapphire (Enchanter)@8', 'Efreeti Wind Staff@E']),
    ]),
    'Magician': ('MAG', 'Magus Frinon', [
        ('Test of Clarification', 'clarification', 'Bracelet of Clarification', 'Lena', ['Feathered Cape@3']),
        ('Test of Empowerment', 'empowerment', 'Mask of Empowerment', 'Neza', ['Ceramic Mask@4']),
        ('Test of Shielding', 'shielding', 'Gold White Pendant', 'Azia', ['Golden Coffer@5']),
        ('Test of Summoning', 'summoning', 'Drake-Hide Amice', 'Dena', ['Large Diamond@6']),
        ('Test of Interpretation', 'interpretation', 'Duennan Shielding Ring', 'Ena', ['Golden Efreeti Ring@7']),
        ('Test of Gesticulation', 'gesticulation', 'Staff of The Magister', 'Jaka', ['Hazy Opal@8', 'Efreeti Magi Staff@E']),
        ('Test of Displacement', 'displacement', 'Staff of Elemental Mastery: Air', 'Heda', ['Crown of Elemental Mastery@7t', 'Large Opal@8', 'Djinni Stave@7']),
    ]),
    'Monk': ('MNK', 'Holwin', [
        ('Test of Strength', 'strength', 'Back Straps of Mastery', 'Caza', ['Silken Strands@3']),
        ('Test of Sight', 'sight', "Ton Po's Eye Patch", 'Geza', ['Cracked Leather Eyepatch@4']),
        ('Test of Speed', 'speed', 'Sandals of Alacrity', 'Jaka', ['Dove Slippers@5']),
        ('Test of Tears', 'tears', "Ton Po's Shoulder Wraps", 'Beza', ['Silken Wrap@6']),
        ('Test of Fists', 'fists', "Wu's Fist of Mastery", 'Neza', ['Brass Knuckles@E', 'Nebulous Sapphire@7']),
        ('Test of Tranquility', 'tranquility', 'Golden Sash of Tranquility', 'Lena', ['Tear of Quellious@8']),
    ]),
    'Necromancer': ('NEC', 'Drakis Bloodcaster', [
        ('Test of Flight', 'flight', 'Bloody Griffon-Hide Wrist Guard', 'Lena', ["Griffon's Beak@3"]),
        ('Test of Power', 'power', 'Cloak of Spiroc Feathers', 'Neza', ['Black Silk Cape@4']),
        ('Test of Mind', 'mind', 'Bloodsoaked Raiment', 'Ozah', ['Fine Cloth Raiment@5']),
        ('Test of Heart', 'heart', 'Sphinx Heart Amulet', 'Azia', ['Pulsating Ruby@6']),
        ('Test of Hands', 'hands', 'Gorgon Head Staff', 'Fana', ['Gorgon Head@3', 'Efreeti Great Staff@E']),
        ('Test of Finger', 'finger', 'Band of Wailing Winds', 'Caza', ['Ring of Veeshan@7']),
    ]),
    'Paladin': ('PAL', 'Dason Goldblade', [
        ('Test of Compassion', 'compassion', 'Truvinan', 'Izah', ['Efreeti Zweihander@E', 'Large Sky Diamond@8']),
        ('Test of Sacrifice', 'sacrifice', 'Aldryn, Blade of the Ocean', 'Ozah', ['Bixie Sword Blade@6']),
        ('Test of Love', 'love', 'Thelvorn, Blade of Light', 'Geza', ['Sphinx Claw@7', 'Golden Hilt@7t']),
        ('Test of Spirit', 'spirit', 'Girdle of Faith', 'Lena', ['Ivory Sky Diamond@5']),
    ]),
    'Ranger': ('RNG', 'Ranger Spirit', [
        ('Test of Body', 'body', 'Griffon Talon Necklace', 'Meda', ['Griffon Talon@3']),
        ('Test of Defense', 'defense', 'Dark Cloak of the Sky', 'Neza', ['Fine Velvet Cloak@4']),
        ('Test of The Earth', 'elemental earth', "Earthshaker's Mantle", 'Kala', ['Spiroc Earth Totem@5']),
        ('Test of Thunder', 'elemental thunder', 'Thunderforged Earring', 'Azia', ['White Gold Earring@6']),
        ('Test of Blade', 'blade', 'Arydryidriyorn', 'Ena', ['Circlet of Brambles@7', 'Efreeti Long Sword@E']),
        ('Test of Ranged Attack', 'ranged attack', 'Windstriker', 'Heda', ['Shimmering Pearl@8', 'Efreeti War Bow@E']),
    ]),
    'Rogue': ('ROG', 'Thalik Silenthand', [
        ('Test of Thievery', 'thievery', 'Wispy Choker of Vigor', 'Ozah', ['Inlaid Choker@3']),
        ('Test of Trickery', 'trickery', "Renard's Belt of Quickness", 'Izah', ['Sphinxian Circlet@7']),
        ('Test of Silence', 'silence', 'Griffon Wing Spaulders', 'Ena', ['Spiroc Sky Totem@5']),
        ('Test of Cunning', 'cunning', 'Crystal Mask', 'Dena', ["Jester's Mask@4"]),
        ('Test of Stealth', 'stealth', 'Shimmering Bracer of Protection', 'Geza', ['Fine Wool Cloak@6']),
        ('Test of Deception', 'deception', 'Thornstinger', 'Jaka', ['Bixie Stinger@6', 'Bloodsky Sapphire@8']),
    ]),
    'Shadow Knight': ('SHD', 'Sarkis Ebonblade', [
        ('Test of Bash', 'bash', 'Amulet of the Sphinx Eye', 'Ozah', ['Finely Crafted Amulet@3']),
        ('Test of Smash', 'smash', 'Crimson Ring of the Djinni', 'Beza', ['Silvery Ring@4']),
        ('Test of Slash', 'slash', 'Pegasus-Hide Belt', 'Dena', ['Finely Woven Cloth Belt@5']),
        ('Test of Disempowerment', 'disempowerment', 'Blood Sky Face Plate', 'Fana', ['Rusted Pauldrons@6']),
        ('Test of Envenoming', 'envenoming', 'Obtenebrate Mithril Guard', 'Heda', ['Efreeti War Shield@E']),
        ('Raising of the Dead', 'raising of the dead', 'Pearlescent Pauldrons', 'Izah', ['Sphinxian Ring@7', 'Fae Pauldrons@8']),
        ('Test of Necropotence', 'necropotence', 'Khyldorn the Blood Drinker', 'Kala', ['Blood Sky Ruby@8', 'Efreeti War Axe@E']),
    ]),
    'Shaman': ('SHM', 'Medicine Man Veetra', [
        ('Test of Might', 'might', 'Amulet of the Fang', 'Meda', ['Leather Cord@3']),
        ('Test of Health', 'health', 'Bracelet of the Spirits', 'Kala', ['Ceremonial Belt@5']),
        ('Test of Sight', 'sight', 'Fairy-Hide Mantle', 'Beza', ['Light Damask Mantle@5']),
        ('Test of Shrink', 'shrink', 'Warhammer of the Wind', 'Ena', ['Corrosive Venom@6', 'Efreeti War Club@E']),
        ('Test of Snake', 'snake', 'Vermilion Sky Ring', 'Heda', ['Bixie Essence@6', 'Spiritualist`s Ring@7']),
        ('Test of The Witch Doctor', 'witch doctor', 'Garduk', 'Geza', ['Symbol of Veeshan@8', 'Efreeti War Maul@E']),
    ]),
    'Warrior': ('WAR', 'Torgon Blademaster', [
        ('Test of Skill', 'skill', 'Azure Ruby Ring', 'Neza', ['Azure Ring@3']),
        ('Test of Strength', 'strength', 'Runed Wind Amulet', 'Azia', ['Stone Amulet@4']),
        ('Test of Force', 'force', 'Pauldrons of the Blue Sky', 'Beza', ['Spiroc Air Totem@5']),
        ('Test of Think', 'think', 'Belt of the Four Winds', 'Fana', ['Wind Tablet@6']),
        ('Test of Smash', 'smash', 'Dagas', 'Jaka', ['Djinni War Blade@7']),
        ('Test of Bash', 'bash', 'Fangol', 'Dena', ['Ethereal Emerald@8']),
    ]),
    'Wizard': ('WIZ', 'Wizard Schrock', [
        ('Test of Concentration', 'concentration', "Augmentor's Mask", 'Dena', ['Grey Damask Cloak@3']),
        ('Test of Focus', 'focus', "Al`Kabor's Cap of Binding", 'Fana', ['Woven Skull Cap@4']),
        ('Test of Meditation', 'meditation', 'Raiment of Thunder', 'Geza', ['High Quality Raiment@5']),
        ('Test of Conception', 'conception', 'Solidate Mithril Ring', 'Izah', ['Box of Winds@6', 'Efreeti Statuette@E']),
        ('Test of Visualization', 'visualization', 'Amulet of the Void', 'Jaka', ['Amethyst Amulet@7']),
        ('Test of Preparation', 'preparation', "Nargon's Staff", 'Caza', ['Large Sky Lapis@8', 'Efreeti War Staff@E']),
    ]),
}

# EQLWiki page for each class's tests.
PAGES = {cls: "https://eqlwiki.com/" + cls.replace(" ", "_") + "_Plane_of_Sky_Tests" for cls in CLASSES}

# Extra reward names that also prove a test was done (tests with more than one reward).
# EQLWiki also lists Efreeti Belt / Gem of Invigoration / Efreeti Battle Axe beside three
# Warrior rewards, but those drop or come from other tests too, so they don't prove a turn-in.
EXTRA_REWARDS = {
    ('Beastlord', 'Test of Claw'): ['Spirit Render'],
}
