#!/usr/bin/env python3
"""
STA 2e Combat Helper
====================

A Gamemaster helper for Star Trek Adventures 2nd Edition starship combat:
bridge stations and actions, dynamic task Difficulty, dice resolution,
damage / Shaken / breach handling, turn budgets and roster persistence.

Run from source:
    python main.py

Build a single Windows executable (run on Windows):
    pip install pyinstaller
    pyinstaller --onefile --windowed --name STA2e_Combat_Helper main.py
    -> dist/STA2e_Combat_Helper.exe

Only the Python standard library is used (tkinter / ttk).
"""

from __future__ import annotations

import copy
import datetime
import json
import os
import random
import re
import sys
from dataclasses import asdict, dataclass, field, fields

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

APP_NAME = "STA 2e Combat Helper"
APP_VERSION = "1.1.0"
SAVE_FORMAT_VERSION = 3


def app_dir() -> str:
    """Folder that holds the app: next to the .exe when frozen, else next to main.py."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


DATA_FILE = os.path.join(app_dir(), "sta2e_ships.json")

# =============================================================================
# Domain data (STA 2nd Edition)
# =============================================================================

SYSTEMS = ["Communications", "Computers", "Engines", "Sensors", "Structure", "Weapons"]
SYSTEM_ABBR = {"Communications": "Comms", "Computers": "Comp", "Engines": "Eng",
               "Sensors": "Sens", "Structure": "Struct", "Weapons": "Weap"}
DEPARTMENTS = ["Command", "Conn", "Engineering", "Security", "Medicine", "Science"]
SIDES = ["Player", "NPC"]
RANGES = ["Contact", "Close", "Medium", "Long", "Extreme"]
WEAPON_RANGES = ["Close", "Medium", "Long"]
WEAPON_TYPES = ["Energy", "Torpedo"]
CUSTOM_WEAPON = "Custom / Other"

MOMENTUM_MAX = 6
ENERGY_BASE_DIFFICULTY = 2
TORPEDO_BASE_DIFFICULTY = 3
MAX_DICE_POOL = 5

# Crew Quality -> (Attribute, Department) used for NPC crew rolls.
CREW_QUALITY = {
    "Basic": (8, 1),
    "Proficient": (9, 2),
    "Talented": (10, 3),
    "Exceptional": (11, 4),
}
DEFAULT_CREW_QUALITY = "Talented"

# Minor Damage table rolled when a ship becomes Shaken (d20).
MINOR_DAMAGE_TABLE = [
    (1, 6, "Brace for Impact!",
     "The ship cannot take a Major Action on its next turn."),
    (7, 12, "Losing Power!",
     "Reserve Power is drained. The next attempt to Regain Power is +1 Difficulty."),
    (13, 18, "Casualties and Minor Damage",
     "The ship immediately suffers a Complication trait."),
    (19, 20, "Re-roll", "Roll again on this table."),
]
MINOR_DAMAGE_REROLL = "Re-roll"

# Nature of Breach table (d20), rolled whenever a breach is inflicted on a system.
# Listed from least to most severe; a system keeps its most severe condition.
BREACH_NATURE_TABLE = [
    (1, 4, "Damaged",
     "Subsystem is mostly functional. The GM is encouraged to spend Threat to cause "
     "complications."),
    (5, 8, "Malfunctioning",
     "A character must take the Restore minor action each turn before any task using this "
     "subsystem can be attempted."),
    (9, 12, "Primary Offline",
     "Primary Offline, Switching to Backup: backup systems engaged, +1 Difficulty to all tasks "
     "using this subsystem."),
    (13, 16, "Failing",
     "Subsystem losing power: +1 Difficulty to all tasks using this subsystem. The GM may "
     "spend 1 Threat to set it Offline."),
    (17, 20, "Offline",
     "Subsystem completely shut down / destroyed: tasks using it cannot be attempted."),
]
BREACH_NATURES = [n for _lo, _hi, n, _d in BREACH_NATURE_TABLE]
BREACH_SEVERITY = {n: i for i, n in enumerate(BREACH_NATURES)}
BREACH_DIFFICULTY = {"Primary Offline": 1, "Failing": 1}
BREACH_SHORT = {"Damaged": "Damaged", "Malfunctioning": "Malfunctioning",
                "Primary Offline": "Primary Offline (+1 Diff)", "Failing": "Failing (+1 Diff)",
                "Offline": "OFFLINE"}

# Random system hit table: (low, high, system). The die size is the top value.
SYSTEM_HIT_TABLE = [
    (1, 2, "Communications"),
    (3, 4, "Computers"),
    (5, 6, "Engines"),
    (7, 8, "Sensors"),
    (9, 10, "Structure"),
    (11, 12, "Weapons"),
]
SYSTEM_HIT_DIE = SYSTEM_HIT_TABLE[-1][1]
# Alternative weighted d20 table (rulebook-style) - selectable in the System Hit Generator.
SYSTEM_HIT_TABLE_D20 = [
    (1, 1, "Communications"),
    (2, 2, "Computers"),
    (3, 6, "Engines"),
    (7, 9, "Sensors"),
    (10, 17, "Structure"),
    (18, 20, "Weapons"),
]
SYSTEM_HIT_TABLES = {"d12 (even)": SYSTEM_HIT_TABLE, "d20 (weighted)": SYSTEM_HIT_TABLE_D20}
DEFAULT_HIT_TABLE = "d12 (even)"

# Weapon qualities: name -> (takes an X value, reminder text)
WEAPON_QUALITIES = {
    "Area": (False, "Attack can also affect other vessels close to the target - resolve "
                    "extra targets per the rulebook."),
    "Area or Spread": (False, "The attacker chooses Area or Spread each time the weapon hits "
                              "(asked automatically)."),
    "Calibration": (False, "Weapon has calibration benefits - remember to apply them when "
                           "Calibrate Weapons / Targeting Solution was used."),
    "Cumbersome": (False, "+1 Difficulty to attacks with this weapon (auto-applied)."),
    "Dampening": (False, "On a hit, the target's Reserve Power is drained (auto-applied)."),
    "Depleting": (False, "Increasing damage costs only 1 Momentum per +1 (auto-applied)."),
    "Devastating": (False, "Breaches caused are harder to fix: +1 Difficulty to Damage "
                           "Control on that ship (auto-tracked)."),
    "Hidden": (True, "Attack is concealed: detecting/locating the attacker is +X "
                     "Difficulty."),
    "High Yield": (False, "+1 additional Breach whenever this attack triggers a Breach "
                          "(auto-applied)."),
    "Intense": (False, "Increasing damage costs only 1 Momentum per +1 (auto-applied)."),
    "Jamming": (False, "On a hit, the target has +1 Difficulty to Communications/Sensors "
                       "tasks until End Round (auto-applied)."),
    "Persistent": (False, "On a hit the attacker may spend 1-3 Momentum: the target takes half "
                          "the weapon's damage (rounded up, Resistance applies) at the end of "
                          "each round for that many rounds (auto-applied)."),
    "Piercing": (False, "Ignores the target's Resistance (auto-applied)."),
    "Slowing": (False, "On a hit, the target cannot Keep the Initiative until End Round "
                       "(auto-flagged)."),
    "Spread": (False, "Devastating Attack costs only 1 Momentum (auto-applied)."),
    "Versatile": (True, "On a successful attack, gain X bonus Momentum (NPC: Threat) "
                        "(auto-applied)."),
}

AREA_OR_SPREAD = "Area or Spread"

# Weapon Auto-Calculator (STA 2e Core Rulebook pp. 228-230).
# Energy weapons = Energy Type (qualities) + Delivery Method (range, damage, qualities).
# Delivery Method -> (range, damage bonus added to the ship's Scale, intrinsic qualities)
ENERGY_DELIVERY_METHODS = {
    "Cannon": ("Close", 2, {}),
    "Banks": ("Medium", 1, {}),
    "Arrays": ("Medium", 0, {AREA_OR_SPREAD: 0}),
    "Spinal Lance": ("Long", 3, {"Cumbersome": 0}),
}
# Energy Type -> intrinsic qualities (quality -> X value, 0 if none)
ENERGY_TYPES = {
    "Antiproton Beam": {"High Yield": 0},
    "Disruptor": {"Intense": 0},
    "Electromagnetic / Ionic": {"Dampening": 0, "Piercing": 0},
    "Free Electron Laser": {},
    "Graviton Beam": {"Devastating": 0, "Piercing": 0},
    "Phase / Pulse": {"Versatile": 1},
    "Phased Polaron Beam": {"Intense": 0, "Piercing": 0},
    "Phaser": {"Versatile": 2},
    "Proton Beam": {"Persistent": 0},
    "Tetryon Beam": {"Depleting": 0},
}
# Torpedo Type -> (range, base damage, qualities)
TORPEDO_TYPES = {
    "Chroniton": ("Long", 3, {"Calibration": 0, "Slowing": 0}),
    "Gravimetric": ("Long", 5, {"Calibration": 0, "Cumbersome": 0, "High Yield": 0,
                                "Piercing": 0}),
    "Neutronic": ("Long", 4, {"Calibration": 0, "Dampening": 0}),
    "Nuclear": ("Medium", 3, {"Calibration": 0, "Intense": 0}),
    "Photon": ("Long", 3, {"High Yield": 0}),
    "Photonic": ("Long", 2, {"High Yield": 0}),
    "Plasma": ("Long", 5, {"Calibration": 0, "Cumbersome": 0, "Persistent": 0}),
    "Polaron": ("Long", 3, {"Calibration": 0, "Piercing": 0}),
    "Positron": ("Long", 5, {"Calibration": 0, "Cumbersome": 0, "Dampening": 0}),
    "Quantum": ("Long", 4, {"Calibration": 0, "High Yield": 0, "Intense": 0}),
    "Spatial": ("Medium", 2, {}),
    "Tetryonic": ("Long", 2, {"Depleting": 0, "High Yield": 0}),
    "Transphasic": ("Long", 4, {"Calibration": 0, "Devastating": 0, "Piercing": 0}),
    "Tricobalt": ("Long", 6, {"Area": 0, "Calibration": 0, "Cumbersome": 0}),
}
# Weapons System Damage Bonus: (highest Weapons rating, bonus); anything higher gets the max.
WEAPONS_DAMAGE_BONUS_TABLE = ((6, 0), (8, 1), (10, 2), (12, 3))
WEAPONS_DAMAGE_BONUS_MAX = 4
# Words that identify a type in an existing weapon's name (used to pre-select the calculator).
ENERGY_TYPE_ALIASES = {
    "Antiproton Beam": ("antiproton",),
    "Disruptor": ("disruptor", "disruptors"),
    "Electromagnetic / Ionic": ("electromagnetic", "ionic", "ion"),
    "Free Electron Laser": ("free electron", "laser", "lasers"),
    "Graviton Beam": ("graviton",),
    "Phase / Pulse": ("phase/pulse", "phase / pulse", "pulse", "phase"),
    "Phased Polaron Beam": ("phased polaron", "polaron"),
    "Phaser": ("phaser", "phasers"),
    "Proton Beam": ("proton",),
    "Tetryon Beam": ("tetryon",),
}
DELIVERY_ALIASES = {
    "Cannon": ("cannon", "cannons"),
    "Banks": ("bank", "banks"),
    "Arrays": ("array", "arrays"),
    "Spinal Lance": ("spinal lance", "lance"),
}

# Starship talents and special rules: name -> (kind, reminder text).
# Talents not in this catalogue can still be added to a ship as free text (reminder only).
TALENT = "Talent"
SPECIAL_RULE = "Special Rule"
STARSHIP_TALENTS = {
    "Ablative Armor": (TALENT, "+2 Resistance (auto-applied)."),
    "Improved Hull Integrity": (TALENT, "+1 Resistance (auto-applied)."),
    "Advanced Shields": (TALENT, "+5 maximum Shields (auto-applied)."),
    "Cloaking Device": (TALENT, "Cloak toggle. While Cloaked the ship has the Cloaked trait, its "
                                "Shields are 0 and cannot be raised, and it cannot attack until "
                                "it decloaks (Minor Action). Enemies must Reveal it before "
                                "targeting it."),
    "Extensive Shuttlebays": (TALENT, "Small Craft Readiness = Scale - 1; can support Scale 2 "
                                      "craft such as runabouts."),
    "Rapid-Fire Torpedo Launcher": (TALENT, "Torpedo Salvo: +1 Damage (auto-applied) and Tactical "
                                            "may re-roll 1d20 on the attack."),
    "Fast Targeting Systems": (TALENT, "Targeting Solution grants BOTH the d20 re-roll AND the "
                                       "choice of system hit."),
    "Advanced Sensor Suites": (TALENT, "When the ship assists a Sensors task it rolls 2d20 instead "
                                       "of 1d20 (not while Sensors has breaches)."),
    "Point Defense System": (TALENT, "While active, torpedo attacks against this ship face Cover: "
                                     "+1 Difficulty (auto-applied)."),
    "Secondary Reactors": (TALENT, "Once per scene, when the ship uses Reroute Power, spend 2 "
                                   "Momentum (Immediate) to restore its Reserve Power "
                                   "(contextual button / prompt)."),
    "Backup EPS Conduits": (TALENT, "Redundant power conduits: reminder during Reroute Power and "
                                    "when the ship loses power (Losing Power!) - apply the "
                                    "talent's text (GM ruling)."),
    "Rugged Design": (TALENT, "Breach repairs: re-roll 1d20 on Damage Control (auto-roll "
                              "re-rolls a failed die); on success you may spend 2 Momentum to "
                              "patch a second breach (contextual prompt)."),
    "Improved Damage Control": (TALENT, "Better damage-control teams: reminder during Damage "
                                        "Control - apply the talent's text (GM ruling)."),
    "Electronic Warfare Systems": (TALENT, "Built to intercept and jam signals: reminder for "
                                           "Communications tasks (GM ruling)."),
    "Reduced Sensor Silhouette": (TALENT, "Hard to detect: reminder on Reveal / Sensor Sweep / "
                                          "Scan for Weakness against this ship (GM may add "
                                          "Difficulty)."),
    "Emergency Medical Hologram": (TALENT, "An EMH can treat casualties when medical staff are "
                                           "unavailable (narrative reminder)."),
    "Experimental Vessel": (SPECIAL_RULE, "Ship assist dice cause a complication on 18-20 "
                                          "(auto-applied)."),
    "Prototype": (SPECIAL_RULE, "Same as Experimental Vessel: ship assist dice cause a "
                                "complication on 18-20 (auto-applied)."),
    "Abundant Personnel": (SPECIAL_RULE, "Crew Support pool is doubled (auto-applied)."),
    "Specialized Shuttlebay": (SPECIAL_RULE, "Shuttlebay configured for specialised craft "
                                             "(narrative reminder)."),
}
TALENT_RESISTANCE_BONUS = {"Ablative Armor": 2, "Improved Hull Integrity": 1}
TALENT_SHIELD_BONUS = {"Advanced Shields": 5}
EXPERIMENTAL_RULES = ("Experimental Vessel", "Prototype")


def talent_kind(name: str) -> str:
    return STARSHIP_TALENTS.get(name, (TALENT, ""))[0]


def talent_text(name: str) -> str:
    return STARSHIP_TALENTS.get(name, (TALENT, "Custom talent - no automation; reminder only."))[1]


BONUS_DAMAGE_COST = 2          # Momentum per +1 damage (1 with Intense/Depleting)
DEVASTATING_ATTACK_COST = 2    # Momentum (1 with Spread)


def _action(kind, system, *, roll=True, attr=None, dept=None, assist=None, base=0,
            reminder="", attack=False, needs_target=False, range_penalty=False,
            requires_power=False, sensor=False, task_label="Task", custom_base=False):
    return {
        "kind": kind, "system": system, "roll": roll, "attr": attr, "dept": dept,
        "task_label": task_label,
        "assist": assist, "base": base, "reminder": reminder, "attack": attack,
        "needs_target": needs_target, "range_penalty": range_penalty,
        "requires_power": requires_power, "sensor": sensor, "custom_base": custom_base,
    }


def _standard_minors() -> dict:
    """Minor actions any crew member can take, whatever their station."""
    return {
        "Change Position": _action(
            "Minor", None, roll=False,
            reminder="Move to another bridge station or ship location. Minor Action - does not "
                     "use a turn."),
        "Interact": _action(
            "Minor", None, roll=False,
            reminder="Interact with a console or object in the environment. Minor Action."),
        "Prepare": _action(
            "Minor", None, roll=False,
            reminder="Set up for a task - required before Warp and for raising / lowering "
                     "shields or arming weapons. Minor Action."),
        "Restore": _action(
            "Minor", None, roll=False,
            reminder="Minor adjustments or repairs after disruption: a Malfunctioning "
                     "subsystem can be used for the rest of this turn. Minor Action."),
    }


def _create_trait(attrs, depts, assist, purpose) -> dict:
    """Station-specific Create Trait (Major, Difficulty 2)."""
    return _action(
        "Major", assist[0] if assist else None, attr=attrs, dept=depts, assist=assist,
        base=2, task_label="Suggested task",
        reminder=f"Difficulty 2. Create, alter or remove a trait for {purpose}. On success the "
                 "trait goes into the Scene Traits list.")


STANDARD_STATION = "Starship Standard Actions"

# Station -> Action -> definition. Each station lists its Minor actions first.
#   system: ship system the action draws on (re-use check, breach conditions).
#   assist: (System, Department) the ship rolls when it assists the task.
#   kind:   Major (uses a turn), Minor, or Free.
BRIDGE_STATIONS = {
    "Command": {
        **_standard_minors(),
        "Direct": _action(
            "Major", "Communications", roll=False, attr="Control", dept="Command",
            task_label="Commander's assist die",
            reminder="Costs 1 Momentum (NPC: 1 Threat). Choose an ally: they immediately take "
                     "a Major Action WITHOUT the usual +1 Difficulty penalty. The commander "
                     "assists that task using Control + Command."),
        "Rally": _action(
            "Major", "Communications", attr="Presence", dept="Command",
            assist=("Communications", "Command"), base=0,
            reminder="Difficulty 0 task used specifically to generate Momentum: every success "
                     "scored becomes Momentum (NPC: Threat)."),
        "Assist": _action(
            "Major", "Communications", roll=False,
            reminder="The commander may assist TWO allies' tasks instead of one. Each assist "
                     "die uses the commander's own Attribute + Department for that task."),
        "Create Trait": _create_trait("Control / Insight / Reason", "Command",
                                      ("Computers", "Command"),
                                      "tactical plans and strategies"),
    },
    "Conn / Helm": {
        "Impulse": _action(
            "Minor", "Engines", roll=False,
            reminder="Move up to 2 zones. Minor Action - does not use a turn."),
        "Thrusters": _action(
            "Minor", "Engines", roll=False,
            reminder="Move anywhere within Close range, or into Contact with another "
                     "vessel or object. Minor Action - does not use a turn."),
        "Attack Pattern": _action(
            "Major", "Engines", attr="Control", dept="Conn", assist=("Engines", "Conn"),
            base=1,
            reminder="On success the helm assists ALL of this ship's attacks until its next "
                     "turn (adds a Control + Conn assist die to Fire / Ram), but attacks "
                     "AGAINST this ship are -1 Difficulty (auto-applied). Cleared at End Round."),
        "Evasive Action": _action(
            "Major", "Structure", roll=False, attr="Daring", dept="Conn",
            assist=("Structure", "Conn"), task_label="Defence roll when attacked",
            reminder="Until End Round: attacks against this ship become Opposed Tasks "
                     "(defender rolls Daring + Conn, assisted by Structure + Conn). Attacks "
                     "made BY this ship suffer +1 Difficulty."),
        "Maneuver": _action(
            "Major", "Engines", attr="Control", dept="Conn", assist=("Engines", "Conn"),
            base=0,
            reminder="Difficulty 0 task that generates Momentum for crossing difficult "
                     "terrain or hazards. Every success becomes Momentum (NPC: Threat)."),
        "Ram": _action(
            "Major", "Engines", attr="Daring", dept="Conn", assist=("Engines", "Conn"),
            base=2, attack=True, needs_target=True,
            reminder="Target must be within Close range. On success BOTH ships suffer "
                     "collision damage - resolve it in the Damage Resolver (suggested damage "
                     "is pre-filled; the GM may edit it)."),
        "Warp": _action(
            "Major", "Engines", attr="Control", dept="Conn", assist=("Engines", "Conn"),
            base=1, requires_power=True,
            reminder="Requires Reserve Power and a prior Prepare (Warp) minor action. On "
                     "success move up to the ship's Engines score in zones, or leave the "
                     "battle. Reserve Power is consumed by the attempt."),
        "Create Trait": _create_trait("Control / Daring", "Conn", ("Engines", "Conn"),
                                      "positioning and maneuvers"),
    },
    "Tactical": {
        "Prepare": _action(
            "Minor", "Weapons", roll=False,
            reminder="Raise / lower shields, arm / disarm weapons, or prepare for Warp. "
                     "Minor Action - does not use a turn."),
        "Calibrate Weapons": _action(
            "Minor", "Weapons", roll=False,
            reminder="The next attack made with this ship's weapons gains +1 Damage."),
        "Targeting Solution": _action(
            "Minor", "Weapons", roll=False,
            reminder="Target an enemy within Long range. The next attack may re-roll 1d20 "
                     "OR choose which system is hit (pick the benefit when you Fire). With Fast "
                     "Targeting Systems it gets BOTH."),
        "Decloak": _action(
            "Minor", "Engines", roll=False,
            reminder="Drop the cloak (Minor Action - does not use a turn). Shields stay down "
                     "until raised with Prepare."),
        "Fire": _action(
            "Major", "Weapons", attr="Control", dept="Security", assist=("Weapons", "Security"),
            base=ENERGY_BASE_DIFFICULTY, attack=True, needs_target=True,
            reminder="Energy weapons: Difficulty 2. Torpedoes: Difficulty 3 and +1 Threat "
                     "(Salvo: +3 Threat; NPCs spend Threat instead). Cumbersome: +1 "
                     "Difficulty. On a hit, resolve damage in the Tactical panel."),
        "Defensive Fire": _action(
            "Major", "Weapons", roll=False, attr="Daring", dept="Security",
            assist=("Weapons", "Security"), task_label="Defence roll when attacked",
            reminder="Until End Round: attacks against this ship become Opposed Tasks "
                     "(defender rolls Daring + Security, assisted by Weapons + Security)."),
        "Modulate Shields": _action(
            "Major", "Structure", roll=False,
            reminder="The ship's Resistance increases by +2 until End Round."),
        "Tractor Beam": _action(
            "Major", "Structure", attr="Control", dept="Security",
            assist=("Structure", "Security"), base=2, needs_target=True,
            reminder="Target within Close range. On success the target is immobilised; the "
                     "tractor beam's Strength is the ship's Tractor Beam rating (default "
                     "Scale - 1)."),
        "Cloak": _action(
            "Major", "Engines", attr="Control", dept="Engineering",
            assist=("Engines", "Security"), base=2, requires_power=True,
            reminder="Cloaking Device talent only. Requires Reserve Power (consumed). Success: "
                     "the ship gains the Cloaked trait - Shields drop to 0 and cannot be raised, "
                     "it cannot attack, and enemies must Reveal it before targeting it."),
        "Create Trait": _create_trait("Control / Reason", "Security", ("Weapons", "Security"),
                                      "weapon modifications or targeting data"),
    },
    "Sensor Operations": {
        "Calibrate Sensors": _action(
            "Minor", "Sensors", roll=False,
            reminder="The next Sensor Operations task may ignore 1 trait OR re-roll 1d20 "
                     "(auto-roll re-rolls the worst die)."),
        "Launch Probe": _action(
            "Minor", "Sensors", roll=False,
            reminder="Launch a probe anywhere within Long range."),
        "Sensor Sweep": _action(
            "Major", "Sensors", attr="Reason", dept="Science", assist=("Sensors", "Science"),
            base=1, range_penalty=True, sensor=True,
            reminder="Base Difficulty 1, +1 for each range category beyond Close."),
        "Scan for Weakness": _action(
            "Major", "Sensors", attr="Control", dept="Science", assist=("Sensors", "Security"),
            base=2, range_penalty=True, sensor=True, needs_target=True,
            reminder="Base Difficulty 2, +1 for each range category beyond Close. Success: "
                     "the next attack against the target gains +2 Damage OR Piercing."),
        "Reveal": _action(
            "Major", "Sensors", attr="Reason", dept="Science", assist=("Sensors", "Science"),
            base=3, sensor=True,
            reminder="Reveal a cloaked or hidden vessel within Long range."),
        "Create Trait": _create_trait("Reason / Control", "Science", ("Sensors", "Science"),
                                      "discovered information or phenomena"),
    },
    "Operations / Engineering": {
        **_standard_minors(),
        "Damage Control": _action(
            "Major", "Structure", attr="Presence", dept="Engineering",
            assist=("Structure", "Engineering"), base=2,
            reminder="Success: patch 1 breach. Breaches from Devastating weapons add +1 "
                     "Difficulty."),
        "Regenerate Shields": _action(
            "Major", "Structure", attr="Control", dept="Engineering",
            assist=("Structure", "Engineering"), base=2, requires_power=True,
            reminder="Requires Reserve Power (consumed). Difficulty 2, +1 if Shields are at 0. "
                     "Success: restore Shields equal to the Engineering rating; spend 1 "
                     "Momentum for +2 more."),
        "Regain Power": _action(
            "Major", "Engines", attr="Control", dept="Engineering",
            assist=("Engines", "Engineering"), base=1,
            reminder="Success: Reserve Power is restored. +1 Difficulty after 'Losing Power!'."),
        "Reroute Power": _action(
            "Major", "Engines", roll=False, requires_power=True,
            reminder="Requires Reserve Power (consumed). Choose a system: the next task using "
                     "that system receives the Reserve Power boost."),
        "Transport": _action(
            "Major", "Sensors", attr="Control", dept="Engineering",
            assist=("Sensors", "Engineering"), base=1,
            reminder="Remote transporter operation. Difficulty 1+ - add Difficulty for "
                     "interference, range or moving targets with the GM Modifier. Shields "
                     "usually must be lowered."),
        "Create Trait": _create_trait("Control / Reason", "Engineering",
                                      ("Engines", "Engineering"),
                                      "system modifications or power rerouting"),
    },
    "Communications": {
        **_standard_minors(),
        "Send / Respond to Hail": _action(
            "Free", "Communications", roll=False,
            reminder="Free Action: open or answer a hailing frequency (no turn, no Minor "
                     "Action)."),
        "Internal Comms": _action(
            "Free", "Communications", roll=False,
            reminder="Free Action: ship-wide or internal communication (no turn, no Minor "
                     "Action)."),
        "Damage Control": _action(
            "Major", "Structure", attr="Presence", dept="Engineering",
            assist=("Structure", "Engineering"), base=2,
            reminder="Success: patch 1 breach. Breaches from Devastating weapons add +1 "
                     "Difficulty."),
        "Transport": _action(
            "Major", "Sensors", attr="Control", dept="Engineering",
            assist=("Sensors", "Engineering"), base=1,
            reminder="Remote transporter operation. Difficulty 1+ - add Difficulty for "
                     "interference, range or moving targets with the GM Modifier. Shields "
                     "usually must be lowered."),
        "Create Trait": _create_trait("Control / Reason", "Engineering / Command",
                                      ("Communications", "Engineering"),
                                      "encryption, jamming or coordination"),
    },
    STANDARD_STATION: {
        **_standard_minors(),
        "Create / Alter Trait": _action(
            "Major", None, attr="Appropriate Attribute", dept="Department", base=2,
            task_label="Suggested task",
            reminder="Difficulty 2. Create, change or remove a trait in the scene using an "
                     "appropriate Attribute + Department (set them in the Action Resolver)."),
        "Assist": _action(
            "Major", None, roll=False,
            reminder="Nominate an ally: you assist their next task with your own Attribute + "
                     "Department."),
        "Override": _action(
            "Major", None, roll=False,
            reminder="Control another position from your current console: pick the station "
                     "and action to perform - that task is +1 Difficulty (the Override box in "
                     "Action Options is ticked for you). Override itself uses no extra turn."),
        "Pass": _action(
            "Major", None, roll=False,
            reminder="Decline to take a Major Action this turn (the turn is still used). "
                     "Allowed while Bracing for Impact."),
        "Ready": _action(
            "Major", None, roll=False,
            reminder="Declare a Major Action and the event that triggers it; it is resolved "
                     "as a reaction when that happens (until End Round)."),
        "Other Tasks": _action(
            "Major", None, attr="GM's choice", dept="GM's choice", custom_base=True,
            reminder="Any other task the GM calls for, including Extended Tasks. Set its base "
                     "Difficulty in Action Options and the Attribute / Department in the "
                     "Action Resolver."),
    },
}

# Actions a cloaked ship cannot take, and actions that need a detectable target.
HOSTILE_ACTIONS = ("Fire", "Ram", "Tractor Beam")
TARGETED_ACTIONS = ("Fire", "Ram", "Tractor Beam", "Scan for Weakness", "Targeting Solution")

GENERATOR_PROFILES = {
    # profile -> (system modifiers, department weights)
    "Balanced": ({}, {}),
    "Warship": ({"Weapons": 2, "Structure": 1, "Computers": -1, "Communications": -1},
                {"Security": 2, "Conn": 1}),
    "Science / Survey": ({"Sensors": 2, "Computers": 1, "Weapons": -2},
                         {"Science": 2, "Engineering": 1}),
    "Escort / Raider": ({"Engines": 2, "Weapons": 1, "Structure": -1, "Communications": -1},
                        {"Conn": 2, "Security": 1}),
    "Freighter / Civilian": ({"Structure": 1, "Engines": -1, "Weapons": -3},
                             {"Engineering": 2, "Command": 1}),
}


# =============================================================================
# Helpers
# =============================================================================

def to_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        try:
            return int(float(value))
        except (TypeError, ValueError, OverflowError):
            return default


def to_bool(value, default=False) -> bool:
    """Lenient bool for hand-edited JSON ("false", "0", "no" are False)."""
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("false", "0", "no", "off", ""):
            return False
        if text in ("true", "1", "yes", "on"):
            return True
        return default
    if value is None:
        return default
    return bool(value)


def clamp(value, low, high):
    return max(low, min(high, value))


# =============================================================================
# Data model
# =============================================================================

@dataclass
class Weapon:
    name: str = "Phaser Banks"
    wtype: str = "Energy"
    damage: int = 4
    range: str = "Medium"
    qualities: dict = field(default_factory=dict)   # quality -> X value (0 if none)
    # Auto-Calculate profile the stats were based on ("" = custom weapon)
    energy_type: str = ""
    delivery: str = ""
    torpedo_type: str = ""

    def has(self, quality: str) -> bool:
        return quality in self.qualities

    def qval(self, quality: str, default: int = 1) -> int:
        value = to_int(self.qualities.get(quality, default), default)
        return value if value > 0 else default

    def quality_text(self) -> str:
        parts = []
        for q, v in self.qualities.items():
            parts.append(f"{q} {v}" if WEAPON_QUALITIES.get(q, (False,))[0] else q)
        return ", ".join(parts)

    def describe(self) -> str:
        q = self.quality_text()
        return f"{self.name} ({self.wtype}, {self.range}, Dmg {self.damage}{'; ' + q if q else ''})"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Weapon":
        quals = data.get("qualities", {})
        if isinstance(quals, list):
            quals = {q: 0 for q in quals}
        if not isinstance(quals, dict):
            quals = {}
        quals = {str(k): (to_int(v, 0) if WEAPON_QUALITIES[k][0] else 0)
                 for k, v in quals.items() if k in WEAPON_QUALITIES}
        wtype = str(data.get("wtype", data.get("type", "Energy")))
        wtype = wtype if wtype in WEAPON_TYPES else "Energy"
        rng = str(data.get("range", "Medium"))
        etype, delivery, ttype = (str(data.get(k) or "") for k in
                                  ("energy_type", "delivery", "torpedo_type"))
        energy = wtype == "Energy"
        return cls(
            name=str(data.get("name", "Weapon")).strip() or "Weapon",
            wtype=wtype,
            damage=max(0, to_int(data.get("damage", 4), 4)),
            range=rng if rng in WEAPON_RANGES else "Medium",
            qualities=quals,
            energy_type=etype if energy and etype in ENERGY_TYPES else "",
            delivery=delivery if energy and delivery in ENERGY_DELIVERY_METHODS else "",
            torpedo_type=ttype if not energy and ttype in TORPEDO_TYPES else "",
        )


def weapons_damage_bonus(weapons_rating) -> int:
    """Weapons System Damage Bonus (+0 to +4) for the ship's Weapons system rating."""
    rating = to_int(weapons_rating, 0)
    for highest, bonus in WEAPONS_DAMAGE_BONUS_TABLE:
        if rating <= highest:
            return bonus
    return WEAPONS_DAMAGE_BONUS_MAX


def merge_qualities(*sources) -> dict:
    """Merge quality dicts in order; a quality present twice keeps the larger X value."""
    merged = {}
    for src in sources:
        for q, v in src.items():
            merged[q] = max(merged.get(q, 0), v)
    return merged


def energy_weapon_name(energy_type: str, delivery: str) -> str:
    return f"{energy_type.replace(' / ', '/')} {delivery}"


def torpedo_weapon_name(torpedo_type: str) -> str:
    return f"{torpedo_type} Torpedoes"


def calculate_weapon(wtype, scale, weapons_rating, energy_type="", delivery="", torpedo_type="",
                     include_bonus=True):
    """Standard weapon stats from the Core Rulebook tables.

    Returns (Weapon, parts) where parts are (label, value) pairs that add up to the
    damage, or (None, []) when the selection is incomplete for that weapon type."""
    rating = to_int(weapons_rating, 0)
    if wtype == "Energy":
        if energy_type not in ENERGY_TYPES or delivery not in ENERGY_DELIVERY_METHODS:
            return None, []
        rng, delivery_bonus, delivery_q = ENERGY_DELIVERY_METHODS[delivery]
        parts = [("Scale", max(1, to_int(scale, 1))), (delivery, delivery_bonus)]
        quals = merge_qualities(ENERGY_TYPES[energy_type], delivery_q)
        name = energy_weapon_name(energy_type, delivery)
        profile = {"energy_type": energy_type, "delivery": delivery}
    elif wtype == "Torpedo":
        if torpedo_type not in TORPEDO_TYPES:
            return None, []
        rng, base, quals = TORPEDO_TYPES[torpedo_type]
        parts = [(f"{torpedo_type} torpedo", base)]
        quals = dict(quals)
        name = torpedo_weapon_name(torpedo_type)
        profile = {"torpedo_type": torpedo_type}
    else:
        return None, []
    if include_bonus:
        parts.append((f"Weapons {rating} bonus", weapons_damage_bonus(rating)))
    damage = sum(v for _label, v in parts)
    return Weapon(name, wtype, damage, rng, quals, **profile), parts


def format_weapon_calc(parts) -> str:
    """'Scale 5 + 0 (Arrays) + 3 (Weapons 11 bonus) = Damage 8'."""
    if not parts:
        return ""
    label, value = parts[0]
    text = f"{label} {value}"
    for label, value in parts[1:]:
        text += f" {'+' if value >= 0 else '-'} {abs(value)} ({label})"
    return f"{text} = Damage {sum(v for _l, v in parts)}"


def _alias_match(name: str, aliases: dict) -> str:
    """The key whose longest alias appears as whole word(s) in `name` ("" if none)."""
    low = name.lower()
    best, best_len = "", 0
    for key, words in aliases.items():
        for word in words:
            if len(word) > best_len and re.search(r"(?<![a-z])" + re.escape(word)
                                                  + r"(?![a-z])", low):
                best, best_len = key, len(word)
    return best


def infer_weapon_profile(name: str, wtype: str) -> tuple:
    """Guess (energy_type, delivery, torpedo_type) from a weapon's name, e.g. for presets."""
    if wtype == "Torpedo":
        return "", "", _alias_match(name, {t: (t.lower(),) for t in TORPEDO_TYPES})
    return _alias_match(name, ENERGY_TYPE_ALIASES), _alias_match(name, DELIVERY_ALIASES), ""


def weapon_profile(weapon) -> tuple:
    """The weapon's stored Auto-Calculate profile, or one inferred from its name."""
    if weapon.energy_type or weapon.delivery or weapon.torpedo_type:
        return weapon.energy_type, weapon.delivery, weapon.torpedo_type
    return infer_weapon_profile(weapon.name, weapon.wtype)


def resolve_area_or_spread(weapon, choice: str):
    """Copy of `weapon` with 'Area or Spread' replaced by the attacker's choice."""
    chosen = copy.deepcopy(weapon)
    if chosen.has(AREA_OR_SPREAD) and choice in ("Area", "Spread"):
        quals = {}
        for q, v in chosen.qualities.items():
            quals[choice if q == AREA_OR_SPREAD else q] = v
        chosen.qualities = quals
    return chosen


@dataclass
class Ship:
    name: str
    ship_class: str = ""
    side: str = "NPC"
    scale: int = 4
    crew_quality: str = DEFAULT_CREW_QUALITY
    base_shields: int = 12          # before talents (Advanced Shields adds +5)
    shields: int = 12
    base_resistance: int = 4        # before talents (Ablative Armor +2, Improved Hull +1)
    systems: dict = field(default_factory=lambda: {s: 8 for s in SYSTEMS})
    departments: dict = field(default_factory=lambda: {d: 2 for d in DEPARTMENTS})
    weapons: list = field(default_factory=list)
    talents: list = field(default_factory=list)     # talent / special rule names
    tractor_beam: int = 0           # tractor beam Strength; 0 = default (Scale - 1)
    notes: str = ""
    # --- lasting combat state ---------------------------------------------
    reserve_power: bool = True
    shields_up: bool = True
    stored_shields: int = -1        # Shields to restore when raised again (-1 = full)
    weapons_armed: bool = True
    warp_prepared: bool = False
    cloaked: bool = False
    point_defense_active: bool = True
    crew_support_used: int = 0
    small_craft_deployed: int = 0
    secondary_reactors_used: bool = False   # once per scene
    breaches: dict = field(default_factory=lambda: {s: 0 for s in SYSTEMS})
    breach_conditions: dict = field(default_factory=lambda: {s: "" for s in SYSTEMS})
    devastating_systems: list = field(default_factory=list)
    complications: list = field(default_factory=list)
    persistent_effects: list = field(default_factory=list)   # [{amount, rounds, source}]
    tractored_by: str = ""
    tractor_strength: int = 0       # strength of a tractor beam holding THIS ship
    rerouted_power: str = ""
    # --- "next time" effects (consumed when used) -------------------------
    calibrated_weapons: bool = False
    targeting_solution: bool = False
    calibrated_sensors: bool = False
    weakness_scanned: str = ""          # "", "damage" or "piercing"
    brace_for_impact: bool = False
    regain_power_penalty: int = 0
    # --- per-round state (reset by End Round) ------------------------------
    turns_used: int = 0
    systems_used: list = field(default_factory=list)
    restored_systems: list = field(default_factory=list)   # Restore minor action this turn
    readied_action: str = ""
    resistance_bonus: int = 0
    evasive: bool = False
    defensive_fire: bool = False
    attack_pattern: bool = False
    jammed: bool = False
    slowed: bool = False
    shaken: bool = False
    revealed: bool = False          # a cloaked ship detected with Reveal this round

    # ----------------------------------------------------------------- talents
    def has_talent(self, name: str) -> bool:
        return name in self.talents

    @property
    def talent_resistance_bonus(self) -> int:
        return sum(TALENT_RESISTANCE_BONUS.get(t, 0) for t in self.talents)

    @property
    def talent_shield_bonus(self) -> int:
        return sum(TALENT_SHIELD_BONUS.get(t, 0) for t in self.talents)

    @property
    def max_shields(self) -> int:
        return max(0, self.base_shields + self.talent_shield_bonus)

    @property
    def effective_resistance(self) -> int:
        return max(0, self.base_resistance + self.talent_resistance_bonus + self.resistance_bonus)

    @property
    def tractor_strength_rating(self) -> int:
        return self.tractor_beam if self.tractor_beam > 0 else max(0, self.scale - 1)

    @property
    def crew_support_max(self) -> int:
        base = self.scale
        return base * 2 if self.has_talent("Abundant Personnel") else base

    @property
    def small_craft_readiness(self) -> int:
        return max(0, self.scale - 1) if self.has_talent("Extensive Shuttlebays") else 0

    @property
    def max_small_craft_scale(self) -> int:
        return 2 if self.has_talent("Extensive Shuttlebays") else 1

    @property
    def assist_complication_from(self) -> int:
        """Lowest d20 result that is a complication on this ship's assist dice."""
        return 18 if any(self.has_talent(t) for t in EXPERIMENTAL_RULES) else 20

    def ship_assist_dice(self, system: str) -> int:
        """Advanced Sensor Suites: 2 assist dice on Sensors tasks unless Sensors is breached."""
        if (system == "Sensors" and self.has_talent("Advanced Sensor Suites")
                and self.breaches.get("Sensors", 0) == 0):
            return 2
        return 1

    # ----------------------------------------------------------------- derived
    def crew_ratings(self) -> tuple:
        return CREW_QUALITY.get(self.crew_quality, CREW_QUALITY[DEFAULT_CREW_QUALITY])

    def total_breaches(self) -> int:
        return sum(self.breaches.values())

    def weapon(self, name: str):
        return next((w for w in self.weapons if w.name == name), None)

    def resistance_text(self) -> str:
        parts = [f"{self.base_resistance} base"]
        for t in self.talents:
            if TALENT_RESISTANCE_BONUS.get(t):
                parts.append(f"+{TALENT_RESISTANCE_BONUS[t]} {t}")
        if self.resistance_bonus:
            parts.append(f"{self.resistance_bonus:+d} Modulated")
        if len(parts) == 1:
            return str(self.effective_resistance)
        return f"{self.effective_resistance} ({' '.join(parts)})"

    # ----------------------------------------------------------------- state
    def clamp_shields(self) -> None:
        self.shields = clamp(self.shields, 0, self.max_shields)
        if self.stored_shields >= 0:
            self.stored_shields = clamp(self.stored_shields, 0, self.max_shields)

    def breach_condition(self, system: str) -> str:
        return self.breach_conditions.get(system, "") if self.breaches.get(system, 0) else ""

    def set_breach_condition(self, system: str, nature: str, force: bool = False) -> str:
        """Attach a Nature of Breach; the most severe condition wins unless forced."""
        current = self.breach_conditions.get(system, "")
        if not nature:
            if force:
                self.breach_conditions[system] = ""
            return self.breach_conditions.get(system, "")
        if force or not current or BREACH_SEVERITY[nature] >= BREACH_SEVERITY.get(current, -1):
            self.breach_conditions[system] = nature
        return self.breach_conditions[system]

    def needs_restore(self, system: str) -> bool:
        return (self.breach_condition(system) == "Malfunctioning"
                and system not in self.restored_systems)

    def normalize(self) -> None:
        """Keep derived limits consistent after talents / Scale change."""
        for sysname in SYSTEMS:
            if not self.breaches.get(sysname, 0):
                self.breach_conditions[sysname] = ""
        self.clamp_shields()
        self.crew_support_used = clamp(self.crew_support_used, 0, self.crew_support_max)
        self.small_craft_deployed = clamp(self.small_craft_deployed, 0,
                                          self.small_craft_readiness)

    def lower_shields(self) -> None:
        """Lowered shields count as 0; the current value is kept for when they are raised."""
        if self.shields_up:
            self.stored_shields = self.shields
            self.shields = 0
            self.shields_up = False

    def raise_shields(self) -> bool:
        """Returns False if the shields cannot be raised (e.g. while cloaked)."""
        if self.cloaked:
            return False
        if not self.shields_up:
            restore = self.stored_shields if self.stored_shields >= 0 else self.max_shields
            self.shields = clamp(restore, 0, self.max_shields)
            self.stored_shields = -1
            self.shields_up = True
        return True

    def engage_cloak(self) -> None:
        self.lower_shields()
        self.cloaked = True
        self.revealed = False

    def disengage_cloak(self) -> None:
        """Decloaking leaves the shields down until the ship raises them (Prepare)."""
        self.cloaked = False
        self.revealed = False

    def reset_round(self) -> None:
        """Clear everything that only lasts until the end of the round."""
        self.turns_used = 0
        self.systems_used = []
        self.restored_systems = []
        self.readied_action = ""
        self.resistance_bonus = 0
        self.evasive = False
        self.defensive_fire = False
        self.attack_pattern = False
        self.jammed = False
        self.slowed = False
        self.shaken = False
        self.revealed = False

    def clear_temporary_effects(self) -> None:
        self.reset_round()
        self.calibrated_weapons = False
        self.targeting_solution = False
        self.calibrated_sensors = False
        self.weakness_scanned = ""
        self.brace_for_impact = False
        self.regain_power_penalty = 0
        self.rerouted_power = ""
        self.tractored_by = ""
        self.tractor_strength = 0
        self.warp_prepared = False
        self.persistent_effects = []

    def full_repair(self) -> None:
        self.clear_temporary_effects()
        self.cloaked = False
        self.shields_up = True
        self.stored_shields = -1
        self.shields = self.max_shields
        self.breaches = {s: 0 for s in SYSTEMS}
        self.breach_conditions = {s: "" for s in SYSTEMS}
        self.devastating_systems = []
        self.complications = []
        self.reserve_power = True
        self.weapons_armed = True

    def active_effects(self) -> list:
        fx = []
        if self.cloaked:
            fx.append("CLOAKED" + (" (revealed)" if self.revealed else ""))
        if not self.shields_up:
            stored = self.stored_shields if self.stored_shields >= 0 else self.max_shields
            fx.append(f"Shields lowered ({stored} when raised)")
        if self.shaken:
            fx.append("Shaken (this round)")
        if self.brace_for_impact:
            fx.append("Brace for Impact (no Major Action next turn)")
        if self.regain_power_penalty:
            fx.append(f"Losing Power (+{self.regain_power_penalty} to Regain Power)")
        if self.resistance_bonus:
            fx.append(f"Modulated Shields (+{self.resistance_bonus} Resistance)")
        if self.evasive:
            fx.append("Evasive Action")
        if self.defensive_fire:
            fx.append("Defensive Fire")
        if self.attack_pattern:
            fx.append("Attack Pattern")
        if self.calibrated_weapons:
            fx.append("Weapons Calibrated (+1 Dmg)")
        if self.targeting_solution:
            fx.append("Targeting Solution")
        if self.calibrated_sensors:
            fx.append("Sensors Calibrated")
        if self.weakness_scanned:
            fx.append("Weakness Scanned (" + ("+2 Dmg" if self.weakness_scanned == "damage"
                                              else "Piercing") + ")")
        if self.jammed:
            fx.append("Jammed (+1 Comms/Sensors tasks)")
        if self.slowed:
            fx.append("Slowed (cannot Keep the Initiative)")
        if self.tractored_by:
            fx.append(f"Tractored by {self.tractored_by} (Strength {self.tractor_strength})")
        if self.rerouted_power:
            fx.append(f"Power rerouted to {self.rerouted_power}")
        if self.warp_prepared:
            fx.append("Prepared for Warp")
        if self.readied_action:
            fx.append(f"Readied: {self.readied_action}")
        for sysname in SYSTEMS:
            cond = self.breach_condition(sysname)
            if cond:
                fx.append(f"{sysname}: {BREACH_SHORT[cond]}"
                          + (" (restored this turn)" if sysname in self.restored_systems else ""))
        for eff in self.persistent_effects:
            fx.append(f"Persistent {eff.get('amount', 1)} dmg x{eff.get('rounds', 1)} round(s) "
                      f"({eff.get('source', '?')})")
        return fx

    # ------------------------------------------------------------ persistence
    def to_dict(self) -> dict:
        data = asdict(self)
        data["weapons"] = [w.to_dict() for w in self.weapons]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Ship":
        if not isinstance(data, dict) or not str(data.get("name", "")).strip():
            raise ValueError("ship entry has no name")
        data = dict(data)
        # v1 saves stored the totals as "shields_max" / "resistance".
        if "base_shields" not in data and "shields_max" in data:
            data["base_shields"] = data["shields_max"]
        if "base_resistance" not in data and "resistance" in data:
            data["base_resistance"] = data["resistance"]
        ship = cls(name=str(data["name"]).strip())
        for f in fields(cls):
            if f.name in ("name", "weapons", "breach_conditions") or f.name not in data:
                continue
            default = getattr(ship, f.name)
            value = data[f.name]
            if isinstance(default, bool):
                value = to_bool(value, default)
            elif isinstance(default, int):
                value = to_int(value, default)
            elif isinstance(default, str):
                value = "" if value is None else str(value)
            elif isinstance(default, dict):
                merged = dict(default)
                if isinstance(value, dict):
                    for key in merged:
                        if key in value:
                            merged[key] = to_int(value[key], merged[key])
                value = merged
            elif isinstance(default, list):
                value = list(value) if isinstance(value, list) else default
            setattr(ship, f.name, value)
        ship.weapons = [Weapon.from_dict(w) for w in data.get("weapons", []) or []
                        if isinstance(w, dict)]
        conditions = data.get("breach_conditions")
        if isinstance(conditions, dict):
            for sysname in SYSTEMS:
                value = conditions.get(sysname, "")
                if isinstance(value, str) and value in BREACH_SEVERITY:
                    ship.breach_conditions[sysname] = value
        # normalise
        if ship.crew_quality not in CREW_QUALITY:
            ship.crew_quality = DEFAULT_CREW_QUALITY
        if ship.side not in SIDES:
            ship.side = "NPC"
        ship.scale = clamp(ship.scale, 1, 10)
        talents = []
        for t in ship.talents:
            t = str(t).strip()
            if t and t not in talents:
                talents.append(t)
        ship.talents = talents
        ship.base_shields = max(0, ship.base_shields)
        ship.base_resistance = max(0, ship.base_resistance)
        ship.tractor_beam = max(0, ship.tractor_beam)
        ship.stored_shields = max(-1, ship.stored_shields)
        ship.turns_used = max(0, ship.turns_used)
        if ship.cloaked and not ship.has_talent("Cloaking Device"):
            ship.cloaked = False
        if ship.cloaked and ship.shields_up:
            ship.lower_shields()
        if not ship.shields_up and (ship.shields > 0 or "stored_shields" not in data):
            # v1 kept the value live while shields were lowered; v2 stores it.
            if ship.stored_shields < 0:
                ship.stored_shields = ship.shields
            ship.shields = 0
        ship.breaches = {s: max(0, v) for s, v in ship.breaches.items()}
        ship.normalize()
        ship.devastating_systems = [s for s in ship.devastating_systems if s in SYSTEMS]
        ship.systems_used = [s for s in ship.systems_used if s in SYSTEMS]
        ship.restored_systems = [s for s in ship.restored_systems if s in SYSTEMS]
        ship.complications = [str(c) for c in ship.complications]
        ship.persistent_effects = [
            {"amount": max(1, to_int(e.get("amount", 1), 1)),
             "rounds": max(1, to_int(e.get("rounds", 1), 1)),
             "source": str(e.get("source", "?")),
             # v1 effects (no "rounds") ignored Resistance; keep that when migrating.
             "piercing": to_bool(e.get("piercing", "rounds" not in e))}
            for e in ship.persistent_effects if isinstance(e, dict)]
        if ship.weakness_scanned not in ("", "damage", "piercing"):
            ship.weakness_scanned = ""
        if ship.rerouted_power not in SYSTEMS:
            ship.rerouted_power = ""
        return ship


def preset_ships() -> list:
    aurora = Ship(
        name="USS Aurora", ship_class="Akira-class Prototype", side="Player", scale=5,
        crew_quality="Talented", base_shields=19, shields=19, base_resistance=5,
        systems={"Communications": 9, "Computers": 10, "Engines": 10, "Sensors": 11,
                 "Structure": 9, "Weapons": 11},
        departments={"Command": 1, "Conn": 2, "Engineering": 3, "Security": 4,
                     "Medicine": 3, "Science": 3},
        weapons=[
            Weapon("Phaser Arrays", "Energy", 8, "Medium",
                   {"Versatile": 2, "Area": 0, "Spread": 0}),
            Weapon("Photon Torpedoes", "Torpedo", 7, "Long", {"High Yield": 0}),
        ],
        talents=["Ablative Armor", "Extensive Shuttlebays", "Rapid-Fire Torpedo Launcher",
                 "Advanced Sensor Suites", "Emergency Medical Hologram",
                 "Experimental Vessel", "Specialized Shuttlebay"],
        tractor_beam=4,
        notes="Resistance 7 = base 5 + 2 Ablative Armor.")
    warbird = Ship(
        name="D'Deridex Warbird", ship_class="D'Deridex-class Warbird", side="NPC", scale=6,
        crew_quality="Talented", base_shields=21, shields=21, base_resistance=6,
        systems={"Communications": 9, "Computers": 10, "Engines": 10, "Sensors": 11,
                 "Structure": 11, "Weapons": 9},
        departments={"Command": 3, "Conn": 2, "Engineering": 2, "Security": 4,
                     "Medicine": 1, "Science": 3},
        weapons=[
            Weapon("Disruptor Banks", "Energy", 9, "Medium", {"Intense": 0}),
            Weapon("Plasma Torpedoes", "Torpedo", 7, "Long",
                   {"Persistent": 0, "Calibration": 0, "Cumbersome": 0}),
        ],
        talents=["Cloaking Device", "Electronic Warfare Systems", "Fast Targeting Systems",
                 "Improved Damage Control", "Reduced Sensor Silhouette", "Secondary Reactors",
                 "Abundant Personnel"],
        tractor_beam=5,
        notes="Romulan Star Empire.")
    return [aurora, warbird]


def generate_npc_ship(name: str, scale: int, crew_quality: str, profile: str = "Balanced",
                      rng=random, talents=None) -> Ship:
    """Build a plausible NPC vessel of the given Scale, Crew Quality, role and talents."""
    scale = clamp(to_int(scale, 4), 1, 7)
    sys_mods, dept_bias = GENERATOR_PROFILES.get(profile, GENERATOR_PROFILES["Balanced"])
    base = 7 + (scale + 1) // 2
    systems = {s: clamp(base + sys_mods.get(s, 0) + rng.randint(-1, 1), 5, 14) for s in SYSTEMS}
    departments = {d: 1 for d in DEPARTMENTS}
    weights = [1 + 2 * dept_bias.get(d, 0) for d in DEPARTMENTS]
    for _ in range(4 + scale // 2):
        dept = rng.choices(DEPARTMENTS, weights=weights)[0]
        if departments[dept] < 5:
            departments[dept] += 1
    shields = systems["Structure"] + departments["Security"] + scale
    resistance = scale + (1 if profile == "Warship" else 0)
    civilian = profile == "Freighter / Civilian"
    energy_dmg = max(1, scale + (1 if systems["Weapons"] >= 11 else 0) - (2 if civilian else 0))
    weapons = [Weapon("Energy Weapon Banks", "Energy", energy_dmg, "Medium",
                      {"Versatile": 1} if scale >= 4 and not civilian else {})]
    if not civilian and scale >= 3:
        weapons.append(Weapon("Torpedo Launchers", "Torpedo", scale + 1, "Long", {"High Yield": 0}))
    ship = Ship(
        name=name, ship_class=f"Generated {profile} (Scale {scale})", side="NPC", scale=scale,
        crew_quality=crew_quality if crew_quality in CREW_QUALITY else DEFAULT_CREW_QUALITY,
        base_shields=shields, shields=shields, base_resistance=resistance, systems=systems,
        departments=departments, weapons=weapons, talents=list(dict.fromkeys(talents or [])),
        notes=f"Generated by NPC Generator ({profile}).")
    ship.shields = ship.max_shields
    return ship


def parse_roster_data(data) -> tuple:
    """Accept a roster save, a ship export, a list of ships or one ship dict.

    Returns (ships, meta, errors)."""
    meta = {}
    if isinstance(data, dict) and "ships" in data:
        entries = data.get("ships") or []
        meta = {k: data[k] for k in ("round", "threat", "momentum", "gm_modifier",
                                     "attacker", "target", "system_hit_table",
                                     "scene_traits") if k in data}
    elif isinstance(data, list):
        entries = data
    elif isinstance(data, dict) and "name" in data:
        entries = [data]
    else:
        raise ValueError("Unrecognised file: expected a roster with a 'ships' list.")
    if not isinstance(entries, list):
        raise ValueError("'ships' must be a list.")
    ships, errors = [], []
    for i, entry in enumerate(entries, 1):
        try:
            ships.append(Ship.from_dict(entry))
        except (ValueError, TypeError, AttributeError, OverflowError) as exc:
            errors.append(f"entry {i}: {exc}")
    return ships, meta, errors


# =============================================================================
# Rules engine (pure functions - no GUI)
# =============================================================================

@dataclass
class Die:
    roll: int
    target: int
    crit: int
    source: str = "crew"        # crew | ship | assist
    rerolled_from: int = 0
    comp_from: int = 20         # rolls >= this are complications (Experimental Vessel: 18)

    @property
    def successes(self) -> int:
        if self.roll <= self.crit:
            return 2
        return 1 if self.roll <= self.target else 0

    @property
    def complication(self) -> bool:
        return self.roll >= self.comp_from

    def label(self) -> str:
        prefix = f"({self.rerolled_from}->)" if self.rerolled_from else ""
        return f"{prefix}{self.roll}{'*' * self.successes}{'!' if self.complication else ''}"


@dataclass
class TaskOutcome:
    successes: int
    difficulty: int
    success: bool
    excess: int
    complications: int = 0
    opposition: object = None
    assist_ignored: bool = False
    dice: list = field(default_factory=list)


def make_die(target: int, crit: int, source: str = "crew", rng=random, comp_from: int = 20) -> Die:
    return Die(rng.randint(1, 20), target, max(1, crit), source, comp_from=comp_from)


def reroll_worst(dice: list, rng=random):
    """Re-roll the worst crew die if it failed or is a complication.

    Returns (old, new), or None when no crew die needs re-rolling."""
    crew = [d for d in dice if d.source == "crew" and (d.successes == 0 or d.complication)]
    if not crew:
        return None
    worst = max(crew, key=lambda d: d.roll)
    old = worst.roll
    worst.rerolled_from = old
    worst.roll = rng.randint(1, 20)
    return old, worst.roll


def outcome_from_successes(total: int, difficulty: int, opposition=None, complications: int = 0,
                           dice=None, assist_ignored: bool = False) -> TaskOutcome:
    success = total >= difficulty
    excess = max(0, total - difficulty) if success else 0
    return TaskOutcome(total, difficulty, success, excess, complications, opposition,
                       assist_ignored, list(dice or []))


def opposed_difficulty(parts, defender_successes: int) -> int:
    """2e opposed task: the defender rolls first and their successes replace the base
    Difficulty; every other modifier (Cumbersome, GM, ...) still applies."""
    return max(0, defender_successes + sum(v for _label, v in parts[1:]))


def evaluate_task(dice: list, difficulty: int, opposition=None) -> TaskOutcome:
    """Assist dice (ship / helpers) only count if the crew scored a success."""
    crew = sum(d.successes for d in dice if d.source == "crew")
    helpers = sum(d.successes for d in dice if d.source != "crew")
    total = crew + (helpers if crew > 0 else 0)
    comps = sum(1 for d in dice if d.complication)
    return outcome_from_successes(total, difficulty, opposition, comps, dice,
                                  assist_ignored=crew == 0 and helpers > 0)


def format_dice(dice: list) -> str:
    groups = []
    for source, title in (("crew", "Crew"), ("ship", "Ship"), ("assist", "Assist")):
        rolled = [d.label() for d in dice if d.source == source]
        if rolled:
            groups.append(f"{title}: {' '.join(rolled)}")
    return " | ".join(groups)


def bonus_dice_cost(pool_size: int) -> int:
    """Momentum cost for extra d20s: 3rd = 1, 4th = 2, 5th = 3 (cumulative)."""
    extra = clamp(pool_size, 2, MAX_DICE_POOL) - 2
    return extra * (extra + 1) // 2


def bonus_damage_cost_each(weapon) -> int:
    if weapon is not None and (weapon.has("Intense") or weapon.has("Depleting")):
        return 1
    return BONUS_DAMAGE_COST


def devastating_attack_cost(weapon) -> int:
    return 1 if weapon is not None and weapon.has("Spread") else DEVASTATING_ATTACK_COST


def minor_damage_lookup(roll: int) -> str:
    for low, high, name, _desc in MINOR_DAMAGE_TABLE:
        if low <= roll <= high:
            return name
    raise ValueError(f"roll {roll} outside minor damage table")


def minor_damage_description(name: str) -> str:
    return next((desc for _l, _h, n, desc in MINOR_DAMAGE_TABLE if n == name), "")


def roll_minor_damage(rng=random) -> tuple:
    """Roll d20 on the Minor Damage table, automatically re-rolling 19-20.

    Returns (list_of_rolls, result_name)."""
    rolls = []
    for _ in range(100):
        roll = rng.randint(1, 20)
        rolls.append(roll)
        name = minor_damage_lookup(roll)
        if name != MINOR_DAMAGE_REROLL:
            return rolls, name
    return rolls, MINOR_DAMAGE_TABLE[0][2]


def breach_nature_lookup(roll: int) -> str:
    for low, high, name, _desc in BREACH_NATURE_TABLE:
        if low <= roll <= high:
            return name
    raise ValueError(f"roll {roll} outside Nature of Breach table")


def breach_nature_description(name: str) -> str:
    return next((d for _l, _h, n, d in BREACH_NATURE_TABLE if n == name), "")


def roll_breach_nature(rng=random) -> tuple:
    roll = rng.randint(1, 20)
    return roll, breach_nature_lookup(roll)


def action_systems(adef) -> list:
    """Ship systems a task draws on: the station system plus the ship-assist system."""
    systems = []
    if adef and adef.get("system"):
        systems.append(adef["system"])
    if adef and adef.get("assist") and adef["assist"][0] not in systems:
        systems.append(adef["assist"][0])
    return systems


def system_hit_lookup(roll: int, table=None) -> str:
    for low, high, system in table or SYSTEM_HIT_TABLE:
        if low <= roll <= high:
            return system
    raise ValueError(f"roll {roll} outside system hit table")


def roll_system_hit(rng=random, table=None) -> tuple:
    table = table or SYSTEM_HIT_TABLE
    roll = rng.randint(1, table[-1][1])
    return roll, system_hit_lookup(roll, table)


@dataclass
class DamageOutcome:
    raw: int
    resistance_applied: int
    final_damage: int
    shields_before: int
    shields_after: int
    shaken_reasons: list = field(default_factory=list)
    breach_reasons: list = field(default_factory=list)


def resolve_shield_damage(shields: int, shields_max: int, raw_damage: int, resistance: int,
                          piercing: bool = False) -> DamageOutcome:
    """Apply one attack to a ship's Shields and work out Shaken / Breach triggers.

    * Resistance is deducted unless the attack is Piercing.
    * Hit while Shields are 0, or Shields reduced to 0 -> Breach.
    * Shields dropping below 50% or below 25% -> Shaken (also when the hit reaches 0).
    * Dropping below 25% after already becoming Shaken in the SAME attack -> Breach instead.
    * A single hit causes at most one Breach from these triggers (High Yield adds more).
    """
    applied = 0 if piercing else max(0, resistance)
    final = max(0, raw_damage - applied)
    before = max(0, shields)
    after = max(0, before - final)
    out = DamageOutcome(raw_damage, applied, final, before, after)
    if final <= 0:
        return out
    if before <= 0:
        out.breach_reasons.append("hit while Shields at 0")
        return out
    half, quarter = shields_max * 0.5, shields_max * 0.25
    crossed_half = before >= half > after
    crossed_quarter = before >= quarter > after
    if crossed_half:
        out.shaken_reasons.append("Shields dropped below 50%")
    if crossed_quarter:
        if crossed_half:
            out.breach_reasons.append("Shields below 25% while already Shaken by this attack")
        else:
            out.shaken_reasons.append("Shields dropped below 25%")
    if after == 0:
        reason = "Shields reduced to 0"
        if out.breach_reasons:
            reason += " (after being Shaken by this attack)"
        out.breach_reasons = [reason]
    return out


def pending_damage_bonus(pending) -> int:
    """Automatic extra damage carried by a pending hit (calibration, weakness, rapid-fire)."""
    if not pending:
        return 0
    return (pending.get("calibrate", 0) + pending.get("scan_damage", 0)
            + pending.get("rapid_fire", 0))


def range_penalty(range_band: str) -> int:
    if range_band not in RANGES:
        return 0
    return max(0, RANGES.index(range_band) - RANGES.index("Close"))


def compute_difficulty(action_name: str, adef: dict, ship=None, weapon=None,
                       range_band: str = "Close", gm_modifier: int = 0, target=None,
                       override: bool = False, custom_base=None):
    """Total Difficulty = Base + Weapon modifiers + context (talents, breaches, range...)
    + GM Modifier.

    Returns (total, [(label, value), ...]) or (None, []) for actions without a roll."""
    if not adef or not adef["roll"]:
        return None, []
    parts = []
    base = adef["base"]
    if adef.get("custom_base") and custom_base is not None:
        base = max(0, to_int(custom_base, base))
        parts.append(("Base (GM set)", base))
    elif action_name == "Fire":
        if weapon is not None and weapon.wtype == "Torpedo":
            base = TORPEDO_BASE_DIFFICULTY
            parts.append(("Base (Torpedo)", base))
        else:
            parts.append(("Base (Energy)", base))
    else:
        parts.append(("Base", base))
    if adef["attack"]:
        parts.append(("Weapon mods (Cumbersome)" if weapon is not None and weapon.has("Cumbersome")
                      else "Weapon mods", 1 if weapon is not None and weapon.has("Cumbersome")
                      else 0))
    if adef["range_penalty"]:
        pen = range_penalty(range_band)
        if pen:
            parts.append((f"Range ({range_band})", pen))
    if ship is not None:
        if adef["attack"] and ship.evasive:
            parts.append(("Own Evasive Action", 1))
        if action_name == "Regenerate Shields" and ship.shields <= 0:
            parts.append(("Shields at 0", 1))
        if action_name == "Regain Power" and ship.regain_power_penalty:
            parts.append(("Losing Power!", ship.regain_power_penalty))
        if ship.jammed and adef["system"] in ("Communications", "Sensors"):
            parts.append(("Jammed", 1))
        if action_name == "Damage Control" and ship.devastating_systems:
            parts.append(("Devastating breaches", 1))
        for sysname in action_systems(adef):
            condition = ship.breach_condition(sysname)
            if BREACH_DIFFICULTY.get(condition):
                parts.append((f"{condition} breach: {sysname}", BREACH_DIFFICULTY[condition]))
    if override:
        parts.append(("Override from another console", 1))
    if target is not None and target is not ship:
        if target.cloaked and action_name in TARGETED_ACTIONS:
            parts.append(("Target Cloaked", 1))
        if adef["attack"] and target.attack_pattern:
            parts.append(("Target's Attack Pattern", -1))
        if (action_name == "Fire" and weapon is not None and weapon.wtype == "Torpedo"
                and target.has_talent("Point Defense System") and target.point_defense_active):
            parts.append(("Point Defense (Cover)", 1))
    parts.append(("GM Modifier", gm_modifier))
    total = max(0, sum(v for _label, v in parts))
    return total, parts


def format_difficulty_hint(total, parts) -> str:
    """Compact form for the Rule Hints, e.g.
    'Base 2 + 1 (Failing breach: Engines) + 1 (GM Modifier) = Total Difficulty 4'."""
    if total is None:
        return "No task roll required."
    label, value = parts[0]
    text = f"{label} {value}"
    for label, value in parts[1:]:
        if value:
            text += f" {'+' if value > 0 else '-'} {abs(value)} ({label})"
    return f"{text} = Total Difficulty {total}"


def format_difficulty(total, parts) -> str:
    if total is None:
        return "No task roll required."
    text = ""
    for i, (label, value) in enumerate(parts):
        if i == 0:
            text = f"{label} {value}"
        elif value < 0:
            text += f" - {label} {abs(value)}"
        else:
            text += f" + {label} {value}"
    return f"{text} = {total}"


# =============================================================================
# Reusable widgets / dialogs
# =============================================================================

def make_modal(win: tk.Toplevel, parent) -> None:
    win.transient(parent)
    win.update_idletasks()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        win.geometry(f"+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 3)}")
    except tk.TclError:
        pass
    try:
        win.wait_visibility()
        win.grab_set()
    except tk.TclError:
        pass
    win.focus_set()


def set_enabled(widget, enabled: bool) -> None:
    if isinstance(widget, ttk.Combobox):
        widget.configure(state="readonly" if enabled else "disabled")
    else:
        widget.state(["!disabled"] if enabled else ["disabled"])


def int_var_value(var, default=0) -> int:
    try:
        return int(var.get())
    except (tk.TclError, ValueError):
        return default


class ScrollableFrame(ttk.Frame):
    """A vertically scrollable container; put children in `.body`."""

    def __init__(self, master, width=400, **kw):
        super().__init__(master, **kw)
        bg = ttk.Style().lookup("TFrame", "background") or None
        self.canvas = tk.Canvas(self, width=width, highlightthickness=0, borderwidth=0,
                                background=bg)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.body = ttk.Frame(self.canvas, padding=(4, 4, 8, 4))
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.hsb.grid_remove()
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._fit_width)

    def _on_body_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._fit_width()

    def _fit_width(self, _event=None):
        """Stretch the body to the panel width, but never squeeze it below its natural
        width (Tk grids would collapse weighted columns); scroll sideways instead."""
        width, need = self.canvas.winfo_width(), self.body.winfo_reqwidth()
        self.canvas.itemconfigure(self._win, width=max(width, need))
        if need > width > 1:
            self.hsb.grid()
        else:
            self.hsb.grid_remove()
            self.canvas.xview_moveto(0)

    def fit_to_content(self) -> None:
        """Request enough width to show the body without horizontal scrolling."""
        self.update_idletasks()
        self.canvas.configure(width=self.body.winfo_reqwidth())

    def scroll(self, steps: int) -> None:
        if self.body.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(steps, "units")


class ShieldBar(tk.Canvas):
    """Horizontal shield gauge with 50% / 25% Shaken threshold markers."""

    def __init__(self, master, height=24, **kw):
        super().__init__(master, height=height, highlightthickness=1,
                         highlightbackground="#555577", background="#1b1b2f", **kw)
        self._value = (0, 0)
        self.bind("<Configure>", lambda _e: self._draw())

    def set_value(self, current: int, maximum: int) -> None:
        self._value = (current, maximum)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = max(self.winfo_width(), 20), max(self.winfo_height(), 10)
        cur, mx = self._value
        frac = 0.0 if mx <= 0 else clamp(cur / mx, 0.0, 1.0)
        color = "#2e9e5b" if frac >= 0.5 else ("#d39e00" if frac >= 0.25 else "#c0392b")
        if frac > 0:
            self.create_rectangle(0, 0, w * frac, h, fill=color, width=0)
        for t in (0.5, 0.25):
            self.create_line(w * t, 0, w * t, h, fill="#ffffff", dash=(3, 2))
        self.create_text(w / 2, h / 2, fill="#ffffff",
                         text=f"Shields {cur}/{mx}  ({frac * 100:.0f}%)")


class ChoiceDialog(tk.Toplevel):
    def __init__(self, parent, title, prompt, options, default=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=prompt, wraplength=420, justify="left").pack(anchor="w", pady=(0, 8))
        self.var = tk.StringVar(value=default if default in options else options[0])
        for opt in options:
            ttk.Radiobutton(frm, text=opt, value=opt, variable=self.var).pack(anchor="w")
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        make_modal(self, parent)

    def _ok(self):
        self.result = self.var.get()
        self.destroy()

    @classmethod
    def ask(cls, parent, title, prompt, options, default=None):
        if not options:
            return None
        dlg = cls(parent, title, prompt, list(options), default)
        parent.wait_window(dlg)
        return dlg.result


class ShakenDialog(tk.Toplevel):
    """Shaken Resolver: choose a Minor Damage result manually or auto-roll a d20."""

    def __init__(self, parent, ship_name: str, reason: str, rng=random):
        super().__init__(parent)
        self.title(f"Shaken Resolver - {ship_name}")
        self.resizable(False, False)
        self.rng = rng
        self.result = None
        self.rolls = []
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"{ship_name} is SHAKEN!", style="Alert.TLabel").pack(anchor="w")
        ttk.Label(frm, text=f"Cause: {reason}", wraplength=460).pack(anchor="w", pady=(0, 8))
        box = ttk.LabelFrame(frm, text="STA 2e Minor Damage Table (d20)", padding=8)
        box.pack(fill="x")
        self.var = tk.StringVar(value=MINOR_DAMAGE_TABLE[0][2])
        for low, high, name, desc in MINOR_DAMAGE_TABLE:
            ttk.Radiobutton(box, text=f"{low}-{high}: {name}  -  {desc}", value=name,
                            variable=self.var).pack(anchor="w", pady=1)
        self.roll_lbl = ttk.Label(frm, text="Select a result manually, or Auto-Roll.",
                                  wraplength=460)
        self.roll_lbl.pack(anchor="w", pady=8)
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Auto-Roll d20", command=self.auto_roll).pack(side="left")
        ttk.Button(btns, text="Apply Result", style="Accent.TButton",
                   command=self._apply).pack(side="right")
        ttk.Button(btns, text="Skip", command=self.destroy).pack(side="right", padx=6)
        make_modal(self, parent)

    def auto_roll(self):
        rolls, name = roll_minor_damage(self.rng)
        self.rolls = rolls
        self.var.set(name)
        trail = " -> ".join(f"{r} ({minor_damage_lookup(r)})" for r in rolls)
        self.roll_lbl.configure(text=f"Rolled: {trail}")

    def _apply(self):
        name = self.var.get()
        if name == MINOR_DAMAGE_REROLL:
            self.auto_roll()        # choosing "Re-roll" manually rolls the table again
            return
        self.result = (name, list(self.rolls))
        self.destroy()

    @classmethod
    def ask(cls, parent, ship_name, reason, rng=random):
        dlg = cls(parent, ship_name, reason, rng)
        parent.wait_window(dlg)
        return dlg.result


class BreachNatureDialog(tk.Toplevel):
    """Nature of Breach resolver: auto-roll a d20 or pick the condition from a dropdown."""

    def __init__(self, parent, ship_name: str, system: str, reason: str, current: str = "",
                 rng=random):
        super().__init__(parent)
        self.title(f"Nature of Breach - {ship_name} {system}")
        self.resizable(False, False)
        self.rng = rng
        self.result = None
        self.roll = None
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"BREACH: {ship_name} - {system}", style="Alert.TLabel").pack(
            anchor="w")
        ttk.Label(frm, text=f"Cause: {reason}" + (f"   (current condition: {current})"
                                                  if current else ""),
                  wraplength=480).pack(anchor="w", pady=(0, 8))
        box = ttk.LabelFrame(frm, text="Nature of Breach (d20)", padding=8)
        box.pack(fill="x")
        for low, high, name, desc in BREACH_NATURE_TABLE:
            ttk.Label(box, text=f"{low}-{high}  {name}: {desc}", wraplength=470,
                      justify="left").pack(anchor="w", pady=1)
        pick = ttk.Frame(frm)
        pick.pack(fill="x", pady=(8, 0))
        ttk.Label(pick, text="Condition:").pack(side="left")
        self.var = tk.StringVar(value=BREACH_NATURES[0])
        self.combo = ttk.Combobox(pick, textvariable=self.var, values=BREACH_NATURES,
                                  state="readonly", width=18)
        self.combo.pack(side="left", padx=6)
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self._manual())
        self.roll_lbl = ttk.Label(frm, text="Pick a condition manually, or Auto-Roll.",
                                  wraplength=480)
        self.roll_lbl.pack(anchor="w", pady=8)
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Auto-Roll d20", command=self.auto_roll).pack(side="left")
        ttk.Button(btns, text="Apply", style="Accent.TButton", command=self._apply).pack(
            side="right")
        ttk.Button(btns, text="Skip", command=self.destroy).pack(side="right", padx=6)
        make_modal(self, parent)

    def auto_roll(self):
        self.roll, name = roll_breach_nature(self.rng)
        self.var.set(name)
        self.roll_lbl.configure(text=f"Rolled {self.roll}: {name} - "
                                     f"{breach_nature_description(name)}")

    def _manual(self):
        self.roll = None
        name = self.var.get()
        self.roll_lbl.configure(text=f"Chosen: {name} - {breach_nature_description(name)}")

    def _apply(self):
        self.result = (self.var.get(), self.roll)
        self.destroy()

    @classmethod
    def ask(cls, parent, ship_name, system, reason, current="", rng=random):
        dlg = cls(parent, ship_name, system, reason, current, rng)
        parent.wait_window(dlg)
        return dlg.result


class WeaponDialog(tk.Toplevel):
    """Add / edit a weapon, with the Core Rulebook Auto-Calculator (pp. 228-230)."""

    CUSTOM = "(custom)"

    def __init__(self, parent, weapon=None, scale=None, weapons_rating=None):
        super().__init__(parent)
        self.title("Weapon" if weapon is None else f"Edit Weapon - {weapon.name}")
        self.resizable(False, False)
        self.result = None
        self._filling = False
        w = weapon or Weapon()
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        self.name_var = tk.StringVar(value=w.name)
        self.type_var = tk.StringVar(value=w.wtype)
        self.dmg_var = tk.IntVar(value=w.damage)
        self.range_var = tk.StringVar(value=w.range)
        ttk.Label(frm, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.name_var, width=28).grid(row=0, column=1, columnspan=3,
                                                                  sticky="ew", pady=2)
        ttk.Label(frm, text="Type").grid(row=1, column=0, sticky="w")
        ttk.Combobox(frm, textvariable=self.type_var, values=WEAPON_TYPES, state="readonly",
                     width=10).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(frm, text="Damage").grid(row=1, column=2, sticky="e", padx=(8, 2))
        ttk.Spinbox(frm, from_=0, to=30, textvariable=self.dmg_var, width=5).grid(
            row=1, column=3, sticky="w")
        ttk.Label(frm, text="Range").grid(row=2, column=0, sticky="w")
        ttk.Combobox(frm, textvariable=self.range_var, values=WEAPON_RANGES, state="readonly",
                     width=10).grid(row=2, column=1, sticky="w", pady=2)
        self._build_calculator(frm, w, scale, weapons_rating)
        qbox = ttk.LabelFrame(frm, text="Qualities (editable)", padding=6)
        qbox.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.q_vars = {}
        for i, (q, (has_x, desc)) in enumerate(WEAPON_QUALITIES.items()):
            row, col = divmod(i, 2)
            cell = ttk.Frame(qbox)
            cell.grid(row=row, column=col, sticky="w", padx=4, pady=1)
            on = tk.BooleanVar(value=w.has(q))
            ttk.Checkbutton(cell, text=q + (" X" if has_x else ""), variable=on).pack(side="left")
            xv = None
            if has_x:
                xv = tk.IntVar(value=max(1, to_int(w.qualities.get(q, 1), 1)))
                ttk.Spinbox(cell, from_=1, to=9, textvariable=xv, width=3).pack(side="left", padx=2)
            self.q_vars[q] = (on, xv)
        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)

        self.type_var.trace_add("write", lambda *_a: self._on_type_change())
        for var in (self.calc_scale_var, self.calc_weapons_var, self.bonus_var):
            var.trace_add("write", lambda *_a: self._on_ship_values_change())
        watched = [self.dmg_var, self.range_var, self.name_var]
        for on, xv in self.q_vars.values():
            watched += [on] + ([xv] if xv is not None else [])
        for var in watched:
            var.trace_add("write", lambda *_a: self._refresh_calc())
        self._show_selectors()
        self._refresh_calc()
        make_modal(self, parent)

    # ------------------------------------------------------------ calculator
    def _build_calculator(self, frm, w, scale, weapons_rating):
        calc = ttk.LabelFrame(frm, text="Auto-Calculate Weapon Stats (Core Rulebook pp. 228-230)",
                              padding=6)
        calc.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        etype, delivery, ttype = weapon_profile(w)
        self.etype_var = tk.StringVar(value=etype or self.CUSTOM)
        self.delivery_var = tk.StringVar(value=delivery or self.CUSTOM)
        self.ttype_var = tk.StringVar(value=ttype or self.CUSTOM)
        self.energy_row = ttk.Frame(calc)
        ttk.Label(self.energy_row, text="Energy Type").pack(side="left")
        ecb = ttk.Combobox(self.energy_row, textvariable=self.etype_var, state="readonly",
                           values=[self.CUSTOM] + list(ENERGY_TYPES), width=22)
        ecb.pack(side="left", padx=(4, 8))
        ttk.Label(self.energy_row, text="+ Delivery Method").pack(side="left")
        dcb = ttk.Combobox(self.energy_row, textvariable=self.delivery_var, state="readonly",
                           values=[self.CUSTOM] + list(ENERGY_DELIVERY_METHODS), width=13)
        dcb.pack(side="left", padx=(4, 0))
        self.torp_row = ttk.Frame(calc)
        ttk.Label(self.torp_row, text="Torpedo Type").pack(side="left")
        tcb = ttk.Combobox(self.torp_row, textvariable=self.ttype_var, state="readonly",
                           values=[self.CUSTOM] + list(TORPEDO_TYPES), width=14)
        tcb.pack(side="left", padx=(4, 0))
        for cb in (ecb, dcb, tcb):
            cb.bind("<<ComboboxSelected>>", lambda _e: self._on_selection())
        self.energy_row.grid(row=0, column=0, sticky="w")
        self.torp_row.grid(row=0, column=0, sticky="w")

        ship_row = ttk.Frame(calc)
        ship_row.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.calc_scale_var = tk.IntVar(value=clamp(to_int(scale, 4), 1, 10))
        self.calc_weapons_var = tk.IntVar(value=clamp(to_int(weapons_rating, 8), 1, 16))
        ttk.Label(ship_row, text="Ship Scale").pack(side="left")
        ttk.Spinbox(ship_row, from_=1, to=10, textvariable=self.calc_scale_var,
                    width=4).pack(side="left", padx=(4, 8))
        ttk.Label(ship_row, text="Weapons").pack(side="left")
        ttk.Spinbox(ship_row, from_=1, to=16, textvariable=self.calc_weapons_var,
                    width=4).pack(side="left", padx=(4, 8))
        self.bonus_lbl = ttk.Label(ship_row, text="", style="Bold.TLabel")
        self.bonus_lbl.pack(side="left")
        self.bonus_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(calc, text="Add the Weapons System Damage Bonus to the Damage rating",
                        variable=self.bonus_var).grid(row=2, column=0, sticky="w")
        self.calc_lbl = ttk.Label(calc, text="", style="Bold.TLabel", wraplength=470)
        self.calc_lbl.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.calc_q_lbl = ttk.Label(calc, text="", wraplength=470)
        self.calc_q_lbl.grid(row=4, column=0, sticky="w")
        act = ttk.Frame(calc)
        act.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(act, text="Auto-Populate", style="Accent.TButton",
                   command=self.auto_populate).pack(side="left")
        self.autofill_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(act, text="Auto-fill when a selection changes",
                        variable=self.autofill_var).pack(side="left", padx=(8, 0))
        self.calc_status_lbl = ttk.Label(calc, text="", wraplength=470)
        self.calc_status_lbl.grid(row=6, column=0, sticky="w", pady=(2, 0))

    def _selection(self):
        def val(var):
            v = var.get()
            return "" if v == self.CUSTOM else v
        return val(self.etype_var), val(self.delivery_var), val(self.ttype_var)

    def standard(self):
        """(Weapon, parts) for the current selection, or (None, []) if incomplete."""
        etype, delivery, ttype = self._selection()
        return calculate_weapon(self.type_var.get(), int_var_value(self.calc_scale_var, 4),
                                int_var_value(self.calc_weapons_var, 8), etype, delivery, ttype,
                                include_bonus=self.bonus_var.get())

    def _show_selectors(self):
        if self.type_var.get() == "Torpedo":
            self.energy_row.grid_remove()
            self.torp_row.grid()
        else:
            self.torp_row.grid_remove()
            self.energy_row.grid()

    def _on_type_change(self):
        self._show_selectors()
        self._on_selection()

    def _on_selection(self):
        if self.autofill_var.get() and self.standard()[0] is not None:
            self.auto_populate()
        else:
            self._refresh_calc()

    def _on_ship_values_change(self):
        std = self.standard()[0]
        if self.autofill_var.get() and std is not None:
            self.dmg_var.set(std.damage)       # only the damage depends on Scale / Weapons
        self._refresh_calc()

    def auto_populate(self):
        """(Re)apply the standard name, range, damage and qualities for the selection."""
        std = self.standard()[0]
        if std is None:
            what = "a Torpedo Type" if self.type_var.get() == "Torpedo" else \
                "an Energy Type and a Delivery Method"
            self.calc_status_lbl.configure(text=f"Select {what} first.", style="Alert.TLabel")
            return False
        self._filling = True
        try:
            self.name_var.set(std.name)
            self.range_var.set(std.range)
            self.dmg_var.set(std.damage)
            for q, (on, xv) in self.q_vars.items():
                on.set(q in std.qualities)
                if xv is not None and q in std.qualities:
                    xv.set(max(1, std.qualities[q]))
        finally:
            self._filling = False
        self._refresh_calc()
        return True

    def current_qualities(self) -> dict:
        quals = {}
        for q, (on, xv) in self.q_vars.items():
            if on.get():
                quals[q] = max(1, int_var_value(xv, 1)) if xv is not None else 0
        return quals

    def _refresh_calc(self):
        if self._filling or not hasattr(self, "q_vars"):
            return
        rating = int_var_value(self.calc_weapons_var, 8)
        self.bonus_lbl.configure(
            text=f"\u2192 Weapons System Damage Bonus +{weapons_damage_bonus(rating)}")
        std, parts = self.standard()
        if std is None:
            self.calc_lbl.configure(text="Standard: - (pick a type above, or keep a custom "
                                         "weapon)")
            self.calc_q_lbl.configure(text="")
            self.calc_status_lbl.configure(text="Custom weapon - all fields are set by hand.",
                                           style="Info.TLabel")
            return
        self.calc_lbl.configure(text=f"Standard {std.name}: {format_weapon_calc(parts)}, "
                                     f"Range {std.range}")
        self.calc_q_lbl.configure(text="Qualities: " + (std.quality_text() or "none"))
        diffs = []
        if int_var_value(self.dmg_var, -1) != std.damage:
            diffs.append(f"Damage {int_var_value(self.dmg_var, 0)} (standard {std.damage})")
        if self.range_var.get() != std.range:
            diffs.append(f"Range {self.range_var.get()} (standard {std.range})")
        if self.current_qualities() != std.qualities:
            diffs.append("qualities edited")
        if diffs:
            self.calc_status_lbl.configure(
                text="Customised: " + "; ".join(diffs) + ". Auto-Populate restores the "
                     "standard values.", style="Alert.TLabel")
        else:
            self.calc_status_lbl.configure(text="\u2713 Matches the standard values.",
                                           style="Good.TLabel")

    # ------------------------------------------------------------ result
    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Weapon", "The weapon needs a name.", parent=self)
            return
        wtype = self.type_var.get()
        etype, delivery, ttype = self._selection()
        energy = wtype == "Energy"
        self.result = Weapon(name, wtype, max(0, int_var_value(self.dmg_var, 0)),
                             self.range_var.get(), self.current_qualities(),
                             energy_type=etype if energy else "",
                             delivery=delivery if energy else "",
                             torpedo_type=ttype if not energy else "")
        self.destroy()

    @classmethod
    def ask(cls, parent, weapon=None, scale=None, weapons_rating=None):
        dlg = cls(parent, weapon, scale, weapons_rating)
        parent.wait_window(dlg)
        return dlg.result


class TalentPicker(ttk.Frame):
    """Multi-select list of starship talents / special rules, plus custom entries."""

    def __init__(self, master, selected=(), height=8, on_change=None, allow_custom=True):
        super().__init__(master)
        self.on_change = on_change
        self.names = list(STARSHIP_TALENTS)
        self.names += [t for t in selected if t not in self.names]
        lf = ttk.Frame(self)
        lf.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.lb = tk.Listbox(lf, selectmode="multiple", exportselection=False, height=height,
                             width=34, activestyle="none")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for name in self.names:
            self.lb.insert("end", self._label(name))
        for name in selected:
            self.lb.selection_set(self.names.index(name))
        self._prev = set(self.lb.curselection())
        self.lb.bind("<<ListboxSelect>>", self._changed)
        self.info = ttk.Label(self, text="Click a talent to see its rule.", wraplength=260,
                              justify="left", style="Info.TLabel")
        self.info.grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))
        if allow_custom:
            self.custom_var = tk.StringVar()
            ttk.Entry(self, textvariable=self.custom_var, width=22).grid(row=2, column=0,
                                                                         sticky="ew", pady=(3, 0))
            ttk.Button(self, text="Add custom", command=self._add_custom).grid(
                row=2, column=1, sticky="w", padx=(3, 0), pady=(3, 0))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    @staticmethod
    def _label(name):
        if name not in STARSHIP_TALENTS:
            return f"{name}  (custom)"
        return name + ("  (Special Rule)" if talent_kind(name) == SPECIAL_RULE else "")

    def _changed(self, _event=None):
        sel = set(self.lb.curselection())
        changed = sel ^ self._prev
        self._prev = sel
        if changed:
            name = self.names[min(changed)]
            state = "selected" if min(changed) in sel else "removed"
            self.info.configure(text=f"{name} ({state}): {talent_text(name)}")
        if self.on_change:
            self.on_change()
        return sel

    def _add_custom(self):
        name = self.custom_var.get().strip()
        if not name:
            return
        if name not in self.names:
            self.names.append(name)
            self.lb.insert("end", self._label(name))
        self.lb.selection_set(self.names.index(name))
        self.custom_var.set("")
        self._changed()

    def selected(self) -> list:
        return [self.names[i] for i in self.lb.curselection()]

    def clear(self):
        self.lb.selection_clear(0, "end")
        self._prev = set()
        self.info.configure(text="Click a talent to see its rule.")
        if self.on_change:
            self.on_change()


class ShipEditor(tk.Toplevel):
    """Custom Ship creator / editor (systems, departments, weapons, talents, crew quality)."""

    def __init__(self, parent, ship, existing_names, title):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self.is_new = ship is None
        self.src = copy.deepcopy(ship) if ship else Ship(name="New Ship")
        self.existing = set(existing_names) - ({ship.name} if ship else set())
        self.weapons = [copy.deepcopy(w) for w in self.src.weapons]
        s = self.src

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        for col in range(3):
            frm.columnconfigure(col, weight=1)

        gen = ttk.LabelFrame(frm, text="General", padding=6)
        gen.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.name_var = tk.StringVar(value=s.name)
        self.class_var = tk.StringVar(value=s.ship_class)
        self.side_var = tk.StringVar(value=s.side)
        self.scale_var = tk.IntVar(value=s.scale)
        self.quality_var = tk.StringVar(value=s.crew_quality)
        self.shields_var = tk.IntVar(value=s.base_shields)
        self.res_var = tk.IntVar(value=s.base_resistance)
        self.tractor_var = tk.IntVar(value=s.tractor_beam)
        ttk.Label(gen, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(gen, textvariable=self.name_var, width=30).grid(row=0, column=1, columnspan=3,
                                                                  sticky="ew", pady=2)
        ttk.Label(gen, text="Class / Notes").grid(row=1, column=0, sticky="w")
        ttk.Entry(gen, textvariable=self.class_var, width=30).grid(row=1, column=1, columnspan=3,
                                                                   sticky="ew", pady=2)
        ttk.Label(gen, text="Side").grid(row=2, column=0, sticky="w")
        ttk.Combobox(gen, textvariable=self.side_var, values=SIDES, state="readonly",
                     width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(gen, text="Scale").grid(row=2, column=2, sticky="e", padx=(8, 2))
        ttk.Spinbox(gen, from_=1, to=10, textvariable=self.scale_var, width=5).grid(
            row=2, column=3, sticky="w")
        ttk.Label(gen, text="Crew Quality").grid(row=3, column=0, sticky="w")
        qcb = ttk.Combobox(gen, textvariable=self.quality_var, values=list(CREW_QUALITY),
                           state="readonly", width=12)
        qcb.grid(row=3, column=1, sticky="w", pady=2)
        self.quality_info = ttk.Label(gen, text="")
        self.quality_info.grid(row=3, column=2, columnspan=3, sticky="w", padx=(8, 0))
        qcb.bind("<<ComboboxSelected>>", lambda _e: self._update_quality_info())
        ttk.Label(gen, text="Shields (base)").grid(row=4, column=0, sticky="w")
        ttk.Spinbox(gen, from_=0, to=60, textvariable=self.shields_var, width=5).grid(
            row=4, column=1, sticky="w")
        ttk.Label(gen, text="Resistance (base)").grid(row=4, column=2, sticky="e", padx=(8, 2))
        ttk.Spinbox(gen, from_=0, to=20, textvariable=self.res_var, width=5).grid(
            row=4, column=3, sticky="w")
        self.effective_lbl = ttk.Label(gen, text="", style="Bold.TLabel")
        self.effective_lbl.grid(row=4, column=4, sticky="w", padx=(10, 0))
        ttk.Label(gen, text="Tractor Beam Strength").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(gen, from_=0, to=15, textvariable=self.tractor_var, width=5).grid(
            row=5, column=1, sticky="w", pady=2)
        ttk.Label(gen, text="(0 = Scale - 1)", style="Info.TLabel").grid(row=5, column=2,
                                                                         columnspan=2, sticky="w")
        ttk.Button(gen, text="Auto-calc base (Shields = Structure + Security + Scale, "
                             "Resistance = Scale)",
                   command=self._auto_calc).grid(row=6, column=0, columnspan=5, sticky="w",
                                                 pady=(4, 0))
        gen.columnconfigure(4, weight=1)

        sysf = ttk.LabelFrame(frm, text="Systems", padding=6)
        sysf.grid(row=1, column=0, sticky="nsew", pady=6, padx=(0, 3))
        self.sys_vars = {}
        for i, name in enumerate(SYSTEMS):
            self.sys_vars[name] = tk.IntVar(value=s.systems.get(name, 8))
            ttk.Label(sysf, text=name).grid(row=i, column=0, sticky="w")
            ttk.Spinbox(sysf, from_=1, to=16, textvariable=self.sys_vars[name], width=5).grid(
                row=i, column=1, sticky="w", pady=1)
        deptf = ttk.LabelFrame(frm, text="Departments", padding=6)
        deptf.grid(row=1, column=1, sticky="nsew", pady=6, padx=3)
        self.dept_vars = {}
        for i, name in enumerate(DEPARTMENTS):
            self.dept_vars[name] = tk.IntVar(value=s.departments.get(name, 2))
            ttk.Label(deptf, text=name).grid(row=i, column=0, sticky="w")
            ttk.Spinbox(deptf, from_=0, to=5, textvariable=self.dept_vars[name], width=5).grid(
                row=i, column=1, sticky="w", pady=1)
        tf = ttk.LabelFrame(frm, text="Starship Talents & Special Rules (multi-select)",
                            padding=6)
        tf.grid(row=1, column=2, rowspan=2, sticky="nsew", pady=6, padx=(3, 0))
        self.talents = TalentPicker(tf, selected=s.talents, height=12,
                                    on_change=self._update_effective)
        self.talents.pack(fill="both", expand=True)

        wf = ttk.LabelFrame(frm, text="Weapons", padding=6)
        wf.grid(row=2, column=0, columnspan=2, sticky="nsew")
        cols = ("type", "damage", "range", "qualities")
        self.tree = ttk.Treeview(wf, columns=cols, height=5, selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.column("#0", width=140)
        for c, w in zip(cols, (65, 65, 65, 170)):
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor="w")
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nsew")
        self.tree.bind("<Double-1>", lambda _e: self._edit_weapon())
        ttk.Button(wf, text="Add Weapon...", command=self._add_weapon).grid(row=1, column=0,
                                                                            sticky="w", pady=4)
        ttk.Button(wf, text="Edit...", command=self._edit_weapon).grid(row=1, column=1, sticky="w")
        ttk.Button(wf, text="Remove", command=self._remove_weapon).grid(row=1, column=2,
                                                                        sticky="w")
        ttk.Button(wf, text="Recalc Damage", command=self._recalc_weapons).grid(
            row=1, column=3, sticky="e")
        wf.columnconfigure(3, weight=1)

        nf = ttk.LabelFrame(frm, text="Notes", padding=6)
        nf.grid(row=3, column=0, columnspan=3, sticky="ew", pady=6)
        self.notes = tk.Text(nf, height=3, width=60, wrap="word")
        self.notes.pack(fill="both", expand=True)
        self.notes.insert("1.0", s.notes)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=3, sticky="ew")
        ttk.Button(btns, text="Save Ship", style="Accent.TButton",
                   command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)

        for var in (self.shields_var, self.res_var, self.scale_var, self.tractor_var):
            var.trace_add("write", lambda *_a: self._update_effective())
        self._update_quality_info()
        self._update_effective()
        self._refresh_tree()
        make_modal(self, parent)

    def _preview(self) -> Ship:
        probe = Ship(name="preview", scale=clamp(int_var_value(self.scale_var, 4), 1, 10),
                     base_shields=max(0, int_var_value(self.shields_var, 0)),
                     base_resistance=max(0, int_var_value(self.res_var, 0)),
                     tractor_beam=max(0, int_var_value(self.tractor_var, 0)),
                     talents=self.talents.selected())
        return probe

    def _update_effective(self):
        if not hasattr(self, "effective_lbl"):
            return
        p = self._preview()
        text = f"Effective: Shields {p.max_shields}, Resistance {p.effective_resistance}, " \
               f"Tractor {p.tractor_strength_rating}"
        if p.has_talent("Extensive Shuttlebays"):
            text += f", Small Craft {p.small_craft_readiness}"
        self.effective_lbl.configure(text=text)

    def _update_quality_info(self):
        a, d = CREW_QUALITY.get(self.quality_var.get(), CREW_QUALITY[DEFAULT_CREW_QUALITY])
        self.quality_info.configure(text=f"NPC crew: Attribute {a} / Department {d}")

    def _auto_calc(self):
        scale = int_var_value(self.scale_var, 4)
        self.shields_var.set(int_var_value(self.sys_vars["Structure"], 8)
                             + int_var_value(self.dept_vars["Security"], 2) + scale)
        self.res_var.set(scale)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, w in enumerate(self.weapons):
            self.tree.insert("", "end", iid=str(i), text=w.name,
                             values=(w.wtype, w.damage, w.range, w.quality_text()))

    def _selected_index(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _regrab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _weapon_context(self) -> dict:
        """The editor's current (unsaved) Scale and Weapons rating for the calculator."""
        return {"scale": clamp(int_var_value(self.scale_var, 4), 1, 10),
                "weapons_rating": max(1, int_var_value(self.sys_vars["Weapons"], 8))}

    def weapon_damage_updates(self) -> list:
        """(weapon, new damage) for Auto-Calculated weapons whose damage differs from the
        standard for the current Scale / Weapons rating (bonus included)."""
        ctx = self._weapon_context()
        out = []
        for w in self.weapons:
            std, _parts = calculate_weapon(w.wtype, ctx["scale"], ctx["weapons_rating"],
                                           w.energy_type, w.delivery, w.torpedo_type)
            if std is not None and std.damage != w.damage:
                out.append((w, std.damage))
        return out

    def _recalc_weapons(self):
        ctx = self._weapon_context()
        updates = self.weapon_damage_updates()
        linked = [w for w in self.weapons if w.energy_type or w.torpedo_type]
        unlinked = [w.name for w in self.weapons if w not in linked]
        note = ("\n\nNot linked to the calculator (left unchanged): " + ", ".join(unlinked)
                + ".\nOpen them with Edit... and use Auto-Populate to link them."
                if unlinked else "")
        head = (f"Scale {ctx['scale']}, Weapons {ctx['weapons_rating']} (Weapons System "
                f"Damage Bonus +{weapons_damage_bonus(ctx['weapons_rating'])})")
        if not updates:
            messagebox.showinfo("Recalc Damage", f"{head}:\nall calculator-linked weapons "
                                "already have the standard damage." + note, parent=self)
            self._regrab()
            return
        lines = "\n".join(f"  {w.name}: Damage {w.damage} \u2192 {dmg}" for w, dmg in updates)
        if messagebox.askyesno("Recalc Damage", f"{head}:\n\n{lines}\n\nApply the standard "
                               "damage? Ranges, names and qualities are kept." + note,
                               parent=self):
            for w, dmg in updates:
                w.damage = dmg
            self._refresh_tree()
        self._regrab()

    def _add_weapon(self):
        w = WeaponDialog.ask(self, **self._weapon_context())
        self._regrab()
        if w:
            self.weapons.append(w)
            self._refresh_tree()

    def _edit_weapon(self):
        idx = self._selected_index()
        if idx is None:
            return
        w = WeaponDialog.ask(self, self.weapons[idx], **self._weapon_context())
        self._regrab()
        if w:
            self.weapons[idx] = w
            self._refresh_tree()

    def _remove_weapon(self):
        idx = self._selected_index()
        if idx is not None:
            del self.weapons[idx]
            self._refresh_tree()

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Ship", "The ship needs a name.", parent=self)
            return
        if name in self.existing:
            messagebox.showerror("Ship", f"A ship named '{name}' already exists.", parent=self)
            return
        ship = self.src
        was_full = ship.shields >= ship.max_shields
        ship.name = name
        ship.ship_class = self.class_var.get().strip()
        ship.side = self.side_var.get() if self.side_var.get() in SIDES else "NPC"
        ship.scale = clamp(int_var_value(self.scale_var, 4), 1, 10)
        ship.crew_quality = self.quality_var.get()
        ship.base_shields = max(0, int_var_value(self.shields_var, ship.base_shields))
        ship.base_resistance = max(0, int_var_value(self.res_var, ship.base_resistance))
        ship.tractor_beam = max(0, int_var_value(self.tractor_var, 0))
        ship.systems = {k: max(1, int_var_value(v, 8)) for k, v in self.sys_vars.items()}
        ship.departments = {k: clamp(int_var_value(v, 2), 0, 5) for k, v in self.dept_vars.items()}
        ship.weapons = self.weapons
        ship.talents = self.talents.selected()
        ship.notes = self.notes.get("1.0", "end").strip()
        if ship.cloaked and not ship.has_talent("Cloaking Device"):
            ship.disengage_cloak()
        if self.is_new or (was_full and ship.shields_up):
            ship.shields = ship.max_shields if ship.shields_up else 0
        ship.normalize()
        self.result = ship
        self.destroy()

    @classmethod
    def ask(cls, parent, ship, existing_names, title):
        dlg = cls(parent, ship, existing_names, title)
        parent.wait_window(dlg)
        return dlg.result


# =============================================================================
# Main application
# =============================================================================

class CombatHelperApp:
    def __init__(self, root: tk.Tk, data_file: str = DATA_FILE, autoload: bool = True, rng=None):
        self.root = root
        self.data_file = data_file
        self.rng = rng or random.Random()
        self.ships: list = []
        self.round = 1
        self.threat = 0
        self.momentum = 0
        self.scene_traits: list = []
        self.dirty = False
        self.pending_attack = None
        self.last_system_hit = None
        self._refreshing = False
        self._last_attacker = None

        root.title(APP_NAME)
        width = min(1540, max(900, root.winfo_screenwidth() - 40))
        height = min(960, max(600, root.winfo_screenheight() - 80))
        root.geometry(f"{width}x{height}+10+10")
        root.minsize(900, 600)
        self._setup_style()
        self._init_vars()
        self._build_menu()
        self._build_layout()
        self._bind_mousewheel()
        self._startup_load(autoload)
        for panel in (self.left_panel, self.mid_panel, self.right_panel):
            panel.fit_to_content()
        root.after(100, self._place_log_sash)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ style
    def _setup_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        self.font_bold = tkfont.Font(family=family, size=10, weight="bold")
        self.font_big = tkfont.Font(family=family, size=13, weight="bold")
        self.font_counter = tkfont.Font(family=family, size=20, weight="bold")
        self.font_mono = tkfont.nametofont("TkFixedFont")
        purple, orange = "#5b2c83", "#c76b00"
        style.configure("TLabelframe.Label", font=self.font_bold, foreground=purple)
        style.configure("Header.TLabel", font=self.font_big, foreground=purple)
        style.configure("Bold.TLabel", font=self.font_bold)
        style.configure("Threat.TLabel", font=self.font_counter, foreground="#b03a2e")
        style.configure("Momentum.TLabel", font=self.font_counter, foreground="#1f5fbf")
        style.configure("Round.TLabel", font=self.font_counter, foreground=orange)
        style.configure("Diff.TLabel", font=self.font_counter, foreground=purple)
        style.configure("Alert.TLabel", font=self.font_bold, foreground="#b03a2e")
        style.configure("Good.TLabel", font=self.font_bold, foreground="#1e7e46")
        style.configure("Info.TLabel", foreground="#333344")
        style.configure("Major.TLabel", font=self.font_bold, foreground="#ffffff",
                        background="#b03a2e", padding=(6, 1))
        style.configure("Free.TLabel", font=self.font_bold, foreground="#ffffff",
                        background="#1e7e46", padding=(6, 1))
        style.configure("Minor.TLabel", font=self.font_bold, foreground="#ffffff",
                        background="#1f5fbf", padding=(6, 1))
        for name, color, active in (("Accent", "#1f5fbf", "#2f74db"),
                                    ("EndRound", "#c76b00", "#e07f10"),
                                    ("Damage", "#b03a2e", "#cf4b3d")):
            style.configure(f"{name}.TButton", font=self.font_bold, foreground="#ffffff",
                            background=color)
            style.map(f"{name}.TButton", background=[("disabled", "#9a9aa6"), ("active", active)])

    # ------------------------------------------------------------------- vars
    def _init_vars(self):
        self.gm_mod_var = tk.IntVar(value=0)
        self.hit_table_var = tk.StringVar(value=DEFAULT_HIT_TABLE)
        self.attacker_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.station_var = tk.StringVar(value=list(BRIDGE_STATIONS)[0])
        self.action_var = tk.StringVar()
        self.weapon_var = tk.StringVar()
        self.salvo_var = tk.BooleanVar(value=False)
        self.range_var = tk.StringVar(value="Medium")
        self.tsol_mode_var = tk.StringVar(value="reroll")
        self.scan_mode_var = tk.StringVar(value="damage")
        self.regen_boost_var = tk.BooleanVar(value=False)
        self.override_var = tk.BooleanVar(value=False)
        self.other_base_var = tk.IntVar(value=2)
        self.crew_attr_var = tk.IntVar(value=10)
        self.crew_dept_var = tk.IntVar(value=3)
        self.focus_var = tk.BooleanVar(value=True)
        self.dice_var = tk.IntVar(value=2)
        self.autopay_var = tk.BooleanVar(value=True)
        self.assist_var = tk.BooleanVar(value=True)
        self.mode_var = tk.StringVar(value="auto")
        self.manual_succ_var = tk.IntVar(value=0)
        self.opp_var = tk.IntVar(value=0)
        # damage resolver
        self.dmg_weapon_var = tk.StringVar(value=CUSTOM_WEAPON)
        self.dmg_base_var = tk.IntVar(value=0)
        self.dmg_bonus_var = tk.IntVar(value=0)
        self.pierce_var = tk.BooleanVar(value=False)
        self.devastate_var = tk.BooleanVar(value=False)
        # target state toggles
        self.tgt_reserve_var = tk.BooleanVar()
        self.tgt_shields_up_var = tk.BooleanVar()
        self.tgt_armed_var = tk.BooleanVar()
        self.tgt_pds_var = tk.BooleanVar()
        self.tgt_set_shields_var = tk.IntVar(value=0)
        # generator
        self.gen_name_var = tk.StringVar()
        self.gen_scale_var = tk.IntVar(value=4)
        self.gen_quality_var = tk.StringVar(value=DEFAULT_CREW_QUALITY)
        self.gen_profile_var = tk.StringVar(value="Balanced")

        for var in (self.gm_mod_var, self.weapon_var, self.salvo_var, self.range_var,
                    self.tsol_mode_var, self.scan_mode_var, self.regen_boost_var,
                    self.crew_attr_var, self.crew_dept_var, self.focus_var, self.dice_var,
                    self.autopay_var, self.assist_var, self.mode_var, self.opp_var,
                    self.override_var, self.other_base_var):
            var.trace_add("write", lambda *_a: self._on_option_change())
        for var in (self.dmg_base_var, self.dmg_bonus_var, self.pierce_var, self.devastate_var):
            var.trace_add("write", lambda *_a: self._on_damage_option_change())
        self.gen_quality_var.trace_add("write", lambda *_a: self._update_gen_info())

    # ------------------------------------------------------------------- menu
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        fm = tk.Menu(menubar, tearoff=False)
        fm.add_command(label="Save Roster to JSON", command=self.save_roster_clicked,
                       accelerator="Ctrl+S")
        fm.add_command(label="Load Roster from JSON", command=self.load_roster_clicked)
        fm.add_separator()
        fm.add_command(label="Save Roster As...", command=self.save_roster_as)
        fm.add_command(label="Load Roster From File...", command=self.load_roster_from)
        fm.add_separator()
        fm.add_command(label="Import Ship(s)...", command=self.import_ships)
        fm.add_command(label="Export Selected Ship...", command=self.export_ship)
        fm.add_command(label="Export Combat Log...", command=self.export_log)
        fm.add_separator()
        fm.add_command(label="Reset Roster to Presets", command=self.reset_to_presets)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=fm)
        cm = tk.Menu(menubar, tearoff=False)
        cm.add_command(label="End Round", command=self.end_round)
        cm.add_command(label="New Scene (reset once-per-scene talents)", command=self.new_scene)
        cm.add_command(label="New Adventure (refill Crew Support)", command=self.new_adventure)
        menubar.add_cascade(label="Combat", menu=cm)
        hm = tk.Menu(menubar, tearoff=False)
        hm.add_command(label="Quick Reference...", command=self.show_reference)
        hm.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=hm)
        self.root.configure(menu=menubar)
        self.root.bind_all("<Control-s>", lambda _e: self.save_roster_clicked())

    # ----------------------------------------------------------------- layout
    def _build_layout(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)
        self._build_top(outer)
        self.vpane = vpane = ttk.PanedWindow(outer, orient="vertical")
        vpane.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        hpane = ttk.PanedWindow(vpane, orient="horizontal")
        vpane.add(hpane, weight=5)
        self.left_panel = ScrollableFrame(hpane, width=390)
        self.mid_panel = ScrollableFrame(hpane, width=500)
        self.right_panel = ScrollableFrame(hpane, width=470)
        hpane.add(self.left_panel, weight=1)
        hpane.add(self.mid_panel, weight=1)
        hpane.add(self.right_panel, weight=1)
        self._build_left(self.left_panel.body)
        self._build_middle(self.mid_panel.body)
        self._build_right(self.right_panel.body)
        logf = ttk.LabelFrame(vpane, text="Combat History Log", padding=4)
        vpane.add(logf, weight=1)
        self._build_log(logf)

    # ---------------------------------------------------------------- top bar
    def _build_top(self, parent):
        top = ttk.Frame(parent, padding=(8, 6, 8, 2))
        top.pack(fill="x")

        tf = ttk.LabelFrame(top, text="Threat", padding=(6, 0))
        tf.pack(side="left", padx=(0, 8))
        ttk.Button(tf, text="-", width=3, command=lambda: self.adjust_pool("threat", -1)).pack(
            side="left")
        self.threat_lbl = ttk.Label(tf, text="0", width=3, anchor="center", style="Threat.TLabel")
        self.threat_lbl.pack(side="left", padx=4)
        ttk.Button(tf, text="+", width=3, command=lambda: self.adjust_pool("threat", 1)).pack(
            side="left")

        mf = ttk.LabelFrame(top, text=f"Momentum (max {MOMENTUM_MAX})", padding=(6, 0))
        mf.pack(side="left", padx=(0, 8))
        ttk.Button(mf, text="-", width=3, command=lambda: self.adjust_pool("momentum", -1)).pack(
            side="left")
        self.momentum_lbl = ttk.Label(mf, text="0", width=3, anchor="center",
                                      style="Momentum.TLabel")
        self.momentum_lbl.pack(side="left", padx=4)
        ttk.Button(mf, text="+", width=3, command=lambda: self.adjust_pool("momentum", 1)).pack(
            side="left")

        rf = ttk.LabelFrame(top, text="Round", padding=(6, 0))
        rf.pack(side="left", padx=(0, 8))
        self.round_lbl = ttk.Label(rf, text="1", width=3, anchor="center", style="Round.TLabel")
        self.round_lbl.pack(side="left", padx=4)
        ttk.Button(rf, text="END ROUND", style="EndRound.TButton", command=self.end_round).pack(
            side="left", padx=4, pady=4)

        gf = ttk.LabelFrame(top, text="GM Modifier [ + / - ]", padding=(6, 0))
        gf.pack(side="left", padx=(0, 8))
        ttk.Spinbox(gf, from_=-3, to=5, increment=1, textvariable=self.gm_mod_var, width=4,
                    font=self.font_big, state="readonly").pack(side="left", pady=6, padx=2)
        ttk.Label(gf, text="Difficulty\n(-3 to +5)", style="Info.TLabel").pack(side="left", padx=4)

        sf = ttk.Frame(top)
        sf.pack(side="right")
        ttk.Button(sf, text="Save Roster to JSON", command=self.save_roster_clicked).pack(
            side="top", fill="x", pady=1)
        ttk.Button(sf, text="Load Roster from JSON", command=self.load_roster_clicked).pack(
            side="top", fill="x", pady=1)
        self.file_lbl = ttk.Label(top, text="", style="Info.TLabel", justify="right")
        self.file_lbl.pack(side="right", padx=8)

    # ------------------------------------------------------------- left panel
    def _build_left(self, body):
        body.columnconfigure(0, weight=1)

        rf = ttk.LabelFrame(body, text="Ship Roster", padding=6)
        rf.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        rf.columnconfigure(1, weight=1)
        lbf = ttk.Frame(rf)
        lbf.grid(row=0, column=0, columnspan=4, sticky="ew")
        self.roster_lb = tk.Listbox(lbf, height=7, exportselection=False, font=self.font_mono,
                                    activestyle="dotbox")
        sb = ttk.Scrollbar(lbf, orient="vertical", command=self.roster_lb.yview)
        self.roster_lb.configure(yscrollcommand=sb.set)
        self.roster_lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.roster_lb.bind("<Double-Button-1>", lambda _e: self.set_selected_as("attacker"))
        ttk.Label(rf, text="[A] Attacker  [T] Target  |  Shields  T = turns used / Scale\n"
                           "B = breaches, SHK = Shaken.  Double-click = set Attacker.",
                  style="Info.TLabel").grid(
            row=1, column=0, columnspan=4, sticky="w")
        bf = ttk.Frame(rf)
        bf.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 2))
        ttk.Button(bf, text="Set as Attacker",
                   command=lambda: self.set_selected_as("attacker")).pack(side="left")
        ttk.Button(bf, text="Set as Target",
                   command=lambda: self.set_selected_as("target")).pack(side="left", padx=4)
        ttk.Button(bf, text="Swap", command=self.swap_selection).pack(side="left")

        ttk.Label(rf, text="Attacker:").grid(row=3, column=0, sticky="w")
        self.attacker_cb = ttk.Combobox(rf, textvariable=self.attacker_var, state="readonly")
        self.attacker_cb.grid(row=3, column=1, columnspan=3, sticky="ew", pady=1)
        ttk.Label(rf, text="Target:").grid(row=4, column=0, sticky="w")
        self.target_cb = ttk.Combobox(rf, textvariable=self.target_var, state="readonly")
        self.target_cb.grid(row=4, column=1, columnspan=3, sticky="ew", pady=1)
        self.attacker_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_selection_change())
        self.target_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_selection_change())

        ef = ttk.Frame(rf)
        ef.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        for text, cmd in (("New...", self.new_ship), ("Edit...", self.edit_ship),
                          ("Duplicate", self.duplicate_ship), ("Delete", self.delete_ship)):
            ttk.Button(ef, text=text, command=cmd, width=9).pack(side="left", padx=(0, 3))
        xf = ttk.Frame(rf)
        xf.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(3, 0))
        ttk.Button(xf, text="Export Ship...", command=self.export_ship).pack(side="left")
        ttk.Button(xf, text="Import Ship(s)...", command=self.import_ships).pack(side="left",
                                                                                padx=3)
        ttk.Button(xf, text="Full Repair", command=self.full_repair_selected).pack(side="left")

        gf = ttk.LabelFrame(body, text="Custom Ship / NPC Generator", padding=6)
        gf.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        gf.columnconfigure(1, weight=1)
        ttk.Label(gf, text="Name (optional)").grid(row=0, column=0, sticky="w")
        ttk.Entry(gf, textvariable=self.gen_name_var).grid(row=0, column=1, columnspan=3,
                                                           sticky="ew", pady=1)
        ttk.Label(gf, text="Scale").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(gf, from_=1, to=7, textvariable=self.gen_scale_var, width=4,
                    state="readonly").grid(row=1, column=1, sticky="w", pady=1)
        ttk.Label(gf, text="Crew Quality").grid(row=2, column=0, sticky="w")
        ttk.Combobox(gf, textvariable=self.gen_quality_var, values=list(CREW_QUALITY),
                     state="readonly", width=13).grid(row=2, column=1, sticky="w", pady=1)
        self.gen_info = ttk.Label(gf, text="", style="Info.TLabel")
        self.gen_info.grid(row=2, column=2, columnspan=2, sticky="w", padx=4)
        ttk.Label(gf, text="Profile").grid(row=3, column=0, sticky="w")
        ttk.Combobox(gf, textvariable=self.gen_profile_var, values=list(GENERATOR_PROFILES),
                     state="readonly", width=20).grid(row=3, column=1, columnspan=2, sticky="w",
                                                      pady=1)
        ttk.Label(gf, text="Starship Talents (multi-select)").grid(row=4, column=0,
                                                                    columnspan=4, sticky="w",
                                                                    pady=(4, 0))
        self.gen_talents = TalentPicker(gf, height=5, allow_custom=False)
        self.gen_talents.grid(row=5, column=0, columnspan=4, sticky="ew")
        gbf = ttk.Frame(gf)
        gbf.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        ttk.Button(gbf, text="Generate NPC Ship", style="Accent.TButton",
                   command=self.generate_npc).pack(side="left")
        ttk.Button(gbf, text="Custom Ship Editor...", command=self.new_ship).pack(side="left",
                                                                                  padx=4)
        self._update_gen_info()

        af = ttk.LabelFrame(body, text="Active Ship Status (Attacker)", padding=6)
        af.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        af.columnconfigure(0, weight=1)
        self.active_name_lbl = ttk.Label(af, text="-", style="Header.TLabel")
        self.active_name_lbl.grid(row=0, column=0, sticky="w")
        self.active_bar = ShieldBar(af)
        self.active_bar.grid(row=1, column=0, sticky="ew", pady=3)
        ctl = ttk.Frame(af)
        ctl.grid(row=2, column=0, sticky="ew", pady=(0, 3))
        self.cloak_btn = ttk.Button(ctl, text="Engage Cloak", command=self.toggle_cloak)
        self.cloak_btn.pack(side="left")
        self.cloak_lbl = ttk.Label(ctl, text="", style="Alert.TLabel")
        self.cloak_lbl.pack(side="left", padx=6)
        self.active_res_lbl = ttk.Label(af, text="", style="Bold.TLabel", wraplength=360,
                                        justify="left")
        self.active_res_lbl.grid(row=3, column=0, sticky="w")
        pools = ttk.Frame(af)
        pools.grid(row=4, column=0, sticky="w", pady=(3, 0))
        self.crew_support_lbl = ttk.Label(pools, text="Crew Support: -")
        self.crew_support_lbl.grid(row=0, column=0, sticky="w")
        ttk.Button(pools, text="-", width=3,
                   command=lambda: self.adjust_pool_counter("crew_support_used", -1)).grid(
            row=0, column=1, padx=(6, 1))
        ttk.Button(pools, text="+", width=3,
                   command=lambda: self.adjust_pool_counter("crew_support_used", 1)).grid(
            row=0, column=2)
        self.small_craft_lbl = ttk.Label(pools, text="Small Craft: -")
        self.small_craft_lbl.grid(row=1, column=0, sticky="w")
        self.small_craft_minus = ttk.Button(
            pools, text="-", width=3,
            command=lambda: self.adjust_pool_counter("small_craft_deployed", -1))
        self.small_craft_minus.grid(row=1, column=1, padx=(6, 1))
        self.small_craft_plus = ttk.Button(
            pools, text="+", width=3,
            command=lambda: self.adjust_pool_counter("small_craft_deployed", 1))
        self.small_craft_plus.grid(row=1, column=2)
        self.active_status_lbl = ttk.Label(af, text="", justify="left", wraplength=360)
        self.active_status_lbl.grid(row=5, column=0, sticky="w", pady=(3, 0))

        tt = ttk.LabelFrame(body, text="Turn Tracker", padding=6)
        tt.grid(row=3, column=0, sticky="ew")
        tt.columnconfigure(0, weight=1)
        self.turns_lbl = ttk.Label(tt, text="Turns used: 0 / 0", style="Bold.TLabel")
        self.turns_lbl.grid(row=0, column=0, sticky="w")
        self.turns_bar = ttk.Progressbar(tt, mode="determinate", maximum=1)
        self.turns_bar.grid(row=1, column=0, sticky="ew", pady=3)
        self.turns_info_lbl = ttk.Label(tt, text="", justify="left", wraplength=360)
        self.turns_info_lbl.grid(row=2, column=0, sticky="w")
        tbf = ttk.Frame(tt)
        tbf.grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Button(tbf, text="+1 Turn", command=lambda: self.adjust_turns(1)).pack(side="left")
        ttk.Button(tbf, text="-1 Turn", command=lambda: self.adjust_turns(-1)).pack(side="left",
                                                                                  padx=3)
        ttk.Button(tbf, text="Reset Turns", command=self.reset_turns).pack(side="left")

    # ----------------------------------------------------------- middle panel
    def _build_middle(self, body):
        body.columnconfigure(0, weight=1)

        sf = ttk.LabelFrame(body, text="Bridge Station & Action Selector", padding=6)
        sf.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        sf.columnconfigure(1, weight=1)
        ttk.Label(sf, text="Station").grid(row=0, column=0, sticky="w")
        self.station_cb = ttk.Combobox(sf, textvariable=self.station_var,
                                       values=list(BRIDGE_STATIONS), state="readonly")
        self.station_cb.grid(row=0, column=1, sticky="ew", pady=1)
        self.station_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_station_change())
        ttk.Label(sf, text="Action").grid(row=1, column=0, sticky="w")
        self.action_cb = ttk.Combobox(sf, textvariable=self.action_var, state="readonly")
        self.action_cb.grid(row=1, column=1, sticky="ew", pady=1)
        self.action_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_action_change())
        self.kind_lbl = ttk.Label(sf, text="MAJOR", style="Major.TLabel")
        self.kind_lbl.grid(row=0, column=2, rowspan=2, padx=(8, 0))
        self.actor_lbl = ttk.Label(sf, text="", style="Bold.TLabel", wraplength=440)
        self.actor_lbl.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.breach_warn_lbl = tk.Label(sf, text="", justify="left", anchor="w",
                                        wraplength=440, font=self.font_bold,
                                        foreground="#8b1a10", background="#fde3df",
                                        padx=6, pady=4, relief="solid", borderwidth=1)
        self.breach_warn_lbl.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.breach_warn_lbl.grid_remove()
        self.failing_btn = ttk.Button(sf, text="Spend 1 Threat \u2192 Set Offline",
                                      command=self.failing_to_offline_acting)
        self.failing_btn.grid(row=4, column=0, columnspan=3, sticky="w", pady=(3, 0))
        self.failing_btn.grid_remove()

        of = ttk.LabelFrame(body, text="Action Options", padding=6)
        of.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        of.columnconfigure(1, weight=1)
        ttk.Label(of, text="Weapon").grid(row=0, column=0, sticky="w")
        self.weapon_cb = ttk.Combobox(of, textvariable=self.weapon_var, state="readonly")
        self.weapon_cb.grid(row=0, column=1, sticky="ew", pady=1)
        self.salvo_cb = ttk.Checkbutton(of, text="Torpedo Salvo (+3 Threat)",
                                        variable=self.salvo_var)
        self.salvo_cb.grid(row=1, column=1, sticky="w")
        ttk.Label(of, text="Range to target").grid(row=2, column=0, sticky="w")
        self.range_cb = ttk.Combobox(of, textvariable=self.range_var, values=RANGES,
                                     state="readonly", width=10)
        self.range_cb.grid(row=2, column=1, sticky="w", pady=1)
        ttk.Label(of, text="Targeting Solution").grid(row=3, column=0, sticky="w")
        tsf = ttk.Frame(of)
        tsf.grid(row=3, column=1, sticky="w")
        self.tsol_rb1 = ttk.Radiobutton(tsf, text="Re-roll worst d20", value="reroll",
                                        variable=self.tsol_mode_var)
        self.tsol_rb2 = ttk.Radiobutton(tsf, text="Choose system hit", value="choose",
                                        variable=self.tsol_mode_var)
        self.tsol_rb1.pack(side="left")
        self.tsol_rb2.pack(side="left", padx=6)
        self.tsol_both_lbl = ttk.Label(tsf, text="", style="Good.TLabel")
        self.tsol_both_lbl.pack(side="left")
        ttk.Label(of, text="Scan for Weakness").grid(row=4, column=0, sticky="w")
        swf = ttk.Frame(of)
        swf.grid(row=4, column=1, sticky="w")
        self.scan_rb1 = ttk.Radiobutton(swf, text="+2 Damage", value="damage",
                                        variable=self.scan_mode_var)
        self.scan_rb2 = ttk.Radiobutton(swf, text="Piercing", value="piercing",
                                        variable=self.scan_mode_var)
        self.scan_rb1.pack(side="left")
        self.scan_rb2.pack(side="left", padx=6)
        self.regen_cb = ttk.Checkbutton(of, text="Regenerate Shields: spend 1 Momentum for "
                                                 "+2 Shields", variable=self.regen_boost_var)
        self.regen_cb.grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.secreact_btn = ttk.Button(of, text="Secondary Reactors: spend 2 to restore Reserve "
                                                "Power (1/scene)",
                                       command=lambda: self.use_secondary_reactors())
        self.secreact_btn.grid(row=6, column=0, columnspan=2, sticky="w", pady=(3, 0))
        self.override_cb = ttk.Checkbutton(of, text="Override - acting from another console "
                                                    "(+1 Difficulty)",
                                           variable=self.override_var)
        self.override_cb.grid(row=7, column=0, columnspan=2, sticky="w", pady=(3, 0))
        obf = ttk.Frame(of)
        obf.grid(row=8, column=0, columnspan=2, sticky="w", pady=(3, 0))
        ttk.Label(obf, text="Other Task base Difficulty").pack(side="left")
        self.other_base_sb = ttk.Spinbox(obf, from_=0, to=5, textvariable=self.other_base_var,
                                         width=4, state="readonly")
        self.other_base_sb.pack(side="left", padx=4)

        df = ttk.LabelFrame(body, text="Difficulty", padding=6)
        df.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        df.columnconfigure(1, weight=1)
        self.diff_total_lbl = ttk.Label(df, text="2", style="Diff.TLabel", width=3,
                                        anchor="center")
        self.diff_total_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 8))
        ttk.Label(df, text="Total = Base + Weapon mods + Context + GM Modifier",
                  style="Info.TLabel").grid(row=0, column=1, sticky="w")
        self.diff_parts_lbl = ttk.Label(df, text="", style="Bold.TLabel", wraplength=400,
                                        justify="left")
        self.diff_parts_lbl.grid(row=1, column=1, sticky="w")

        hf = ttk.LabelFrame(body, text="Rule Hints", padding=6)
        hf.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        hf.columnconfigure(0, weight=1)
        self.hints = tk.Text(hf, height=15, width=50, wrap="word", relief="flat",
                             background="#f6f3fb",
                             padx=6, pady=4, font=tkfont.nametofont("TkDefaultFont"))
        self.hints.grid(row=0, column=0, sticky="ew")
        hsb = ttk.Scrollbar(hf, orient="vertical", command=self.hints.yview)
        hsb.grid(row=0, column=1, sticky="ns")
        self.hints.configure(yscrollcommand=hsb.set)
        self.hints.tag_configure("head", font=self.font_bold, foreground="#5b2c83")
        self.hints.tag_configure("key", font=self.font_bold)
        self.hints.tag_configure("warn", foreground="#b03a2e")
        self.hints.tag_configure("good", foreground="#1e7e46")
        self.hints.configure(state="disabled")

        rf = ttk.LabelFrame(body, text="Action Resolver", padding=6)
        rf.grid(row=4, column=0, sticky="ew")
        rf.columnconfigure(5, weight=1)
        ttk.Label(rf, text="Crew Attribute").grid(row=0, column=0, sticky="w")
        self.attr_sb = ttk.Spinbox(rf, from_=4, to=16, textvariable=self.crew_attr_var, width=4)
        self.attr_sb.grid(row=0, column=1, sticky="w")
        ttk.Label(rf, text="Department").grid(row=0, column=2, sticky="e", padx=(8, 2))
        self.dept_sb = ttk.Spinbox(rf, from_=0, to=5, textvariable=self.crew_dept_var, width=4)
        self.dept_sb.grid(row=0, column=3, sticky="w")
        self.focus_cb = ttk.Checkbutton(rf, text="Focus (crit <= Dept)", variable=self.focus_var)
        self.focus_cb.grid(row=0, column=4, columnspan=2, sticky="w", padx=(8, 0))
        ttk.Label(rf, text="Dice pool (d20)").grid(row=1, column=0, sticky="w")
        self.dice_sb = ttk.Spinbox(rf, from_=1, to=MAX_DICE_POOL, textvariable=self.dice_var,
                                   width=4, state="readonly")
        self.dice_sb.grid(row=1, column=1, sticky="w")
        self.dice_cost_lbl = ttk.Label(rf, text="", style="Info.TLabel")
        self.dice_cost_lbl.grid(row=1, column=2, columnspan=4, sticky="w", padx=(8, 0))
        self.autopay_cb = ttk.Checkbutton(rf, text="Auto-pay bonus dice", variable=self.autopay_var)
        self.autopay_cb.grid(row=2, column=0, columnspan=2, sticky="w")
        self.assist_cb = ttk.Checkbutton(rf, text="Ship assists (System + Department)",
                                         variable=self.assist_var)
        self.assist_cb.grid(row=2, column=2, columnspan=4, sticky="w", padx=(8, 0))
        mf = ttk.Frame(rf)
        mf.grid(row=3, column=0, columnspan=6, sticky="w", pady=(4, 0))
        self.auto_rb = ttk.Radiobutton(mf, text="Auto-roll dice", value="auto",
                                       variable=self.mode_var)
        self.auto_rb.pack(side="left")
        self.manual_rb = ttk.Radiobutton(mf, text="Manual successes:", value="manual",
                                         variable=self.mode_var)
        self.manual_rb.pack(side="left", padx=(10, 2))
        self.manual_sb = ttk.Spinbox(mf, from_=0, to=20, textvariable=self.manual_succ_var,
                                     width=4)
        self.manual_sb.pack(side="left")
        of2 = ttk.Frame(rf)
        of2.grid(row=4, column=0, columnspan=6, sticky="w", pady=(4, 0))
        ttk.Label(of2, text="Opposed - defender successes:").pack(side="left")
        self.opp_sb = ttk.Spinbox(of2, from_=0, to=20, textvariable=self.opp_var, width=4)
        self.opp_sb.pack(side="left", padx=2)
        self.opp_info_lbl = ttk.Label(of2, text="", style="Info.TLabel")
        self.opp_info_lbl.pack(side="left", padx=4)
        self.resolve_btn = ttk.Button(rf, text="ROLL & RESOLVE", style="Accent.TButton",
                                      command=self.resolve_action)
        self.resolve_btn.grid(row=5, column=0, columnspan=6, sticky="ew", pady=(8, 4), ipady=4)
        self.result_lbl = ttk.Label(rf, text="", wraplength=440, justify="left")
        self.result_lbl.grid(row=6, column=0, columnspan=6, sticky="w")

    # ------------------------------------------------------------ right panel
    def _build_right(self, body):
        body.columnconfigure(0, weight=1)

        tf = ttk.LabelFrame(body, text="Target Status", padding=6)
        tf.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tf.columnconfigure(0, weight=1)
        self.tgt_name_lbl = ttk.Label(tf, text="-", style="Header.TLabel")
        self.tgt_name_lbl.grid(row=0, column=0, sticky="w")
        self.tgt_info_lbl = ttk.Label(tf, text="", style="Info.TLabel", wraplength=430)
        self.tgt_info_lbl.grid(row=1, column=0, sticky="w")
        self.tgt_bar = ShieldBar(tf)
        self.tgt_bar.grid(row=2, column=0, sticky="ew", pady=3)
        self.tgt_res_lbl = ttk.Label(tf, text="", style="Bold.TLabel")
        self.tgt_res_lbl.grid(row=3, column=0, sticky="w")
        self.tgt_fx_lbl = ttk.Label(tf, text="", wraplength=430, justify="left")
        self.tgt_fx_lbl.grid(row=4, column=0, sticky="w")
        cf = ttk.Frame(tf)
        cf.grid(row=5, column=0, sticky="w", pady=(3, 0))
        ttk.Checkbutton(cf, text="Reserve Power", variable=self.tgt_reserve_var,
                        command=lambda: self.toggle_target_flag("reserve_power",
                                                                self.tgt_reserve_var)).pack(
            side="left")
        ttk.Checkbutton(cf, text="Shields Up", variable=self.tgt_shields_up_var,
                        command=self.toggle_target_shields).pack(side="left", padx=6)
        ttk.Checkbutton(cf, text="Weapons Armed", variable=self.tgt_armed_var,
                        command=lambda: self.toggle_target_flag("weapons_armed",
                                                                self.tgt_armed_var)).pack(
            side="left")
        tcf = ttk.Frame(tf)
        tcf.grid(row=7, column=0, sticky="w", pady=(3, 0))
        self.tgt_pds_cb = ttk.Checkbutton(
            tcf, text="Point Defense active", variable=self.tgt_pds_var,
            command=lambda: self.toggle_target_flag("point_defense_active", self.tgt_pds_var))
        self.tgt_pds_cb.pack(side="left")
        self.tgt_cloak_btn = ttk.Button(tcf, text="Toggle Target Cloak",
                                        command=self.toggle_target_cloak)
        self.tgt_cloak_btn.pack(side="left", padx=6)
        shf = ttk.Frame(tf)
        shf.grid(row=6, column=0, sticky="w", pady=(4, 0))
        ttk.Label(shf, text="Shields:").pack(side="left")
        ttk.Button(shf, text="-1", width=3,
                   command=lambda: self.adjust_target_shields(-1)).pack(side="left", padx=1)
        ttk.Button(shf, text="+1", width=3,
                   command=lambda: self.adjust_target_shields(1)).pack(side="left", padx=1)
        ttk.Spinbox(shf, from_=0, to=99, textvariable=self.tgt_set_shields_var, width=4).pack(
            side="left", padx=(6, 1))
        ttk.Button(shf, text="Set", width=4, command=self.set_target_shields).pack(side="left")
        ttk.Button(shf, text="Restore Full", command=self.restore_target_shields).pack(
            side="left", padx=4)

        dfm = ttk.LabelFrame(body, text="Tactical Combat & Damage Resolver", padding=6)
        alf = ttk.LabelFrame(body, text="Active Quality & Talent Alerts", padding=6)
        alf.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        alf.columnconfigure(0, weight=1)
        self.alerts = tk.Text(alf, height=12, width=50, wrap="word", relief="flat",
                              background="#fbf6ee", padx=6, pady=4,
                              font=tkfont.nametofont("TkDefaultFont"))
        self.alerts.grid(row=0, column=0, sticky="ew")
        asb = ttk.Scrollbar(alf, orient="vertical", command=self.alerts.yview)
        asb.grid(row=0, column=1, sticky="ns")
        self.alerts.configure(yscrollcommand=asb.set)
        self.alerts.tag_configure("head", font=self.font_bold, foreground="#5b2c83")
        self.alerts.tag_configure("warn", foreground="#b03a2e")
        self.alerts.tag_configure("good", foreground="#1e7e46")
        self.alerts.tag_configure("dim", foreground="#6b6b78")
        self.alerts.configure(state="disabled")
        dfm.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        dfm.columnconfigure(2, weight=1)
        self.pending_lbl = ttk.Label(dfm, text="", wraplength=430, justify="left",
                                     style="Good.TLabel")
        self.pending_lbl.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(dfm, text="Weapon").grid(row=1, column=0, sticky="w")
        self.dmg_weapon_cb = ttk.Combobox(dfm, textvariable=self.dmg_weapon_var, state="readonly")
        self.dmg_weapon_cb.grid(row=1, column=1, columnspan=2, sticky="ew", pady=1)
        self.dmg_weapon_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_damage_weapon_change())
        ttk.Label(dfm, text="Base damage").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(dfm, from_=0, to=40, textvariable=self.dmg_base_var, width=5).grid(
            row=2, column=1, sticky="w", pady=1)
        self.dmg_auto_lbl = ttk.Label(dfm, text="", style="Info.TLabel")
        self.dmg_auto_lbl.grid(row=2, column=2, sticky="w", padx=(6, 0))
        ttk.Label(dfm, text="Bonus damage").grid(row=3, column=0, sticky="w")
        ttk.Spinbox(dfm, from_=0, to=12, textvariable=self.dmg_bonus_var, width=5).grid(
            row=3, column=1, sticky="w", pady=1)
        self.dmg_cost_lbl = ttk.Label(dfm, text="", style="Info.TLabel")
        self.dmg_cost_lbl.grid(row=3, column=2, sticky="w", padx=(6, 0))
        ttk.Checkbutton(dfm, text="Piercing (ignore Resistance)", variable=self.pierce_var).grid(
            row=4, column=0, columnspan=3, sticky="w")
        self.devastate_cb = ttk.Checkbutton(dfm, text="Devastating Attack",
                                            variable=self.devastate_var)
        self.devastate_cb.grid(row=5, column=0, columnspan=3, sticky="w")
        self.dmg_preview_lbl = ttk.Label(dfm, text="", wraplength=430, justify="left",
                                         style="Bold.TLabel")
        self.dmg_preview_lbl.grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))
        dbf = ttk.Frame(dfm)
        dbf.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        dbf.columnconfigure(0, weight=1)
        ttk.Button(dbf, text="APPLY DAMAGE TO TARGET", style="Damage.TButton",
                   command=self.apply_damage).grid(row=0, column=0, sticky="ew", ipady=3)
        ttk.Button(dbf, text="Clear Pending", command=self.clear_pending_attack).grid(
            row=0, column=1, sticky="ew", padx=(4, 0))

        hf = ttk.LabelFrame(body, text="System Hit Generator & Shaken Resolver", padding=6)
        hf.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        hf.columnconfigure(1, weight=1)
        self.syshit_btn = ttk.Button(hf, text="Roll System Hit",
                                     command=self.roll_system_hit_clicked)
        self.syshit_btn.grid(row=0, column=0, sticky="w")
        self.syshit_lbl = ttk.Label(hf, text="-", style="Bold.TLabel")
        self.syshit_lbl.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(hf, text="Add Breach There", command=self.breach_last_hit).grid(row=0, column=2)
        tbl = ttk.Frame(hf)
        tbl.grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 0))
        ttk.Label(tbl, text="Table:").pack(side="left")
        tcb = ttk.Combobox(tbl, textvariable=self.hit_table_var, values=list(SYSTEM_HIT_TABLES),
                           state="readonly", width=14)
        tcb.pack(side="left", padx=4)
        tcb.bind("<<ComboboxSelected>>", lambda _e: self.on_hit_table_change())
        self.hit_table_lbl = ttk.Label(hf, text="", style="Info.TLabel")
        self.hit_table_lbl.grid(row=2, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Button(hf, text="Open Shaken Resolver for Target...",
                   command=self.shaken_resolver_clicked).grid(row=3, column=0, columnspan=3,
                                                              sticky="w", pady=(2, 0))

        bf = ttk.LabelFrame(body, text="Breach Tracker (Target)", padding=6)
        bf.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        for col, text in enumerate(("System", "Rtg", "Br.", "", "", "Nature of Breach",
                                    "Failing:")):
            ttk.Label(bf, text=text, style="Bold.TLabel").grid(row=0, column=col, sticky="w",
                                                               padx=2)
        self.breach_rows = {}
        no_condition = "-"
        for i, sysname in enumerate(SYSTEMS, start=1):
            ttk.Label(bf, text=SYSTEM_ABBR[sysname]).grid(row=i, column=0, sticky="w", padx=2)
            rating = ttk.Label(bf, text="-")
            rating.grid(row=i, column=1, sticky="w", padx=2)
            count = ttk.Label(bf, text="0", style="Bold.TLabel", width=3)
            count.grid(row=i, column=2, sticky="w", padx=2)
            ttk.Button(bf, text="-", width=2,
                       command=lambda s=sysname: self.adjust_breach(s, -1)).grid(row=i, column=3)
            ttk.Button(bf, text="+", width=2,
                       command=lambda s=sysname: self.adjust_breach(s, 1)).grid(row=i, column=4)
            cond_var = tk.StringVar(value=no_condition)
            cond_cb = ttk.Combobox(bf, textvariable=cond_var, state="readonly", width=13,
                                   values=[no_condition] + BREACH_NATURES)
            cond_cb.grid(row=i, column=5, sticky="w", padx=(6, 2), pady=1)
            cond_cb.bind("<<ComboboxSelected>>", lambda _e, s=sysname, v=cond_var:
                         self.set_breach_condition_manual(s, "" if v.get() == "-" else v.get()))
            off_btn = ttk.Button(bf, text="\u2192 Offline",
                                 command=lambda s=sysname: self.failing_to_offline(s))
            off_btn.grid(row=i, column=6, sticky="w")
            self.breach_rows[sysname] = {"rating": rating, "count": count, "cond": cond_cb,
                                         "cond_var": cond_var, "offline": off_btn}
        self.breach_total_lbl = ttk.Label(bf, text="", wraplength=430, justify="left")
        self.breach_total_lbl.grid(row=len(SYSTEMS) + 1, column=0, columnspan=7, sticky="w",
                                   pady=(4, 0))

        cf2 = ttk.LabelFrame(body, text="Complications & Effects (Target)", padding=6)
        cf2.grid(row=5, column=0, sticky="ew")
        cf2.columnconfigure(0, weight=1)
        self.comp_lb = tk.Listbox(cf2, height=4, exportselection=False)
        self.comp_lb.grid(row=0, column=0, columnspan=4, sticky="ew")
        cbf = ttk.Frame(cf2)
        cbf.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(cbf, text="Add Complication...", command=self.add_complication).pack(
            side="left")
        ttk.Button(cbf, text="Remove", command=self.remove_complication).pack(side="left", padx=3)
        ttk.Button(cbf, text="Clear Temp Effects", command=self.clear_target_effects).pack(
            side="left")

        stf = ttk.LabelFrame(body, text="Scene Traits", padding=6)
        stf.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        stf.columnconfigure(0, weight=1)
        self.trait_lb = tk.Listbox(stf, height=3, exportselection=False)
        self.trait_lb.grid(row=0, column=0, sticky="ew")
        tbf = ttk.Frame(stf)
        tbf.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(tbf, text="Add Trait...", command=self.add_scene_trait).pack(side="left")
        ttk.Button(tbf, text="Remove", command=self.remove_scene_trait).pack(side="left", padx=3)
        ttk.Label(tbf, text="(Create Trait actions add here)", style="Info.TLabel").pack(
            side="left", padx=4)

    # ---------------------------------------------------------------- the log
    def _build_log(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(parent, height=9, wrap="word", font=self.font_mono,
                                     state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_configure("separator", foreground="#c76b00", font=self.font_bold)
        self.log_text.tag_configure("alert", foreground="#b03a2e")
        self.log_text.tag_configure("success", foreground="#1e7e46")
        self.log_text.tag_configure("fail", foreground="#7d3c98")
        self.log_text.tag_configure("pool", foreground="#1f5fbf")
        bf = ttk.Frame(parent)
        bf.grid(row=0, column=1, sticky="n", padx=(4, 0))
        ttk.Button(bf, text="Clear Log", command=self.clear_log).pack(fill="x")
        ttk.Button(bf, text="Export Log...", command=self.export_log).pack(fill="x", pady=3)

    def _place_log_sash(self):
        """Give the combat panels most of the height; the log keeps ~8 lines."""
        try:
            self.vpane.update_idletasks()
            height = self.vpane.winfo_height()
            if height > 1:
                self.vpane.sashpos(0, max(300, height - 150))
        except tk.TclError:
            pass

    def _bind_mousewheel(self):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, self._on_mousewheel, add="+")
            # Scrolling over spinboxes / comboboxes scrolls the panel instead of
            # silently changing their value.
            for cls in ("TSpinbox", "TCombobox"):
                self.root.bind_class(cls, seq, self._on_mousewheel_break)

    def _on_mousewheel_break(self, event):
        self._on_mousewheel(event)
        return "break"

    def _on_mousewheel(self, event):
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        if widget is None or isinstance(widget, (tk.Text, tk.Listbox, ttk.Treeview)):
            return
        while widget is not None and not isinstance(widget, ScrollableFrame):
            widget = getattr(widget, "master", None)
        if widget is None:
            return
        if getattr(event, "num", None) == 4:
            steps = -1
        elif getattr(event, "num", None) == 5:
            steps = 1
        else:
            delta = event.delta
            steps = -max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120)
        widget.scroll(steps * 2)

    # ============================================================ properties
    def ship_by_name(self, name):
        return next((s for s in self.ships if s.name == name), None)

    @property
    def attacker(self):
        return self.ship_by_name(self.attacker_var.get())

    @property
    def target(self):
        return self.ship_by_name(self.target_var.get())

    def current_action(self):
        return BRIDGE_STATIONS.get(self.station_var.get(), {}).get(self.action_var.get())

    def selected_weapon(self):
        ship = self.attacker
        return ship.weapon(self.weapon_var.get()) if ship else None

    def unique_name(self, base: str) -> str:
        names = {s.name for s in self.ships}
        if base not in names:
            return base
        i = 2
        while f"{base} ({i})" in names:
            i += 1
        return f"{base} ({i})"

    def selected_roster_ship(self):
        sel = self.roster_lb.curselection()
        if sel and sel[0] < len(self.ships):
            return self.ships[sel[0]]
        return None

    # =========================================================== dialogs api
    # (thin wrappers so behaviour can be scripted / tested)
    def ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message, parent=self.root)

    def ask_yes_no_cancel(self, title, message):
        return messagebox.askyesnocancel(title, message, parent=self.root)

    def ask_choice(self, title, prompt, options, default=None):
        return ChoiceDialog.ask(self.root, title, prompt, options, default)

    def ask_string(self, title, prompt, initial=""):
        return simpledialog.askstring(title, prompt, initialvalue=initial, parent=self.root)

    def show_error(self, title, message):
        messagebox.showerror(title, message, parent=self.root)

    def show_info(self, title, message):
        messagebox.showinfo(title, message, parent=self.root)

    def ask_shaken_result(self, ship, reason):
        return ShakenDialog.ask(self.root, ship.name, reason, self.rng)

    def ask_breach_nature(self, ship, system, reason):
        return BreachNatureDialog.ask(self.root, ship.name, system, reason,
                                      ship.breach_condition(system), self.rng)

    # ================================================================ logging
    def log(self, message, tag="info"):
        if tag == "separator":
            line = f"{message}\n"
        else:
            line = f"[{datetime.datetime.now():%H:%M:%S}] [R{self.round}] {message}\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        if self.ask_yes_no("Clear Log", "Clear the combat history log?"):
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")

    def export_log(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export Combat Log", defaultextension=".txt",
            initialfile=f"sta2e_combat_log_{datetime.date.today():%Y%m%d}.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.log_text.get("1.0", "end"))
        except OSError as exc:
            self.show_error("Export Log", f"Could not write log:\n{exc}")
            return
        self.log(f"Combat log exported to {path}.")

    # ================================================================== pools
    def adjust_pool(self, kind, delta):
        if kind == "threat":
            self.threat = max(0, self.threat + delta)
            self.log(f"GM adjusted Threat {delta:+d} -> {self.threat}.", "pool")
        else:
            self.momentum = clamp(self.momentum + delta, 0, MOMENTUM_MAX)
            self.log(f"GM adjusted Momentum {delta:+d} -> {self.momentum}.", "pool")
        self.changed()

    def add_threat(self, amount, reason):
        self.threat = max(0, self.threat + amount)
        self.log(f"Threat {amount:+d} ({reason}) -> {self.threat}.", "pool")

    def add_momentum(self, amount, reason):
        new = self.momentum + amount
        if new > MOMENTUM_MAX:
            self.log(f"Momentum pool full - {new - MOMENTUM_MAX} Momentum lost.", "alert")
            new = MOMENTUM_MAX
        self.momentum = max(0, new)
        self.log(f"Momentum {amount:+d} ({reason}) -> {self.momentum}.", "pool")

    def gain_for_side(self, ship, amount, reason):
        if amount <= 0:
            return
        if ship.side == "Player":
            self.add_momentum(amount, reason)
        else:
            self.add_threat(amount, f"{ship.name}: {reason}")

    def pay_for_side(self, ship, cost, reason) -> bool:
        """Players spend Momentum (shortfall is paid by adding Threat); NPCs spend Threat."""
        if cost <= 0:
            return True
        if ship.side == "Player":
            from_m = min(self.momentum, cost)
            self.momentum -= from_m
            shortfall = cost - from_m
            msg = f"{ship.name} pays {cost} for {reason}: {from_m} Momentum"
            if shortfall:
                self.threat += shortfall
                msg += f" + {shortfall} Threat added (Momentum short)"
            self.log(msg + f". Momentum {self.momentum}, Threat {self.threat}.", "pool")
            return True
        if cost > self.threat:
            if not self.ask_yes_no("Insufficient Threat",
                                   f"{ship.name} needs {cost} Threat for {reason}, but the "
                                   f"pool has only {self.threat}.\n\nProceed anyway?"):
                return False
            self.log(f"GM override: {ship.name} pays {reason} with insufficient Threat.", "alert")
        self.threat = max(0, self.threat - cost)
        self.log(f"{ship.name} spends {cost} Threat for {reason} -> {self.threat}.", "pool")
        return True

    # ============================================================== selection
    def on_station_change(self):
        actions = list(BRIDGE_STATIONS.get(self.station_var.get(), {}))
        self.action_cb.configure(values=actions)
        if self.action_var.get() not in actions:
            self.action_var.set(actions[0] if actions else "")
        self.on_action_change()

    def on_action_change(self):
        self.result_lbl.configure(text="", style="TLabel")
        self.refresh_all()

    def on_selection_change(self):
        self.refresh_all()

    def set_selected_as(self, role):
        ship = self.selected_roster_ship()
        if ship is None:
            return
        (self.attacker_var if role == "attacker" else self.target_var).set(ship.name)
        self.refresh_all()

    def swap_selection(self):
        a, t = self.attacker_var.get(), self.target_var.get()
        self.attacker_var.set(t)
        self.target_var.set(a)
        self.refresh_all()

    def _on_option_change(self):
        if not self._refreshing:
            self._refresh_middle()
            self._refresh_alerts()

    def _on_damage_option_change(self):
        if not self._refreshing:
            self._refresh_damage_preview()

    def _update_gen_info(self):
        a, d = CREW_QUALITY.get(self.gen_quality_var.get(), CREW_QUALITY[DEFAULT_CREW_QUALITY])
        if hasattr(self, "gen_info"):
            self.gen_info.configure(text=f"Attr {a} / Dept {d}")

    # ================================================================ refresh
    def changed(self):
        self.dirty = True
        self.refresh_all()

    def refresh_all(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._refresh_top()
            self._refresh_selectors()
            self._refresh_roster()
            self._refresh_left_status()
            self._refresh_middle()
            self._refresh_right()
        finally:
            self._refreshing = False

    def _refresh_top(self):
        self.threat_lbl.configure(text=str(self.threat))
        self.momentum_lbl.configure(text=str(self.momentum))
        self.round_lbl.configure(text=str(self.round))
        self.file_lbl.configure(text=f"{os.path.basename(self.data_file)}"
                                     f"{'  (unsaved changes)' if self.dirty else ''}")
        self.root.title(f"{APP_NAME}{' *' if self.dirty else ''}")

    def _refresh_selectors(self):
        names = [s.name for s in self.ships]
        self.attacker_cb.configure(values=names)
        self.target_cb.configure(values=names)
        if self.attacker_var.get() not in names:
            players = [s.name for s in self.ships if s.side == "Player"]
            self.attacker_var.set(players[0] if players else (names[0] if names else ""))
        if self.target_var.get() not in names:
            others = [n for n in names if n != self.attacker_var.get()]
            self.target_var.set(others[0] if others else "")
        ship = self.attacker
        # Crew defaults follow the attacker's Crew Quality when the attacker changes.
        if ship is not None and ship.name != self._last_attacker:
            if self.override_var.get() and self._last_attacker is not None:
                self.override_var.set(False)       # Override belonged to the previous ship
            a, d = ship.crew_ratings()
            self.crew_attr_var.set(a)
            self.crew_dept_var.set(d)
            self._last_attacker = ship.name
        weapons = [w.name for w in ship.weapons] if ship else []
        self.weapon_cb.configure(values=weapons)
        if self.weapon_var.get() not in weapons:
            self.weapon_var.set(weapons[0] if weapons else "")
        src = self.ship_by_name(self.pending_attack["attacker"]) if self.pending_attack else ship
        dvals = ([w.name for w in src.weapons] if src else []) + [CUSTOM_WEAPON]
        if self.pending_attack and self.pending_attack["label"] not in dvals:
            dvals.insert(0, self.pending_attack["label"])
        self.dmg_weapon_cb.configure(values=dvals)
        if self.dmg_weapon_var.get() not in dvals:
            self.dmg_weapon_var.set(CUSTOM_WEAPON)

    def _refresh_roster(self):
        sel = self.roster_lb.curselection()
        self.roster_lb.delete(0, "end")
        a, t = self.attacker_var.get(), self.target_var.get()
        for s in self.ships:
            mark = "[A]" if s.name == a else ("[T]" if s.name == t else "   ")
            side = "PC " if s.side == "Player" else "NPC"
            extra = f" B{s.total_breaches()}" if s.total_breaches() else ""
            extra += " SHK" if s.shaken else ""
            self.roster_lb.insert(
                "end", f"{mark} {s.name[:18]:<18} {side} S{s.scale} "
                       f"{s.shields:>2}/{s.max_shields:<2} T{s.turns_used}/{s.scale}{extra}")
        if sel and sel[0] < len(self.ships):
            self.roster_lb.selection_set(sel[0])

    def _ship_status_text(self, s):
        a, d = s.crew_ratings()
        yes = lambda flag: "Yes" if flag else "No"   # noqa: E731
        lines = [
            f"{s.ship_class or 'Unknown class'}",
            f"Side: {s.side}   Scale: {s.scale}   Crew: {s.crew_quality} (Attr {a} / Dept {d})",
            f"Reserve Power: {yes(s.reserve_power)}   Shields Up: {yes(s.shields_up)}   "
            f"Weapons Armed: {yes(s.weapons_armed)}   "
            f"Tractor Beam: Str {s.tractor_strength_rating}",
            "Systems: " + ", ".join(f"{SYSTEM_ABBR[k]} {v}" for k, v in s.systems.items()),
            "Depts: " + ", ".join(f"{k[:5]} {v}" for k, v in s.departments.items()),
        ]
        talents = [t for t in s.talents if talent_kind(t) == TALENT]
        rules = [t for t in s.talents if talent_kind(t) == SPECIAL_RULE]
        lines.append("Talents: " + (", ".join(talents) if talents else "none"))
        if rules:
            lines.append("Special Rules: " + ", ".join(rules))
        breaches = [f"{k} {v}" for k, v in s.breaches.items() if v]
        lines.append("Breaches: " + (", ".join(breaches) if breaches else "none"))
        fx = s.active_effects()
        lines.append("Effects: " + (", ".join(fx) if fx else "none"))
        if s.complications:
            lines.append("Complications: " + "; ".join(s.complications))
        if s.weapons:
            lines.append("Weapons: " + "; ".join(w.describe() for w in s.weapons))
        return "\n".join(lines)

    def _refresh_left_status(self):
        s = self.attacker
        if s is None:
            self.active_name_lbl.configure(text="No ship selected")
            self.active_bar.set_value(0, 0)
            self.active_status_lbl.configure(text="")
            self.active_res_lbl.configure(text="")
            set_enabled(self.cloak_btn, False)
            self.cloak_lbl.configure(text="")
            self.turns_lbl.configure(text="Turns used: - / -")
            self.turns_bar.configure(maximum=1, value=0)
            self.turns_info_lbl.configure(text="")
            return
        self.active_name_lbl.configure(text=s.name)
        self.active_bar.set_value(s.shields, s.max_shields)
        self.active_status_lbl.configure(text=self._ship_status_text(s))
        has_cloak = s.has_talent("Cloaking Device")
        set_enabled(self.cloak_btn, has_cloak)
        self.cloak_btn.configure(text="Decloak (Minor)" if s.cloaked else "Engage Cloak")
        if s.cloaked:
            self.cloak_lbl.configure(text="CLOAKED" + (" - REVEALED" if s.revealed else ""),
                                     style="Alert.TLabel")
        else:
            self.cloak_lbl.configure(text="Visible" if has_cloak else "No Cloaking Device",
                                     style="Info.TLabel")
        self.active_res_lbl.configure(
            text=f"Shields {s.shields}/{s.max_shields}"
                 + (f" (base {s.base_shields} +{s.talent_shield_bonus} talents)"
                    if s.talent_shield_bonus else "")
                 + ("  [LOWERED]" if not s.shields_up else "")
                 + f"\nResistance {s.resistance_text()}")
        self.crew_support_lbl.configure(
            text=f"Crew Support used: {s.crew_support_used} / {s.crew_support_max}"
                 + ("  (x2)" if s.has_talent("Abundant Personnel") else ""))
        if s.small_craft_readiness:
            self.small_craft_lbl.configure(
                text=f"Small Craft out: {s.small_craft_deployed} / {s.small_craft_readiness}"
                     f"  (Scale <= {s.max_small_craft_scale})")
        else:
            self.small_craft_lbl.configure(text="Small Craft Readiness: n/a")
        set_enabled(self.small_craft_minus, s.small_craft_readiness > 0)
        set_enabled(self.small_craft_plus, s.small_craft_readiness > 0)
        over = s.turns_used > s.scale
        self.turns_lbl.configure(text=f"Turns used: {s.turns_used} / {s.scale}"
                                      + ("  - OVER SCALE LIMIT!" if over else ""),
                                 style="Alert.TLabel" if s.turns_used >= s.scale else "Bold.TLabel")
        self.turns_bar.configure(maximum=max(1, s.scale), value=min(s.turns_used, s.scale))
        info = "Systems used this round: " + (", ".join(s.systems_used) if s.systems_used
                                              else "none")
        info += ("\nRe-using a system in the same round costs 1 Threat "
                 + ("(the NPC spends it)." if s.side == "NPC" else "(added to the pool)."))
        if s.brace_for_impact:
            info += "\nBRACE FOR IMPACT: no Major Action on the next turn."
        self.turns_info_lbl.configure(text=info)

    def _refresh_middle(self):
        adef = self.current_action()
        name = self.action_var.get()
        ship, target = self.attacker, self.target
        if adef is None:
            return
        self.kind_lbl.configure(text=adef["kind"].upper(),
                                style=f"{adef['kind']}.TLabel")
        set_enabled(self.override_cb, adef["roll"] or self.override_var.get())
        set_enabled(self.other_base_sb, bool(adef.get("custom_base")))
        warnings = [w for w, level in self._breach_warnings(ship, name, adef) if level == "warn"]
        if warnings:
            self.breach_warn_lbl.configure(text="\n".join(warnings))
            self.breach_warn_lbl.grid()
        else:
            self.breach_warn_lbl.grid_remove()
        if self._failing_systems(ship, name, adef):
            self.failing_btn.grid()
        else:
            self.failing_btn.grid_remove()
        self.actor_lbl.configure(
            text=f"Acting: {ship.name if ship else '-'}   ->   Target: "
                 f"{target.name if target else '-'}")
        weapon = self.selected_weapon() if name == "Fire" else None
        is_fire = name == "Fire"
        set_enabled(self.weapon_cb, is_fire)
        set_enabled(self.salvo_cb, is_fire and weapon is not None and weapon.wtype == "Torpedo")
        tsol = is_fire and ship is not None and ship.targeting_solution
        fts = ship is not None and ship.has_talent("Fast Targeting Systems")
        set_enabled(self.tsol_rb1, tsol and not fts)
        set_enabled(self.tsol_rb2, tsol and not fts)
        self.tsol_both_lbl.configure(text="BOTH" if fts else "")
        set_enabled(self.scan_rb1, name == "Scan for Weakness")
        set_enabled(self.scan_rb2, name == "Scan for Weakness")
        set_enabled(self.regen_cb, name == "Regenerate Shields")
        set_enabled(self.secreact_btn, ship is not None and ship.has_talent("Secondary Reactors")
                    and not ship.secondary_reactors_used and not ship.reserve_power)

        rolls = adef["roll"]
        manual = self.mode_var.get() == "manual"
        for w in (self.attr_sb, self.dept_sb, self.focus_cb, self.dice_sb, self.autopay_cb,
                  self.auto_rb, self.manual_rb):
            set_enabled(w, rolls)
        set_enabled(self.assist_cb, rolls and adef["assist"] is not None)
        set_enabled(self.manual_sb, rolls and manual)
        defense = self._defense_mode(target) if (adef["attack"] and target is not None
                                                 and target is not ship) else None
        set_enabled(self.opp_sb, bool(defense) and manual)
        if defense:
            self.opp_info_lbl.configure(text="(auto-rolled)" if not manual else "(enter value)")
        else:
            self.opp_info_lbl.configure(text="(not opposed)")
        if not rolls:
            self.resolve_btn.configure(text="EXECUTE ACTION")
        else:
            self.resolve_btn.configure(text="RESOLVE (MANUAL SUCCESSES)" if manual
                                       else "ROLL & RESOLVE")

        total, parts = self.compute_current_difficulty()
        if defense and total is not None:
            mods = format_difficulty(sum(v for _l, v in parts[1:]), parts[1:]) if parts[1:] \
                else "no modifiers"
            if manual:
                total = opposed_difficulty(parts, int_var_value(self.opp_var, 0))
                self.diff_total_lbl.configure(text=str(total))
                self.diff_parts_lbl.configure(
                    text=f"OPPOSED: defender's {int_var_value(self.opp_var, 0)} success(es) "
                         f"replace the base; modifiers: {mods}")
            else:
                self.diff_total_lbl.configure(text="?")
                self.diff_parts_lbl.configure(
                    text=f"OPPOSED: defender rolls first, their successes replace the base "
                         f"Difficulty; modifiers: {mods}")
                total = None     # unknown until the defender rolls
        else:
            self.diff_total_lbl.configure(text="-" if total is None else str(total))
            self.diff_parts_lbl.configure(text=format_difficulty(total, parts))
        dice = int_var_value(self.dice_var, 2)
        cost = bonus_dice_cost(dice)
        payer = "Threat" if ship is not None and ship.side == "NPC" else "Momentum"
        self.dice_cost_lbl.configure(
            text=f"Bonus dice cost: {cost} {payer}" if cost else "3rd d20 = 1, 4th = 2, 5th = 3")
        self._write_hints(self._hint_lines(name, adef, ship, target, weapon, total))

    def _write_hints(self, lines):
        self.hints.configure(state="normal")
        self.hints.delete("1.0", "end")
        for text, tag in lines:
            self.hints.insert("end", text + "\n", tag)
        self.hints.configure(state="disabled")

    def _defense_mode(self, target):
        if target is None:
            return None
        if target.evasive:
            return "evasive"
        if target.defensive_fire:
            return "defensive"
        return None

    @staticmethod
    def _be(sysname):
        return "is" if sysname == "Structure" else "are"

    def _breach_warnings(self, ship, name, adef):
        """(text, level) pairs for breach conditions on the systems this action uses.
        level "warn" is shown in the prominent warning box."""
        out = []
        if ship is None or adef is None or name == "Restore":
            return out
        if name == "Prepare":
            for sysname, what in (("Weapons", "arming weapons"), ("Engines", "Prepare for Warp")):
                if ship.breach_condition(sysname) == "Offline":
                    out.append((f"{sysname} {self._be(sysname)} OFFLINE: {what} needs a GM "
                                "override (shields are unaffected).", "info"))
            return out
        included = "(included)" if adef["roll"] else "on tasks that use it"
        for sysname in action_systems(adef):
            cond = ship.breach_condition(sysname)
            be = self._be(sysname)
            if cond == "Offline":
                out.append((f"\u26d4 WARNING: {sysname} {be} OFFLINE! Actions using this "
                            "subsystem cannot be attempted (GM override only).", "warn"))
            elif cond == "Malfunctioning" and sysname in ship.restored_systems:
                out.append((f"{sysname} {be} Malfunctioning - Restore already taken this turn.",
                            "info"))
            elif cond == "Malfunctioning":
                out.append((f"\u26a0 WARNING: {sysname} {be} Malfunctioning! A 'Restore' minor "
                            "action is required this turn before taking Major Actions or tasks "
                            "that use it.", "warn"))
            elif cond == "Failing":
                out.append((f"\u26a0 WARNING: {sysname} {be} Failing: +1 Difficulty {included}. "
                            "The GM may spend 1 Threat to set it Offline (button below).",
                            "warn"))
            elif cond == "Primary Offline":
                out.append((f"\u26a0 {sysname}: Primary Offline, switching to backup - +1 "
                            f"Difficulty {included}.", "warn"))
            elif cond == "Damaged":
                out.append((f"{sysname} {be} Damaged: mostly functional - the GM may spend "
                            "Threat to cause a complication.", "info"))
        return out

    def _hint_lines(self, name, adef, ship, target, weapon, total):
        L = []
        station = self.station_var.get()
        turn_note = {"Major": "  (uses a turn)", "Minor": "  (does not use a turn)",
                     "Free": "  (free - no turn, no Minor Action)"}.get(adef["kind"], "")
        L.append((f"{name.upper()}  -  {station}  -  {adef['kind']} Action{turn_note}", "head"))
        a_val, d_val = int_var_value(self.crew_attr_var, 10), int_var_value(self.crew_dept_var, 3)
        if adef["attr"] and adef["dept"]:
            crit = max(1, d_val) if self.focus_var.get() else 1
            L.append((f"{adef['task_label']}: {adef['attr']} + {adef['dept']}   ->  crew TN "
                      f"{a_val + d_val} "
                      f"({a_val} + {d_val}), crit on {crit} or less", "key"))
        elif adef["roll"]:
            L.append(("Task: Attribute + Department of the assisted task", "key"))
        if adef["assist"]:
            s_sys, s_dept = adef["assist"]
            if ship:
                sv, dv = ship.systems.get(s_sys, 0), ship.departments.get(s_dept, 0)
                L.append((f"Ship Assist: {s_sys} + {s_dept}  ->  TN {sv + dv} ({sv} + {dv}), "
                          f"crit on {max(1, dv)} or less", "key"))
                if ship.breaches.get(s_sys) and not ship.breach_condition(s_sys):
                    L.append((f"  ! {s_sys} has {ship.breaches[s_sys]} breach(es) but no Nature "
                              "of Breach - set it in the Breach Tracker.", "warn"))
            else:
                L.append((f"Ship Assist: {s_sys} + {s_dept}", "key"))
        else:
            L.append(("Ship Assist: none", ""))
        L.append((f"Ship system used: {adef['system']}" if adef["system"]
                  else "Ship system used: none (standard action)", ""))
        if adef["roll"]:
            base_total, parts = self.compute_current_difficulty()
            defense = (self._defense_mode(target) if adef["attack"] and target is not None
                       and target is not ship else None)
            if defense and parts:
                opp = (str(int_var_value(self.opp_var, 0)) if self.mode_var.get() == "manual"
                       else "?")
                mods = "".join(f" {'+' if v > 0 else '-'} {abs(v)} ({label})"
                               for label, v in parts[1:] if v)
                L.append((f"Difficulty (opposed): Defender's successes {opp}{mods} = Total "
                          f"Difficulty {total if total is not None else '?'}", "key"))
            else:
                L.append(("Difficulty: " + format_difficulty_hint(base_total, parts), "key"))
        L.append(("Rule: " + adef["reminder"], ""))

        if name == "Fire":
            if weapon:
                L.append(("Weapon: " + weapon.describe(), "key"))
                for q in weapon.qualities:
                    has_x, desc = WEAPON_QUALITIES.get(q, (False, ""))
                    label = f"{q} {weapon.qualities[q]}" if has_x else q
                    L.append((f"  - {label}: {desc}", ""))
                cost = 3 if self.salvo_var.get() else 1
                if weapon.wtype == "Torpedo":
                    who = ("adds" if ship and ship.side == "Player" else "spends")
                    L.append((f"Cost: torpedo {who} {cost} Threat"
                              + (" (Salvo)" if self.salvo_var.get() else ""), "warn"))
            elif ship:
                L.append((f"! {ship.name} has no weapons - add some in the ship editor.", "warn"))
        if name == "Direct":
            L.append(("Cost: 1 Momentum (NPC: 1 Threat).", "warn"))
        if name in ("Create Trait", "Create / Alter Trait"):
            L.append(("On success you name the new trait, or pick one to alter or remove. "
                      f"Scene traits now: {len(self.scene_traits)}.", "good"))
        if name == "Restore" and ship:
            pending = [s_ for s_ in SYSTEMS if ship.needs_restore(s_)]
            L.append(("Restore: " + (", ".join(pending) + " can be restored this turn."
                                     if pending else "no Malfunctioning subsystem needs it."),
                      "good" if pending else ""))

        alerts = []
        for text, level in self._breach_warnings(ship, name, adef):
            if level == "warn":
                alerts.append(text)
            else:
                L.append((text, ""))
        if ship:
            if adef["kind"] == "Major":
                if ship.turns_used >= ship.scale:
                    alerts.append(f"Turn budget used up: {ship.turns_used}/{ship.scale} "
                                  f"(Scale {ship.scale}).")
                if adef["system"] and adef["system"] in ship.systems_used:
                    alerts.append(f"{adef['system']} already used this round - re-using it "
                                  "costs 1 Threat (NPC spends, player ship adds).")
                if ship.brace_for_impact and name != "Pass":
                    alerts.append("Brace for Impact: this ship cannot take a Major Action now.")
            if adef["requires_power"] and not ship.reserve_power:
                alerts.append("Requires Reserve Power - the ship has none (Regain Power first).")
            if name == "Warp" and not ship.warp_prepared:
                alerts.append("Warp requires a prior Prepare (Warp) minor action.")
            if name == "Fire" and not ship.weapons_armed:
                alerts.append("Weapons are not armed (use Tactical > Prepare).")
            if name == "Fire" and weapon and RANGES.index(self.range_var.get()) > \
                    RANGES.index(weapon.range):
                alerts.append(f"Target range ({self.range_var.get()}) exceeds weapon range "
                              f"({weapon.range}).")
            if name in ("Ram", "Tractor Beam") and range_penalty(self.range_var.get()) > 0:
                alerts.append(f"{name} requires the target within Close range.")
            if name in ("Targeting Solution", "Reveal", "Launch Probe") and \
                    self.range_var.get() == "Extreme":
                alerts.append(f"{name} works only within Long range.")
            if adef["attack"] and ship.evasive:
                alerts.append("This ship is using Evasive Action: its attacks are +1 Difficulty "
                              "(included).")
            if adef["attack"] and ship.attack_pattern:
                L.append(("Attack Pattern active: +1 helm assist die on this attack.", "good"))
            if name == "Fire" and ship.calibrated_weapons:
                L.append(("Weapons calibrated: +1 Damage on this attack.", "good"))
            if name == "Fire" and ship.targeting_solution:
                L.append(("Targeting Solution ready: re-roll 1d20 OR choose the system hit.",
                          "good"))
            if adef["sensor"] and ship.calibrated_sensors:
                L.append(("Sensors calibrated: re-roll 1d20 / ignore 1 trait on this task.",
                          "good"))
            if self._is_rapid_fire_salvo(ship, name, weapon):
                L.append(("Rapid-Fire Torpedo Launcher: salvo gains +1 Damage; Tactical may "
                          "re-roll 1d20 (auto-roll re-rolls a failed die).", "good"))
            if adef["assist"] and ship.ship_assist_dice(adef["assist"][0]) > 1:
                L.append(("Advanced Sensor Suites: the ship assists with 2d20.", "good"))
            elif (adef["assist"] and adef["assist"][0] == "Sensors"
                  and ship.has_talent("Advanced Sensor Suites")):
                alerts.append("Advanced Sensor Suites suppressed: Sensors has breaches.")
            if adef["assist"] and ship.assist_complication_from < 20:
                alerts.append(f"Experimental Vessel: ship assist dice complicate on "
                              f"{ship.assist_complication_from}-20.")
            if name == "Damage Control" and ship.has_talent("Rugged Design"):
                L.append(("Rugged Design: re-roll 1d20 on this repair (auto-roll re-rolls a "
                          "failed die); on success you may spend 2 Momentum to patch a second "
                          "breach.", "good"))
            if ship.cloaked:
                if name in HOSTILE_ACTIONS:
                    alerts.append(f"{ship.name} is CLOAKED: it must decloak (Minor Action) "
                                  f"before {name} - you will be asked to decloak.")
                if name == "Regenerate Shields":
                    alerts.append("Cloaked: shields cannot be raised; regeneration is stored "
                                  "for when they are raised.")
            if ship.rerouted_power and ship.rerouted_power == adef["system"]:
                L.append((f"Rerouted Reserve Power boosts this {adef['system']} task - apply its "
                          "benefit (it is consumed).", "good"))
            if ship.jammed and adef["system"] in ("Communications", "Sensors"):
                alerts.append("Ship is Jammed: +1 Difficulty (included).")
        if target and ship and target is not ship:
            if target.cloaked and not target.revealed and name in TARGETED_ACTIONS:
                alerts.append(f"{target.name} is CLOAKED and not revealed: it cannot be targeted "
                              "(use Sensor Operations > Reveal first).")
            if name == "Reveal":
                if target.cloaked:
                    L.append((f"Reveal vs cloaked {target.name}: success lets ships target it "
                              "until End Round.", "good"))
                else:
                    L.append((f"{target.name} is not cloaked.", ""))
            if adef["attack"] and target.attack_pattern:
                L.append((f"{target.name} is flying an Attack Pattern: -1 Difficulty "
                          "(included).", "good"))
            if (name == "Fire" and weapon is not None and weapon.wtype == "Torpedo"
                    and target.has_talent("Point Defense System") and target.point_defense_active):
                alerts.append(f"{target.name} Point Defense System: Cover, +1 Difficulty vs "
                              "torpedoes (included).")
            if adef["attack"]:
                mode = self._defense_mode(target)
                if mode == "evasive":
                    alerts.append(f"{target.name} is using Evasive Action: OPPOSED task - the "
                                  "defender rolls Daring + Conn (assist Structure + Conn) first; "
                                  "their successes replace the base Difficulty (other modifiers "
                                  "still apply, ties go to the attacker).")
                elif mode == "defensive":
                    alerts.append(f"{target.name} is using Defensive Fire: OPPOSED task - the "
                                  "defender rolls Daring + Security (assist Weapons + Security) "
                                  "first; their successes replace the base Difficulty.")
                if target.weakness_scanned:
                    L.append((f"{target.name} was scanned for weakness: "
                              + ("+2 Damage" if target.weakness_scanned == "damage"
                                 else "Piercing") + " on this attack.", "good"))
                if target.effective_resistance:
                    L.append((f"Target Resistance {target.effective_resistance}"
                              + (" (Modulated Shields)" if target.resistance_bonus else ""), ""))
        elif adef["needs_target"]:
            alerts.append("Select a target ship (different from the acting ship).")
        for a in alerts:
            L.append(("! " + a, "warn"))
        return L

    def _refresh_right(self):
        t = self.target
        if t is None:
            self.tgt_name_lbl.configure(text="No target selected")
            self.tgt_info_lbl.configure(text="")
            self.tgt_bar.set_value(0, 0)
            self.tgt_res_lbl.configure(text="")
            self.tgt_fx_lbl.configure(text="")
            for row in self.breach_rows.values():
                row["rating"].configure(text="-")
                row["count"].configure(text="0")
                row["cond_var"].set("-")
                set_enabled(row["cond"], False)
                set_enabled(row["offline"], False)
            self.breach_total_lbl.configure(text="")
            self.comp_lb.delete(0, "end")
        else:
            a, d = t.crew_ratings()
            self.tgt_name_lbl.configure(text=t.name)
            self.tgt_info_lbl.configure(
                text=f"{t.ship_class or 'Unknown class'} | {t.side} | Scale {t.scale} | "
                     f"Crew {t.crew_quality} ({a}/{d}) | Turns {t.turns_used}/{t.scale}")
            self.tgt_bar.set_value(t.shields, t.max_shields)
            self.tgt_res_lbl.configure(
                text=f"Resistance: {t.resistance_text()}\nShaken thresholds: "
                     f"<{t.max_shields * 0.5:g} / <{t.max_shields * 0.25:g}")
            fx = t.active_effects()
            self.tgt_fx_lbl.configure(text="Effects: " + (", ".join(fx) if fx else "none"),
                                      style="Alert.TLabel" if t.shaken else "TLabel")
            self.tgt_reserve_var.set(t.reserve_power)
            self.tgt_shields_up_var.set(t.shields_up)
            self.tgt_armed_var.set(t.weapons_armed)
            self.tgt_set_shields_var.set(self._target_shield_value(t))
            for sysname, row in self.breach_rows.items():
                row["rating"].configure(text=str(t.systems.get(sysname, 0)))
                n = t.breaches.get(sysname, 0)
                dev = "D" if sysname in t.devastating_systems else ""
                row["count"].configure(text=f"{n}{dev}",
                                       style="Alert.TLabel" if n else "Bold.TLabel")
                cond = t.breach_condition(sysname)
                row["cond_var"].set(cond or "-")
                set_enabled(row["cond"], n > 0)
                set_enabled(row["offline"], cond == "Failing")
            total = t.total_breaches()
            msg = (f"Total breaches: {total}   (Scale {t.scale})   D = Devastating\n"
                   "\u2192 Offline: GM spends 1 Threat to set a Failing system Offline.")
            if total and total >= t.scale:
                msg += "\n! Breaches have reached the ship's Scale - check the rulebook for " \
                       "disabled systems / ship destruction."
            self.breach_total_lbl.configure(text=msg,
                                            style="Alert.TLabel" if total >= t.scale and total
                                            else "TLabel")
            self.comp_lb.delete(0, "end")
            for c in t.complications:
                self.comp_lb.insert("end", c)
        self.trait_lb.delete(0, "end")
        for trait in self.scene_traits:
            self.trait_lb.insert("end", trait)
        self.syshit_lbl.configure(text=self.last_system_hit or "-")
        self.syshit_btn.configure(text=f"Roll System Hit (d{self.hit_table[-1][1]})")
        self.hit_table_lbl.configure(text="  ".join(
            f"{lo}-{hi} {SYSTEM_ABBR[n]}" if lo != hi else f"{lo} {SYSTEM_ABBR[n]}"
            for lo, hi, n in self.hit_table))
        set_enabled(self.tgt_pds_cb, t is not None and t.has_talent("Point Defense System"))
        set_enabled(self.tgt_cloak_btn, t is not None and t.has_talent("Cloaking Device"))
        self.tgt_pds_var.set(bool(t is not None and t.has_talent("Point Defense System")
                                  and t.point_defense_active))
        self._refresh_alerts()
        pa = self.pending_attack
        if pa:
            bits = [f"PENDING HIT: {pa['attacker']} -> {pa['target']} with {pa['label']}"]
            if pa["calibrate"]:
                bits.append(f"Calibrated +{pa['calibrate']}")
            if pa["scan_damage"]:
                bits.append(f"Weakness +{pa['scan_damage']}")
            if pa.get("rapid_fire"):
                bits.append(f"Rapid-Fire salvo +{pa['rapid_fire']}")
            if pa["choose_system"]:
                bits.append("Targeting Solution: choose system")
            if pa["ram"]:
                bits.append("Collision: both ships take damage")
            self.pending_lbl.configure(text=" | ".join(bits))
        else:
            self.pending_lbl.configure(text="No pending attack - damage can still be applied "
                                            "manually to the selected target.")
        self._refresh_damage_preview()

    def _talent_status(self, ship, role):
        """Live, context-aware status lines for each talent / special rule of a ship."""
        name = self.action_var.get()
        weapon = self.selected_weapon() if name == "Fire" else None
        acting = role == "attacker"
        lines = []
        for t in ship.talents:
            tag = ""
            if t in TALENT_RESISTANCE_BONUS:
                text = (f"+{TALENT_RESISTANCE_BONUS[t]} Resistance included "
                        f"(Resistance {ship.effective_resistance}).")
            elif t in TALENT_SHIELD_BONUS:
                text = (f"+{TALENT_SHIELD_BONUS[t]} max Shields included (max "
                        f"{ship.max_shields}).")
            elif t == "Cloaking Device":
                if ship.cloaked:
                    text = ("CLOAKED: Shields 0 and cannot be raised; cannot attack until it "
                            "decloaks (Minor Action). "
                            + ("REVEALED this round - it can be targeted." if ship.revealed
                               else "Must be revealed (Reveal, Difficulty 3) before it can be "
                                    "targeted."))
                    tag = "warn"
                else:
                    text = "Not engaged. Use Engage Cloak in Active Ship Status."
            elif t == "Extensive Shuttlebays":
                text = (f"Small Craft Readiness {ship.small_craft_readiness} (Scale - 1); "
                        "can support Scale 2 craft such as runabouts.")
            elif t == "Rapid-Fire Torpedo Launcher":
                text = "Torpedo Salvo: +1 Damage and Tactical may re-roll 1d20."
                if (acting and weapon is not None and weapon.wtype == "Torpedo"
                        and self.salvo_var.get()):
                    text = "ACTIVE on this salvo: +1 Damage, re-roll 1d20 on the attack."
                    tag = "good"
            elif t == "Fast Targeting Systems":
                text = "Targeting Solution grants BOTH the d20 re-roll AND system choice."
                if acting and ship.targeting_solution:
                    text = "Targeting Solution ready: re-roll AND choose the system hit."
                    tag = "good"
            elif t == "Advanced Sensor Suites":
                if ship.breaches.get("Sensors", 0):
                    text = "SUPPRESSED: Sensors has breaches - ship assists with 1d20."
                    tag = "warn"
                else:
                    text = "Assisting a Sensors task: the ship rolls 2d20 instead of 1d20."
                    adef = self.current_action()
                    if acting and adef and adef["assist"] and adef["assist"][0] == "Sensors":
                        tag = "good"
            elif t in EXPERIMENTAL_RULES:
                text = (f"Ship assist dice complicate on {ship.assist_complication_from}-20.")
                tag = "warn" if acting and (self.current_action() or {}).get("assist") else ""
            elif t == "Abundant Personnel":
                text = (f"Crew Support doubled: {ship.crew_support_max} "
                        f"({ship.crew_support_used} used).")
            elif t == "Point Defense System":
                if ship.point_defense_active:
                    text = "ACTIVE: torpedo attacks against this ship are +1 Difficulty (Cover)."
                    if (not acting and name == "Fire" and self.attacker is not None):
                        aw = self.selected_weapon()
                        if aw is not None and aw.wtype == "Torpedo":
                            tag = "warn"
                else:
                    text = "Inactive (toggle in Target Status)."
            else:
                text = talent_text(t)
            kind = " [Special Rule]" if talent_kind(t) == SPECIAL_RULE else ""
            if t not in STARSHIP_TALENTS:
                kind = " [custom]"
            lines.append((f"  - {t}{kind}: {text}", tag))
        return lines

    def _talent_alert_lines(self):
        lines = []
        if self.scene_traits:
            lines.append(("SCENE TRAITS: " + "; ".join(self.scene_traits), "head"))
        ship, target = self.attacker, self.target
        for role, s in (("attacker", ship), ("target", target)):
            if s is None or (role == "target" and s is ship):
                continue
            lines.append((f"{'ATTACKER' if role == 'attacker' else 'TARGET'}: {s.name}", "head"))
            status = self._talent_status(s, role)
            lines.extend(status if status else [("  (no talents or special rules)", "dim")])
            for sysname in SYSTEMS:
                cond = s.breach_condition(sysname)
                if cond:
                    restored = " - restored this turn" if sysname in s.restored_systems else ""
                    lines.append((f"  - BREACH {sysname} x{s.breaches[sysname]}: "
                                  f"{BREACH_SHORT[cond]}{restored}. "
                                  f"{breach_nature_description(cond)}",
                                  "dim" if cond == "Damaged" else "warn"))
        weapon = None
        pa = self.pending_attack
        if pa and pa.get("weapon") is not None:
            weapon = pa["weapon"]
        elif self.action_var.get() == "Fire":
            weapon = self.selected_weapon()
        if weapon is not None:
            lines.append((f"WEAPON: {weapon.name} ({weapon.wtype}, Dmg {weapon.damage})", "head"))
            if not weapon.qualities:
                lines.append(("  (no qualities)", "dim"))
            for q, v in weapon.qualities.items():
                has_x, desc = WEAPON_QUALITIES.get(q, (False, ""))
                label = f"{q} {v}" if has_x else q
                tag = "warn" if q in ("Cumbersome", "Devastating", "Persistent", "Dampening",
                                      "Jamming", "Slowing", "High Yield") else ""
                lines.append((f"  - {label}: {desc}", tag))
        return lines

    def _refresh_alerts(self):
        self.alerts.configure(state="normal")
        self.alerts.delete("1.0", "end")
        for text, tag in self._talent_alert_lines():
            self.alerts.insert("end", text + "\n", tag)
        self.alerts.configure(state="disabled")

    def _damage_weapon(self):
        if self.pending_attack:
            return self.pending_attack["weapon"]
        ship = self.attacker
        return ship.weapon(self.dmg_weapon_var.get()) if ship else None

    def _damage_payer_is_npc(self):
        pa = self.pending_attack
        payer = self.ship_by_name(pa["attacker"]) if pa else self.attacker
        return payer is not None and payer.side == "NPC"

    def _refresh_damage_preview(self):
        weapon = self._damage_weapon()
        pa = self.pending_attack
        t = (self.ship_by_name(pa["target"]) if pa else None) or self.target
        auto = pending_damage_bonus(pa)
        self.dmg_auto_lbl.configure(text=f"+{auto} automatic (see pending hit)" if pa else "")
        bonus = int_var_value(self.dmg_bonus_var, 0)
        each = bonus_damage_cost_each(weapon)
        dev_cost = devastating_attack_cost(weapon)
        cost = bonus * each + (dev_cost if self.devastate_var.get() else 0)
        payer = "Threat" if self._damage_payer_is_npc() else "Momentum"
        self.dmg_cost_lbl.configure(text=f"{each} {payer} per +1  (total cost: {cost})")
        spread_note = (", 1 with Spread" if weapon is not None and weapon.has(AREA_OR_SPREAD)
                       else "")
        self.devastate_cb.configure(text=f"Devastating Attack ({dev_cost} {payer}{spread_note}: "
                                         "+1 extra system hit / breach)")
        if t is None:
            self.dmg_preview_lbl.configure(text="Select a target.")
            return
        raw = int_var_value(self.dmg_base_var, 0) + auto + bonus
        out = resolve_shield_damage(t.shields, t.max_shields, raw, t.effective_resistance,
                                    self.pierce_var.get())
        res_txt = "Piercing" if self.pierce_var.get() else f"Resistance {out.resistance_applied}"
        text = (f"vs {t.name}: Raw {raw} - {res_txt} = {out.final_damage} damage  ->  Shields "
                f"{out.shields_before} -> {out.shields_after}/{t.max_shields}")
        consequences = [f"SHAKEN ({r})" for r in out.shaken_reasons]
        consequences += [f"BREACH ({r})" for r in out.breach_reasons]
        if self.devastate_var.get():
            consequences.append("Devastating Attack: +1 breach" if out.final_damage > 0
                                else "Devastating Attack: no effect (0 damage, not charged)")
        if consequences:
            text += "\nPredicted: " + "; ".join(consequences)
        self.dmg_preview_lbl.configure(text=text)

    # ============================================================ turn logic
    def adjust_turns(self, delta):
        ship = self.attacker
        if ship is None:
            return
        ship.turns_used = max(0, ship.turns_used + delta)
        if delta > 0:
            ship.restored_systems = []       # a turn ended: Restore must be taken again
        if delta > 0 and ship.brace_for_impact:
            ship.brace_for_impact = False
            self.log(f"{ship.name} spends its turn braced (no Major Action). Brace for Impact "
                     "cleared.")
        self.log(f"{ship.name}: turns used manually set to {ship.turns_used}/{ship.scale}.")
        if ship.turns_used > ship.scale:
            self.log(f"WARNING: {ship.name} exceeds its Scale turn limit "
                     f"({ship.turns_used}/{ship.scale}).", "alert")
        self.changed()

    def adjust_pool_counter(self, attr, delta):
        ship = self.attacker
        if ship is None:
            return
        limit = ship.crew_support_max if attr == "crew_support_used" else ship.small_craft_readiness
        current = getattr(ship, attr)
        pool = "Crew Support" if attr == "crew_support_used" else "Small Craft Readiness"
        if delta > 0 and current >= limit:
            self.log(f"{ship.name}: no {pool} left.", "alert")
            return
        new = clamp(current + delta, 0, max(limit, current))
        if new == current:
            return
        setattr(ship, attr, new)
        label = "Crew Support used" if attr == "crew_support_used" else "Small craft deployed"
        self.log(f"{ship.name}: {label} {new}/{limit}.")
        self.changed()

    def reset_turns(self):
        ship = self.attacker
        if ship is None:
            return
        ship.turns_used = 0
        ship.systems_used = []
        self.log(f"{ship.name}: turn counter reset.")
        self.changed()

    def end_round(self):
        ended = self.round
        for ship in self.ships:
            for eff in list(ship.persistent_effects):
                self._inflict_damage(ship, eff["amount"], bool(eff.get("piercing")),
                                     f"Persistent damage ({eff['source']})")
                eff["rounds"] = eff.get("rounds", 1) - 1
            ship.persistent_effects = [e for e in ship.persistent_effects if e["rounds"] > 0]
        for ship in self.ships:
            ship.reset_round()
        self.override_var.set(False)
        self.log(f"--- END OF ROUND {ended} ---", "separator")
        self.round += 1
        self.log(f"Round {self.round} begins: turn counters, Modulate Shields, Evasive Action, "
                 "Defensive Fire, Attack Pattern, Jammed, Slowed and Shaken flags reset.")
        self.changed()

    # ========================================================== action logic
    def compute_current_difficulty(self):
        name = self.action_var.get()
        weapon = self.selected_weapon() if name == "Fire" else None
        return compute_difficulty(name, self.current_action(), self.attacker, weapon,
                                  self.range_var.get(), int_var_value(self.gm_mod_var, 0),
                                  target=self.target, override=self.override_var.get(),
                                  custom_base=int_var_value(self.other_base_var, 2))

    def resolve_action(self):
        ship = self.attacker
        if ship is None:
            self.show_error("No acting ship", "Select an Attacker / acting ship first.")
            return
        name = self.action_var.get()
        adef = self.current_action()
        if adef is None:
            return
        if name == "Override":
            self._start_override(ship)
            return
        target = self.target
        if adef["needs_target"] and (target is None or target is ship):
            self.show_error("No target", f"{name} needs a target ship different from the "
                                         "acting ship.")
            return
        weapon = self.selected_weapon() if name == "Fire" else None
        if name == "Fire" and weapon is None:
            self.show_error("No weapon", f"{ship.name} has no weapon selected. Add weapons in "
                                         "the ship editor.")
            return
        reaction = (adef["kind"] == "Major" and bool(ship.readied_action)
                    and name not in ("Ready", "Pass") and self.ask_yes_no(
                        "Readied action", f"{ship.name} has a readied action:\n"
                                          f"{ship.readied_action}\n\nResolve {name} as that "
                                          "reaction (no extra turn)?"))
        reuse_threat = self._precheck_action(ship, name, adef, weapon, target, reaction)
        if reuse_threat is None:
            return
        difficulty, parts = self.compute_current_difficulty()
        if not self._pay_action_costs(ship, name, adef, weapon, reuse_threat):
            self.refresh_all()
            return
        if ship.cloaked and name in HOSTILE_ACTIONS:   # the GM agreed to decloak in precheck
            self._decloak(ship, f" to use {name}")
        outcome = None
        if adef["roll"]:
            outcome = self._perform_task(ship, name, adef, target, difficulty, weapon, parts)
        else:
            self.result_lbl.configure(text=f"{name} executed.", style="Good.TLabel")
            self.log(f"{ship.name}: {name} ({adef['kind']} Action).")
        if adef["requires_power"] and ship.reserve_power:
            ship.reserve_power = False
            self.log(f"{ship.name} consumes its Reserve Power.")
        if reaction:
            if adef["system"] and adef["system"] not in ship.systems_used:
                ship.systems_used.append(adef["system"])
            self.log(f"{ship.name}: {name} resolved as the readied reaction "
                     f"({ship.readied_action}) - no extra turn used.", "success")
            ship.readied_action = ""
        elif adef["kind"] == "Major":
            self._consume_turn(ship, adef["system"])
        self._apply_effect(ship, name, adef, target, weapon, outcome)
        if self.override_var.get() and (adef["kind"] == "Major" or adef["roll"]):
            self.override_var.set(False)
            self.log(f"Override used for {name}"
                     + (" (+1 Difficulty applied)." if adef["roll"] else " (no task roll)."))
        self.changed()

    def _precheck_action(self, ship, name, adef, weapon, target=None, reaction=False):
        """Warnings / confirmations. Returns Threat to spend for system re-use, or None to abort."""
        reuse_threat = 0
        band = self.range_var.get()
        if name in ("Cloak", "Decloak") and not ship.has_talent("Cloaking Device"):
            self.show_error("Cloaking Device", f"{ship.name} does not have the Cloaking Device "
                                               "talent.")
            return None
        if name == "Cloak" and ship.cloaked:
            self.show_info("Cloak", f"{ship.name} is already cloaked.")
            return None
        if adef["kind"] == "Major":
            if ship.brace_for_impact and name != "Pass" and not reaction and not self.ask_yes_no(
                    "Brace for Impact!", f"{ship.name} is bracing for impact and cannot take a "
                                         "Major Action this turn.\n\nOverride and act anyway?"):
                return None
            if ship.turns_used >= ship.scale and not reaction:
                if not self.ask_yes_no(
                        "Turn budget exceeded",
                        f"{ship.name} has already used {ship.turns_used}/{ship.scale} turns "
                        f"this round (Scale {ship.scale}).\n\nTake another turn anyway?"):
                    return None
                self.log(f"WARNING: {ship.name} exceeds its Scale turn limit (GM override).",
                         "alert")
            sysname = adef["system"]
            if sysname and sysname in ship.systems_used:
                threat_verb = "spend" if ship.side == "NPC" else "add"
                ans = self.ask_yes_no_cancel(
                    "System already used",
                    f"{ship.name} already used its {sysname} system this round.\n\n"
                    f"Yes = {threat_verb} 1 Threat to use it again\n"
                    "No = proceed WITHOUT spending Threat (GM override)\n"
                    "Cancel = abort the action")
                if ans is None:
                    return None
                if ans:
                    reuse_threat = 1
                else:
                    self.log(f"WARNING: {ship.name} re-uses {sysname} without spending Threat "
                             "(GM override).", "alert")
        if adef["requires_power"] and not ship.reserve_power and not self.ask_yes_no(
                "No Reserve Power", f"{name} requires Reserve Power and {ship.name} has none."
                                    "\n\nProceed anyway?"):
            return None
        if name == "Warp" and not ship.warp_prepared and not self.ask_yes_no(
                "Not prepared", f"{ship.name} has not used Prepare (Warp).\n\nProceed anyway?"):
            return None
        if name == "Fire":
            if not ship.weapons_armed and not self.ask_yes_no(
                    "Weapons not armed", f"{ship.name}'s weapons are not armed.\n\nFire anyway?"):
                return None
            if RANGES.index(band) > RANGES.index(weapon.range) and not self.ask_yes_no(
                    "Out of range", f"Target is at {band} range but {weapon.name} reaches "
                                    f"{weapon.range}.\n\nFire anyway?"):
                return None
        if name in ("Ram", "Tractor Beam") and range_penalty(band) > 0 and not self.ask_yes_no(
                "Out of range", f"{name} requires the target within Close range (currently "
                                f"{band}).\n\nProceed anyway?"):
            return None
        if name in ("Targeting Solution", "Reveal", "Launch Probe") and band == "Extreme" and \
                not self.ask_yes_no("Out of range", f"{name} works within Long range.\n\n"
                                                    "Proceed anyway?"):
            return None
        if name == "Regenerate Shields" and ship.cloaked and not self.ask_yes_no(
                "Cloaked", f"{ship.name} is cloaked: its shields cannot be raised. Regenerate the "
                           "lowered shields anyway (restored when they are raised)?"):
            return None
        if (target is not None and target is not ship and target.cloaked and not target.revealed
                and name in TARGETED_ACTIONS):
            if not self.ask_yes_no(
                    "Target cloaked", f"{target.name} is cloaked and has not been revealed, so it "
                                      "cannot be targeted. Use Sensor Operations > Reveal first."
                                      "\n\nProceed anyway (GM override)?"):
                return None
            self.log(f"GM override: {ship.name} targets the cloaked {target.name}.", "alert")
        systems = [] if name in ("Restore", "Prepare") else action_systems(adef)
        for sysname in systems:
            if ship.breach_condition(sysname) == "Offline":
                if not self.ask_yes_no(
                        "Subsystem offline",
                        f"{ship.name}'s {sysname} {self._be(sysname)} OFFLINE - actions using it "
                        "cannot be attempted.\n\nGM override and attempt it anyway?"):
                    return None
                self.log(f"GM override: {ship.name} uses its OFFLINE {sysname}.", "alert")
        if adef["roll"] or adef["kind"] == "Major":
            for sysname in systems:
                if not ship.needs_restore(sysname):
                    continue
                ans = self.ask_yes_no_cancel(
                    "Restore required",
                    f"{ship.name}'s {sysname} {self._be(sysname)} Malfunctioning: a Restore minor "
                    "action is required this turn before any task using it.\n\n"
                    "Yes = take the Restore minor action now\n"
                    "No = proceed without Restore (GM override)\n"
                    "Cancel = abort the action")
                if ans is None:
                    return None
                if ans:
                    self._mark_restored(ship, sysname, f" before {name}")
                else:
                    self.log(f"GM override: {ship.name} uses its Malfunctioning {sysname} "
                             "without Restore.", "alert")
        if ship.cloaked and name in HOSTILE_ACTIONS and not self.ask_yes_no(
                "Cloaked", f"{ship.name} is cloaked and cannot attack or use its tractor "
                           "beam.\n\nDecloak now (Minor Action) and continue?"):
            return None
        return reuse_threat

    def _pay_action_costs(self, ship, name, adef, weapon, reuse_threat) -> bool:
        spend, add_threat, items = 0, 0, []
        if name == "Direct":
            spend += 1
            items.append("Direct")
        if name == "Fire" and weapon is not None and weapon.wtype == "Torpedo":
            n = 3 if self.salvo_var.get() else 1
            if ship.side == "Player":
                add_threat += n
            else:
                spend += n
            items.append("torpedo salvo" if self.salvo_var.get() else "torpedo")
        if adef["roll"] and self.autopay_var.get():
            dice = clamp(int_var_value(self.dice_var, 2), 1, MAX_DICE_POOL)
            cost = bonus_dice_cost(dice)
            if cost:
                spend += cost
                items.append(f"{dice - 2} bonus d20")
        if reuse_threat:
            items.append("system re-use")
            if ship.side == "Player":
                add_threat += reuse_threat
        if ship.side == "NPC":
            return self.pay_for_side(ship, spend + reuse_threat, " + ".join(items)) \
                if spend + reuse_threat else True
        if spend and not self.pay_for_side(ship, spend, " + ".join(items)):
            return False
        if add_threat:
            reasons = [i for i in items if i in ("torpedo", "torpedo salvo", "system re-use")]
            self.add_threat(add_threat, f"{ship.name}: {' + '.join(reasons)}")
        return True

    def _roll_defense(self, target, mode):
        attr_name, dept_name, assist = (("Daring", "Conn", ("Structure", "Conn"))
                                        if mode == "evasive"
                                        else ("Daring", "Security", ("Weapons", "Security")))
        a, d = target.crew_ratings()
        dice = [make_die(a + d, d, "crew", self.rng) for _ in range(2)]
        s_sys, s_dept = assist
        dice.append(make_die(target.systems[s_sys] + target.departments[s_dept],
                             target.departments[s_dept], "ship", self.rng,
                             comp_from=target.assist_complication_from))
        out = evaluate_task(dice, 0)
        desc = (f"Opposed: {target.name} defends with {attr_name} + {dept_name} "
                f"[{format_dice(dice)}] -> {out.successes} success(es).")
        return out, desc

    def _uses_tsol_reroll(self, ship, name):
        return (name == "Fire" and ship.targeting_solution
                and (self.tsol_mode_var.get() == "reroll"
                     or ship.has_talent("Fast Targeting Systems")))

    def _uses_tsol_choice(self, ship, name):
        return (name == "Fire" and ship.targeting_solution
                and (self.tsol_mode_var.get() == "choose"
                     or ship.has_talent("Fast Targeting Systems")))

    def _is_rapid_fire_salvo(self, ship, name, weapon):
        return (name == "Fire" and weapon is not None and weapon.wtype == "Torpedo"
                and self.salvo_var.get() and ship.has_talent("Rapid-Fire Torpedo Launcher"))

    def _perform_task(self, ship, name, adef, target, difficulty, weapon=None, parts=None):
        attr_v = int_var_value(self.crew_attr_var, 10)
        dept_v = int_var_value(self.crew_dept_var, 3)
        crit = max(1, dept_v) if self.focus_var.get() else 1
        n = clamp(int_var_value(self.dice_var, 2), 1, MAX_DICE_POOL)
        manual = self.mode_var.get() == "manual"
        opposition = None
        defender_comps = 0
        defense = self._defense_mode(target) if (adef["attack"] and target is not None) else None
        if defense:
            if manual:
                opposition = int_var_value(self.opp_var, 0)
                self.log(f"Opposed: {target.name} scored {opposition} success(es) (entered).")
            else:
                opp_out, desc = self._roll_defense(target, defense)
                opposition = opp_out.successes
                defender_comps = opp_out.complications
                self.opp_var.set(opposition)
                self.log(desc)
                if defender_comps:
                    self.log(f"{target.name}: {defender_comps} complication(s) on its defence "
                             "roll" + (f" (ship dice complicate on "
                                       f"{target.assist_complication_from}-20)"
                                       if target.assist_complication_from < 20 else "")
                             + " - GM: add a complication or let them buy it off.", "alert")
            difficulty = opposed_difficulty(parts or [("Base", 0)], opposition)
            self.log(f"Opposed task: Difficulty = defender's {opposition} success(es) + "
                     f"modifiers = {difficulty}.")
        notes = []
        if manual:
            total = int_var_value(self.manual_succ_var, 0)
            outcome = outcome_from_successes(total, difficulty, opposition)
            dice_text = f"{total} success(es) entered manually"
            if adef["sensor"] and ship.calibrated_sensors:
                notes.append("Calibrated Sensors: apply the re-roll / ignore-trait benefit")
            if self._uses_tsol_reroll(ship, name):
                notes.append("Targeting Solution: apply the d20 re-roll")
            if self._is_rapid_fire_salvo(ship, name, weapon):
                notes.append("Rapid-Fire Torpedo Launcher: Tactical may re-roll 1d20")
            if name == "Damage Control" and ship.has_talent("Rugged Design"):
                notes.append("Rugged Design: apply the 1d20 re-roll")
        else:
            dice = [make_die(attr_v + dept_v, crit, "crew", self.rng) for _ in range(n)]
            rerolls = []
            if self._uses_tsol_reroll(ship, name):
                rerolls.append("Targeting Solution")
            if self._is_rapid_fire_salvo(ship, name, weapon):
                rerolls.append("Rapid-Fire Torpedo Launcher")
            if adef["sensor"] and ship.calibrated_sensors:
                rerolls.append("Calibrated Sensors")
            if name == "Damage Control" and ship.has_talent("Rugged Design"):
                rerolls.append("Rugged Design")
            for source in rerolls:
                rr = reroll_worst(dice, self.rng)
                notes.append(f"{source} re-roll {rr[0]} -> {rr[1]}" if rr
                             else f"{source} re-roll not needed")
            if self.assist_var.get() and adef["assist"]:
                s_sys, s_dept = adef["assist"]
                count = ship.ship_assist_dice(s_sys)
                if count > 1:
                    notes.append(f"Advanced Sensor Suites: {count} ship assist dice")
                elif s_sys == "Sensors" and ship.has_talent("Advanced Sensor Suites"):
                    notes.append("Advanced Sensor Suites suppressed (Sensors breached)")
                if ship.assist_complication_from < 20:
                    notes.append(f"ship dice complicate on {ship.assist_complication_from}-20 "
                                 "(Experimental Vessel)")
                for _ in range(count):
                    dice.append(make_die(
                        ship.systems.get(s_sys, 0) + ship.departments.get(s_dept, 0),
                        ship.departments.get(s_dept, 0), "ship", self.rng,
                        comp_from=ship.assist_complication_from))
            if adef["attack"] and ship.attack_pattern:
                ca, cd = ship.crew_ratings()
                dice.append(make_die(ca + cd, cd, "assist", self.rng))
                notes.append("Attack Pattern helm assist")
            outcome = evaluate_task(dice, difficulty, opposition)
            dice_text = format_dice(dice)
            if outcome.assist_ignored:
                notes.append("assist dice ignored - the crew scored no successes")
        if adef["sensor"] and ship.calibrated_sensors:
            ship.calibrated_sensors = False
        if ship.rerouted_power and ship.rerouted_power == adef["system"]:
            notes.append(f"Rerouted Reserve Power ({ship.rerouted_power}) used")
            ship.rerouted_power = ""

        verdict = "SUCCESS" if outcome.success else "FAILURE"
        vs = f"Difficulty {difficulty}"
        if opposition is not None:
            vs += f" (opposed: defender scored {opposition})"
        gain = "Momentum" if ship.side == "Player" else "Threat"
        summary = (f"{verdict}: {outcome.successes} success(es) vs {vs}"
                   + (f"  ->  +{outcome.excess} {gain}" if outcome.excess else ""))
        detail = f"[{dice_text}]" + (f"  ({'; '.join(notes)})" if notes else "")
        if outcome.complications:
            summary += f"\n{outcome.complications} COMPLICATION(S) rolled!"
        if defender_comps:
            summary += f"\nDefender rolled {defender_comps} COMPLICATION(S)!"
        self.result_lbl.configure(text=f"{summary}\n{detail}",
                                  style="Good.TLabel" if outcome.success else "Alert.TLabel")
        self.log(f"{ship.name}: {name} - {summary.splitlines()[0]} {detail}",
                 "success" if outcome.success else "fail")
        if outcome.excess:
            self.gain_for_side(ship, outcome.excess, f"{name} excess successes")
        if outcome.complications:
            self.log(f"{ship.name}: {outcome.complications} complication(s) on {name}! "
                     "(GM: add a complication or let the players buy it off.)", "alert")
        return outcome

    def _consume_turn(self, ship, system):
        ship.turns_used += 1
        if system and system not in ship.systems_used:
            ship.systems_used.append(system)
        ship.restored_systems = []          # Restore lasts for the turn
        if ship.brace_for_impact:
            ship.brace_for_impact = False
            self.log(f"{ship.name}: Brace for Impact cleared (turn taken).")
        msg = f"{ship.name} turn {ship.turns_used}/{ship.scale} used ({system or 'no system'})."
        self.log(msg, "alert" if ship.turns_used > ship.scale else "info")

    def _apply_effect(self, ship, name, adef, target, weapon, outcome):
        ok = outcome.success if outcome is not None else True
        if name in ("Fire", "Ram"):
            self._resolve_attack(ship, name, target, weapon, ok)
            return
        if not ok:
            self.log(f"{ship.name}: {name} failed - no effect.", "fail")
            return
        if name == "Direct":
            self.log(f"{ship.name} directs an ally: they take an immediate Major Action without "
                     "the +1 Difficulty penalty (assisted with Control + Command).", "success")
        elif name == "Assist":
            if self.station_var.get() == STANDARD_STATION:
                self.log(f"{ship.name}: a crew member assists an ally's next task.", "success")
            else:
                self.log(f"{ship.name}'s commander assists up to two allies' next tasks.",
                         "success")
        elif name == "Restore":
            self._restore(ship)
        elif name in ("Create Trait", "Create / Alter Trait"):
            self._create_trait_effect(ship)
        elif name == "Ready":
            text = self.ask_string("Ready", f"{ship.name}: describe the trigger and the readied "
                                            "Major Action:", "")
            ship.readied_action = (text or "").strip() or "Major Action held for a trigger"
            self.log(f"{ship.name} readies: {ship.readied_action} (until End Round).", "success")
        elif name == "Pass":
            self.log(f"{ship.name} passes - no Major Action this turn.", "success")
        elif name in ("Change Position", "Interact", "Send / Respond to Hail", "Internal Comms",
                      "Other Tasks"):
            self.log(f"{ship.name}: {name} - {adef['reminder']}", "success")
        elif name == "Rally":
            self.log(f"{ship.name} rallies the crew.", "success")
        elif name == "Cloak":
            ship.engage_cloak()
            self.log(f"{ship.name} engages its cloaking device: Cloaked trait, Shields 0 and "
                     "cannot be raised, no attacks until it decloaks.", "success")
        elif name == "Decloak":
            if ship.cloaked:
                self._decloak(ship)
            else:
                self.log(f"{ship.name} is not cloaked.")
        elif name == "Reveal" and target is not None and target is not ship and target.cloaked:
            target.revealed = True
            self.log(f"{ship.name} reveals the cloaked {target.name}: it can be targeted until "
                     "End Round (it is still Cloaked).", "success")
        elif name in ("Impulse", "Thrusters", "Launch Probe", "Maneuver", "Sensor Sweep",
                      "Reveal", "Transport"):
            self.log(f"{ship.name}: {name} - {adef['reminder']}", "success")
        elif name == "Attack Pattern":
            ship.attack_pattern = True
            self.log(f"{ship.name}: Attack Pattern - helm assists all attacks this round.",
                     "success")
        elif name == "Evasive Action":
            ship.evasive = True
            self.log(f"{ship.name}: Evasive Action - attacks against it are Opposed; its own "
                     "attacks +1 Difficulty until End Round.", "success")
        elif name == "Warp":
            ship.warp_prepared = False
            self.log(f"{ship.name} goes to warp: move up to {ship.systems['Engines']} zones "
                     "(Engines).", "success")
        elif name == "Prepare":
            self._prepare(ship)
        elif name == "Calibrate Weapons":
            ship.calibrated_weapons = True
            self.log(f"{ship.name}: weapons calibrated (+1 Damage on next attack).", "success")
        elif name == "Targeting Solution":
            ship.targeting_solution = True
            tname = f" on {target.name}" if target and target is not ship else ""
            self.log(f"{ship.name}: targeting solution locked{tname}.", "success")
        elif name == "Defensive Fire":
            ship.defensive_fire = True
            self.log(f"{ship.name}: Defensive Fire - incoming attacks become Opposed (Daring + "
                     "Security) until End Round.", "success")
        elif name == "Modulate Shields":
            ship.resistance_bonus = 2
            self.log(f"{ship.name}: shields modulated - Resistance {ship.effective_resistance} "
                     "until End Round.", "success")
        elif name == "Tractor Beam":
            target.tractored_by = ship.name
            target.tractor_strength = ship.tractor_strength_rating
            self.log(f"{ship.name} locks a tractor beam on {target.name} (Strength "
                     f"{target.tractor_strength}). Target is immobilised.", "success")
        elif name == "Calibrate Sensors":
            ship.calibrated_sensors = True
            self.log(f"{ship.name}: sensors calibrated for the next sensor task.", "success")
        elif name == "Scan for Weakness":
            target.weakness_scanned = self.scan_mode_var.get()
            benefit = "+2 Damage" if target.weakness_scanned == "damage" else "Piercing"
            self.log(f"{ship.name} finds a weakness in {target.name}: next attack against it "
                     f"gains {benefit}.", "success")
        elif name == "Damage Control":
            self._damage_control(ship)
        elif name == "Regenerate Shields":
            amount = max(0, int_var_value(self.crew_dept_var, 0))
            if self.regen_boost_var.get() and self.pay_for_side(ship, 1, "Regenerate +2"):
                amount += 2
            if ship.shields_up:
                before = ship.shields
                ship.shields = min(ship.max_shields, ship.shields + amount)
                self.log(f"{ship.name} regenerates shields: {before} -> {ship.shields}/"
                         f"{ship.max_shields} (+{amount}).", "success")
            else:
                before = ship.stored_shields if ship.stored_shields >= 0 else ship.max_shields
                ship.stored_shields = min(ship.max_shields, before + amount)
                self.log(f"{ship.name} regenerates its lowered shields: {before} -> "
                         f"{ship.stored_shields} (applied when raised).", "success")
        elif name == "Regain Power":
            ship.reserve_power = True
            ship.regain_power_penalty = 0
            self.log(f"{ship.name} regains Reserve Power.", "success")
        elif name == "Reroute Power":
            sysname = self.ask_choice("Reroute Power", f"Reroute {ship.name}'s Reserve Power to "
                                                       "which system?", SYSTEMS, "Weapons")
            if sysname:
                ship.rerouted_power = sysname
                self.log(f"{ship.name} reroutes Reserve Power to {sysname}.", "success")
            if ship.has_talent("Backup EPS Conduits"):
                self.log(f"Reminder: {ship.name} has Backup EPS Conduits - apply the talent's "
                         "benefit to this power reroute (GM ruling).", "alert")
            if (ship.has_talent("Secondary Reactors") and not ship.secondary_reactors_used
                    and not ship.reserve_power):
                payer = "Threat" if ship.side == "NPC" else "Momentum"
                if self.ask_yes_no("Secondary Reactors",
                                   f"Secondary Reactors: spend 2 {payer} (Immediate) to restore "
                                   f"{ship.name}'s Reserve Power now? (once per scene)"):
                    self.use_secondary_reactors(ship)

    def use_secondary_reactors(self, ship=None):
        ship = ship or self.attacker
        if ship is None or not ship.has_talent("Secondary Reactors"):
            return
        if ship.secondary_reactors_used:
            self.show_info("Secondary Reactors", f"{ship.name} already used its Secondary "
                                                 "Reactors this scene (Combat > New Scene "
                                                 "resets it).")
            return
        if ship.reserve_power:
            self.show_info("Secondary Reactors", f"{ship.name} already has Reserve Power.")
            return
        if not self.pay_for_side(ship, 2, "Secondary Reactors"):
            return
        ship.reserve_power = True
        ship.secondary_reactors_used = True
        self.log(f"{ship.name}: Secondary Reactors restore Reserve Power (used for this scene).",
                 "success")
        self.changed()

    def new_scene(self):
        for ship in self.ships:
            ship.secondary_reactors_used = False
        self.log("--- NEW SCENE --- once-per-scene talents (Secondary Reactors) are available "
                 "again.", "separator")
        if self.scene_traits and self.ask_yes_no(
                "New Scene", f"Clear the {len(self.scene_traits)} scene trait(s) as well?"):
            self.scene_traits = []
            self.log("Scene traits cleared.")
        self.changed()

    def new_adventure(self):
        if not self.ask_yes_no("New Adventure", "Refill every ship's Crew Support and recover "
                                                "all deployed small craft?"):
            return
        for ship in self.ships:
            ship.crew_support_used = 0
            ship.small_craft_deployed = 0
            ship.secondary_reactors_used = False
        self.log("--- NEW ADVENTURE --- Crew Support refilled, small craft recovered.",
                 "separator")
        self.changed()

    def _start_override(self, ship):
        stations = [st for st in BRIDGE_STATIONS if st != STANDARD_STATION]
        choice = self.ask_choice("Override", f"{ship.name}: which station do you control from "
                                             "your current console?", stations, stations[0])
        if not choice:
            return
        self.override_var.set(True)
        self.station_var.set(choice)
        self.on_station_change()
        majors = [n for n, a in BRIDGE_STATIONS[choice].items() if a["kind"] == "Major"]
        if majors:
            self.action_var.set(majors[0])
            self.on_action_change()
        self.log(f"{ship.name}: Override - pick the {choice} action to perform; it is +1 "
                 "Difficulty (Override box ticked).")

    def _mark_restored(self, ship, sysname, why=""):
        if sysname not in ship.restored_systems:
            ship.restored_systems.append(sysname)
        self.log(f"{ship.name}: Restore (Minor Action){why} - the Malfunctioning {sysname} can be "
                 "used this turn.", "success")

    def _restore(self, ship):
        candidates = [s_ for s_ in SYSTEMS if ship.needs_restore(s_)]
        if not candidates:
            self.log(f"{ship.name}: Restore - no Malfunctioning subsystem needs it this turn.")
            return
        sysname = candidates[0] if len(candidates) == 1 else self.ask_choice(
            "Restore", "Restore which Malfunctioning subsystem?", candidates, candidates[0])
        if sysname:
            self._mark_restored(ship, sysname)

    def _create_trait_effect(self, ship):
        options = ["Create a new trait"]
        if self.scene_traits:
            options += ["Alter an existing trait", "Remove a trait"]
        choice = self.ask_choice("Create / Alter Trait", f"{ship.name} succeeds. What happens to "
                                                         "the scene's traits?", options,
                                 options[0])
        if not choice:
            self.log(f"{ship.name}: trait change cancelled.")
            return
        if choice.startswith("Create"):
            text = (self.ask_string("New trait", "Name the new trait:", "") or "").strip()
            if text:
                self.scene_traits.append(f"{text} [{ship.name}]")
                self.log(f"{ship.name} creates the trait '{text}'.", "success")
            return
        old = self.ask_choice("Scene traits", "Which trait?", self.scene_traits,
                              self.scene_traits[0])
        if not old:
            return
        if choice.startswith("Alter"):
            text = (self.ask_string("Alter trait", "New wording:", old) or "").strip()
            if text:
                self.scene_traits[self.scene_traits.index(old)] = text
                self.log(f"{ship.name} alters the trait '{old}' -> '{text}'.", "success")
        else:
            self.scene_traits.remove(old)
            self.log(f"{ship.name} removes the trait '{old}'.", "success")

    def add_scene_trait(self):
        text = (self.ask_string("Scene trait", "New scene trait:", "") or "").strip()
        if text:
            self.scene_traits.append(text)
            self.log(f"GM adds scene trait '{text}'.")
            self.changed()

    def remove_scene_trait(self):
        sel = self.trait_lb.curselection()
        if not sel or sel[0] >= len(self.scene_traits):
            return
        removed = self.scene_traits.pop(sel[0])
        self.log(f"Scene trait removed: '{removed}'.")
        self.changed()

    def _prepare(self, ship):
        opts = [f"Shields: {'Lower' if ship.shields_up else 'Raise'}",
                f"Weapons: {'Disarm' if ship.weapons_armed else 'Arm'}",
                "Prepare for Warp"]
        choice = self.ask_choice("Prepare", f"What does {ship.name} prepare?", opts, opts[1])
        if choice is None:
            self.log(f"{ship.name}: Prepare cancelled.")
            return
        needed = ("Weapons" if choice == "Weapons: Arm"
                  else "Engines" if choice == "Prepare for Warp" else "")
        if needed and ship.breach_condition(needed) == "Offline":
            if not self.ask_yes_no("Subsystem offline",
                                   f"{ship.name}'s {needed} {self._be(needed)} OFFLINE - "
                                   f"{choice} cannot be done.\n\nGM override and do it anyway?"):
                self.log(f"{ship.name}: {choice} blocked - {needed} offline.")
                return
            self.log(f"GM override: {ship.name} uses its OFFLINE {needed} ({choice}).", "alert")
        if choice.startswith("Shields"):
            if ship.shields_up:
                self._lower_shields(ship)
            else:
                self._raise_shields(ship)
        elif choice.startswith("Weapons"):
            ship.weapons_armed = not ship.weapons_armed
            self.log(f"{ship.name} {'arms' if ship.weapons_armed else 'disarms'} weapons.",
                     "success")
        else:
            ship.warp_prepared = True
            self.log(f"{ship.name} prepares for warp.", "success")

    def _damage_control(self, ship):
        damaged = [s for s in SYSTEMS if ship.breaches.get(s, 0) > 0]
        if damaged:
            sysname = damaged[0] if len(damaged) == 1 else self.ask_choice(
                "Damage Control", f"Patch a breach on which {ship.name} system?",
                damaged, damaged[0])
            if sysname:
                self._patch_breach(ship, sysname, "Damage Control")
            remaining = [s for s in SYSTEMS if ship.breaches.get(s, 0) > 0]
            payer = "Threat" if ship.side == "NPC" else "Momentum"
            if (sysname and remaining and ship.has_talent("Rugged Design")
                    and self.ask_yes_no("Rugged Design",
                                        f"Rugged Design: spend 2 {payer} to patch a second "
                                        f"breach on {ship.name}?")):
                second = remaining[0] if len(remaining) == 1 else self.ask_choice(
                    "Rugged Design", "Patch a second breach on which system?", remaining,
                    remaining[0])
                if not second:
                    self.log("Rugged Design second patch cancelled - nothing spent.")
                elif self.pay_for_side(ship, 2, "Rugged Design second patch"):
                    self._patch_breach(ship, second, "Rugged Design")
        else:
            self.log(f"{ship.name}: Damage Control - no breaches to patch.")
        if ship.has_talent("Improved Damage Control"):
            self.log(f"Reminder: {ship.name} has Improved Damage Control - apply the talent's "
                     "benefit to this repair (GM ruling).", "alert")

    def _patch_breach(self, ship, sysname, source):
        ship.breaches[sysname] = max(0, ship.breaches.get(sysname, 0) - 1)
        cleared = ""
        if ship.breaches[sysname] == 0:
            if sysname in ship.devastating_systems:
                ship.devastating_systems.remove(sysname)
            if ship.breach_conditions.get(sysname):
                cleared = f" - {ship.breach_conditions[sysname]} condition cleared"
            ship.breach_conditions[sysname] = ""
        self.log(f"{ship.name}: {source} patches 1 breach on {sysname} "
                 f"({ship.breaches[sysname]} left){cleared}.", "success")

    def _resolve_attack(self, ship, name, target, weapon, hit):
        calib = 1 if name == "Fire" and ship.calibrated_weapons else 0
        scan = target.weakness_scanned
        choose = self._uses_tsol_choice(ship, name)
        rapid = 1 if self._is_rapid_fire_salvo(ship, name, weapon) else 0
        if name == "Fire":
            ship.calibrated_weapons = False
            ship.targeting_solution = False
        target.weakness_scanned = ""
        label = weapon.name if name == "Fire" else "Collision (Ram)"
        if not hit:
            self.log(f"MISS - {ship.name}'s {label} fails to hit {target.name}.", "fail")
            self.result_lbl.configure(text=self.result_lbl.cget("text") + "\nAttack MISSES.")
            return
        if name == "Fire":
            base = weapon.damage
            piercing = weapon.has("Piercing") or scan == "piercing"
            if weapon.has("Versatile"):
                x = weapon.qval("Versatile", 1)
                self.gain_for_side(ship, x, f"Versatile {x}")
        else:
            base = ship.scale
            piercing = scan == "piercing"
        self.pending_attack = {
            "attacker": ship.name, "target": target.name, "label": label,
            "weapon": copy.deepcopy(weapon) if name == "Fire" else None,
            "calibrate": calib, "scan_damage": 2 if scan == "damage" else 0,
            "rapid_fire": rapid, "choose_system": choose, "ram": name == "Ram",
        }
        pw = self.pending_attack["weapon"]
        if pw is not None and pw.has(AREA_OR_SPREAD):
            chosen = self._choose_area_or_spread(ship, pw)
            if chosen is not None:
                self.pending_attack["weapon"] = chosen
        self.dmg_weapon_var.set(label)
        self.dmg_base_var.set(base)
        self.dmg_bonus_var.set(0)
        self.pierce_var.set(piercing)
        self.devastate_var.set(False)
        self.log(f"HIT - {ship.name}'s {label} strikes {target.name}! Base damage {base}"
                 + (f" +{calib} calibrated" if calib else "")
                 + (" +2 weakness" if scan == "damage" else "")
                 + (" +1 Rapid-Fire salvo" if rapid else "")
                 + (" (Piercing)" if piercing else "")
                 + ". Resolve it with APPLY DAMAGE.", "success")
        self.result_lbl.configure(text=self.result_lbl.cget("text")
                                  + "\nAttack HITS - resolve damage in the Tactical panel.")

    def _choose_area_or_spread(self, ship, weapon):
        """Arrays: ask which quality this attack uses. Returns the resolved weapon copy,
        or None if the GM cancelled."""
        choice = self.ask_choice(
            "Area or Spread",
            f"{weapon.name} has Area or Spread - choose one for this attack:\n\n"
            f"Area: {WEAPON_QUALITIES['Area'][1]}\nSpread: {WEAPON_QUALITIES['Spread'][1]}",
            ["Area", "Spread"], "Spread")
        if choice not in ("Area", "Spread"):
            self.log(f"{weapon.name}: Area or Spread not chosen yet - asked again when damage "
                     "is applied.")
            return None
        who = f"{ship.name}'s " if ship is not None else ""
        self.log(f"{who}{weapon.name} uses {choice} for this attack.")
        return resolve_area_or_spread(weapon, choice)

    # ========================================================= damage logic
    def on_damage_weapon_change(self):
        if self.pending_attack:
            if self.dmg_weapon_var.get() == self.pending_attack["label"]:
                return
            self.pending_attack = None
            self.log("Pending attack cleared (damage weapon changed manually).")
        ship = self.attacker
        weapon = ship.weapon(self.dmg_weapon_var.get()) if ship else None
        if weapon:
            self.dmg_base_var.set(weapon.damage)
            self.pierce_var.set(weapon.has("Piercing"))
        self.refresh_all()

    def clear_pending_attack(self):
        if self.pending_attack:
            self.log("Pending attack discarded.")
        self.pending_attack = None
        self.dmg_bonus_var.set(0)
        self.devastate_var.set(False)
        self.refresh_all()

    def apply_damage(self):
        pa = self.pending_attack
        target = self.target
        if pa:
            ptarget = self.ship_by_name(pa["target"])
            if ptarget is None:
                pa = self.pending_attack = None
            elif ptarget is not target:
                ans = self.ask_yes_no_cancel(
                    "Pending attack",
                    f"The pending hit was against {ptarget.name}, but "
                    f"{target.name if target else 'no ship'} is selected as Target.\n\n"
                    f"Yes = apply it to {ptarget.name}\nNo = discard the pending hit and apply "
                    "manual damage to the selected target\nCancel = abort")
                if ans is None:
                    return
                if ans:
                    target = ptarget
                else:
                    pa = self.pending_attack = None
        if target is None:
            self.show_error("No target", "Select a target ship first.")
            return
        attacker = self.ship_by_name(pa["attacker"]) if pa else self.attacker
        weapon = pa["weapon"] if pa else self._damage_weapon()
        if not pa and attacker is target:
            attacker = None   # e.g. GM applying hazard damage to the acting ship
        if weapon is not None and weapon.has(AREA_OR_SPREAD):
            weapon = self._choose_area_or_spread(attacker, weapon)
            if weapon is None:
                return
            if pa:
                pa["weapon"] = weapon
        bonus = int_var_value(self.dmg_bonus_var, 0)
        dev = self.devastate_var.get()
        raw = int_var_value(self.dmg_base_var, 0) + pending_damage_bonus(pa) + bonus
        if dev and resolve_shield_damage(target.shields, target.max_shields, raw,
                                         target.effective_resistance,
                                         self.pierce_var.get()).final_damage <= 0:
            dev = False
            self.log("Devastating Attack not applied - the hit is fully absorbed, so no cost "
                     "is charged.", "alert")
        cost = bonus * bonus_damage_cost_each(weapon) + (devastating_attack_cost(weapon) if dev
                                                         else 0)
        if cost:
            if attacker is None:
                self.log(f"Bonus damage / Devastating Attack ({cost} Momentum) - no attacker "
                         "selected, cost not deducted.", "alert")
            elif not self.pay_for_side(attacker, cost, "bonus damage / Devastating Attack"):
                return
        label = pa["label"] if pa else (weapon.name if weapon else "Damage")
        source = f"{attacker.name}'s {label}" if attacker else label
        self._inflict_damage(target, raw, self.pierce_var.get(), source, weapon=weapon,
                             choose_system=bool(pa and pa["choose_system"]),
                             devastating_attack=dev, attacker=attacker)
        if pa and pa["ram"] and attacker is not None and attacker is not target:
            recoil = target.scale
            if self.ask_yes_no("Collision recoil",
                               f"Ramming also damages {attacker.name}.\n\nApply suggested "
                               f"collision damage {recoil} (= {target.name}'s Scale) to "
                               f"{attacker.name}?"):
                self._inflict_damage(attacker, recoil, False,
                                     f"Collision recoil from ramming {target.name}")
        self.pending_attack = None
        self.dmg_bonus_var.set(0)
        self.devastate_var.set(False)
        self.changed()

    def _inflict_damage(self, target, raw, piercing, source, weapon=None, choose_system=False,
                        devastating_attack=False, attacker=None):
        out = resolve_shield_damage(target.shields, target.max_shields, raw,
                                    target.effective_resistance, piercing)
        res_txt = "Piercing" if piercing else f"Resistance {out.resistance_applied}"
        target.shields = out.shields_after
        self.log(f"{source} -> {target.name}: {raw} - {res_txt} = {out.final_damage} damage. "
                 f"Shields {out.shields_before} -> {out.shields_after}/{target.max_shields}.",
                 "alert" if out.final_damage else "info")
        if weapon is not None:
            self._apply_on_hit_qualities(weapon, target, attacker, piercing)
        if out.final_damage <= 0:
            self.log(f"{target.name}'s Resistance absorbs the hit - no Shaken or Breach.")
            return out
        for reason in out.shaken_reasons:
            target.shaken = True
            self.log(f"{target.name} is SHAKEN ({reason})!", "alert")
            self.refresh_all()
            self.open_shaken_resolver(target, reason)
        high_yield = weapon is not None and weapon.has("High Yield")
        devastating = weapon is not None and weapon.has("Devastating")
        for reason in out.breach_reasons:
            sysname = self._pick_breach_system(target, choose_system, reason)
            self._add_breach(target, sysname, 1 + (1 if high_yield else 0), reason, devastating)
        if devastating_attack:
            sysname = self._pick_breach_system(target, False, "Devastating Attack")
            self._add_breach(target, sysname, 1, "Devastating Attack", devastating)
        if target.total_breaches() >= target.scale:
            self.log(f"WARNING: {target.name} has {target.total_breaches()} breaches (Scale "
                     f"{target.scale}) - check disabled systems / destruction.", "alert")
        return out

    def _apply_on_hit_qualities(self, weapon, target, attacker=None, piercing=False):
        if weapon.has("Dampening") and target.reserve_power:
            target.reserve_power = False
            self.log(f"Dampening: {target.name}'s Reserve Power is drained.", "alert")
        if weapon.has("Jamming"):
            target.jammed = True
            self.log(f"Jamming: {target.name} suffers +1 Difficulty to Comms/Sensors tasks "
                     "until End Round.", "alert")
        if weapon.has("Slowing"):
            target.slowed = True
            self.log(f"Slowing: {target.name} cannot Keep the Initiative until End Round.",
                     "alert")
        if weapon.has("Persistent"):
            self._apply_persistent(weapon, target, attacker, piercing)
        if weapon.has("Area"):
            self.log("Area: other vessels near the target may also be affected - GM adjudicates.")
        if weapon.has("Hidden"):
            self.log(f"Hidden {weapon.qval('Hidden', 1)}: locating the attacker is +"
                     f"{weapon.qval('Hidden', 1)} Difficulty.")
        if weapon.has("Calibration"):
            self.log("Calibration: remember any calibration benefits for this weapon.")

    def _apply_persistent(self, weapon, target, attacker, piercing):
        """2e Persistent: spend 1-3 Momentum for half-damage at each End Round."""
        per_round = -(-weapon.damage // 2)     # half the damage rating, rounded up
        payer = "Threat" if attacker is not None and attacker.side == "NPC" else "Momentum"
        lasting = target.effective_resistance - target.resistance_bonus
        if not piercing and per_round <= lasting:
            self.log(f"Persistent: {per_round} lingering damage would be absorbed by "
                     f"{target.name}'s Resistance {lasting} - not worth spending {payer}.")
            return
        if not piercing and per_round <= target.effective_resistance:
            self.log(f"Persistent: the tick at this End Round is absorbed by Modulated Shields; "
                     f"later ticks face Resistance {lasting}.", "alert")
        options = ["0 - no lingering damage"] + [
            f"{n} - {per_round} damage at End Round for {n} round(s)" for n in (1, 2, 3)]
        choice = self.ask_choice(
            "Persistent", f"{weapon.name} is Persistent. Spend 1-3 {payer} so {target.name} "
                          f"takes {per_round} damage (Resistance applies) at the end of each "
                          "round for that many rounds?", options, options[0])
        rounds = to_int((choice or "0").split(" ")[0], 0)
        if rounds and (attacker is None
                       or self.pay_for_side(attacker, rounds, "Persistent damage")):
            target.persistent_effects.append(
                {"amount": per_round, "rounds": rounds, "source": weapon.name,
                 "piercing": bool(piercing)})
            self.log(f"Persistent: {target.name} will take {per_round} damage at the next "
                     f"{rounds} End Round(s).", "alert")

    def _pick_breach_system(self, target, choose, reason):
        if choose:
            sysname = self.ask_choice("Targeting Solution - choose system",
                                      f"Choose the system hit on {target.name} ({reason}):",
                                      SYSTEMS, "Weapons")
            if sysname:
                self.log(f"Targeting Solution: system hit chosen -> {sysname}.")
                self.last_system_hit = sysname
                return sysname
        roll, sysname = roll_system_hit(self.rng, self.hit_table)
        self.last_system_hit = sysname
        self.log(f"System Hit roll (d{self.hit_table[-1][1]}): {roll} -> {sysname}.")
        return sysname

    def _add_breach(self, target, sysname, count, reason, devastating=False):
        target.breaches[sysname] = target.breaches.get(sysname, 0) + count
        if devastating and sysname not in target.devastating_systems:
            target.devastating_systems.append(sysname)
        self.log(f"BREACH x{count} on {target.name} {sysname} ({reason})"
                 + (" [High Yield]" if count > 1 else "")
                 + (" [Devastating]" if devastating else "")
                 + f". {sysname} breaches: {target.breaches[sysname]}.", "alert")
        for i in range(count):
            self.resolve_breach_nature(target, sysname, reason + (
                f" - breach {i + 1} of {count}" if count > 1 else ""))

    def resolve_breach_nature(self, ship, sysname, reason):
        """Ask the GM for the Nature of Breach and attach it to the system."""
        self.refresh_all()
        result = self.ask_breach_nature(ship, sysname, reason)
        if not result:
            self.log(f"Nature of Breach on {ship.name} {sysname} not set (GM skipped)."
                     + (f" It stays {ship.breach_condition(sysname)}."
                        if ship.breach_condition(sysname) else ""))
            return
        nature, roll = result
        how = f"rolled {roll}" if roll else "chosen"
        final = ship.set_breach_condition(sysname, nature)
        if final != nature:
            self.log(f"Nature of Breach ({how}): {nature} - {ship.name} {sysname} stays {final} "
                     "(more severe).", "alert")
        else:
            self.log(f"Nature of Breach on {ship.name} {sysname} ({how}): {nature} - "
                     f"{breach_nature_description(nature)}", "alert")
        if nature == "Damaged":
            self.log(f"GM: {ship.name} {sysname} is Damaged - consider spending Threat to cause "
                     "a complication.", "pool")
        self.changed()

    def set_breach_condition_manual(self, sysname, nature):
        t = self.target
        if t is None:
            return
        if not t.breaches.get(sysname, 0):
            if nature:
                self.log(f"{t.name} {sysname} has no breach - add one before setting its "
                         "condition.", "alert")
            self.refresh_all()
            return
        if nature == t.breach_condition(sysname):
            return
        t.set_breach_condition(sysname, nature, force=True)
        self.log(f"GM sets {t.name} {sysname} condition: {nature or 'none'}.", "alert")
        self.changed()

    def _failing_systems(self, ship, name, adef):
        if ship is None or adef is None or name in ("Restore", "Prepare"):
            return []
        return [s_ for s_ in action_systems(adef) if ship.breach_condition(s_) == "Failing"]

    def failing_to_offline_acting(self):
        """Middle-panel button: the acting ship's Failing subsystem goes Offline for 1 Threat."""
        ship = self.attacker
        failing = self._failing_systems(ship, self.action_var.get(), self.current_action())
        if not failing:
            return
        sysname = failing[0] if len(failing) == 1 else self.ask_choice(
            "Set Offline", "Which Failing subsystem goes Offline?", failing, failing[0])
        if sysname:
            self.failing_to_offline(sysname, ship)

    def failing_to_offline(self, sysname, ship=None):
        """GM button: spend 1 Threat to push a Failing subsystem Offline."""
        t = ship or self.target
        if t is None or t.breach_condition(sysname) != "Failing":
            return
        if self.threat < 1:
            if not self.ask_yes_no("No Threat", "The Threat pool is empty. Set the system "
                                                "Offline anyway (GM override)?"):
                return
            self.log("GM override: Failing -> Offline without Threat.", "alert")
        else:
            self.threat -= 1
            self.log(f"GM spends 1 Threat -> {self.threat}.", "pool")
        t.set_breach_condition(sysname, "Offline", force=True)
        self.log(f"{t.name} {sysname} goes OFFLINE - tasks using it cannot be attempted.",
                 "alert")
        self.changed()

    def open_shaken_resolver(self, ship, reason):
        result = self.ask_shaken_result(ship, reason)
        if not result:
            self.log(f"Shaken result for {ship.name} skipped by GM.")
            return
        name, rolls = result
        rolled = (" (rolled " + " -> ".join(str(r) for r in rolls) + ")") if rolls else \
            " (chosen manually)"
        self.apply_minor_damage(ship, name, rolled)

    def apply_minor_damage(self, ship, name, how=""):
        if name == "Brace for Impact!":
            ship.brace_for_impact = True
        elif name == "Losing Power!":
            ship.reserve_power = False
            ship.regain_power_penalty = 1
            if ship.has_talent("Backup EPS Conduits"):
                self.log(f"Reminder: {ship.name} has Backup EPS Conduits - check whether the "
                         "talent mitigates this power loss (GM ruling).", "alert")
        elif name == "Casualties and Minor Damage":
            text = self.ask_string("Complication", f"Complication trait for {ship.name}:",
                                   "Casualties and Minor Damage")
            ship.complications.append(text.strip() if text and text.strip()
                                      else "Casualties and Minor Damage")
        self.log(f"Minor Damage on {ship.name}{how}: {name} - "
                 f"{minor_damage_description(name)}", "alert")
        self.changed()

    def shaken_resolver_clicked(self):
        t = self.target
        if t is None:
            self.show_error("No target", "Select a target ship first.")
            return
        t.shaken = True
        self.open_shaken_resolver(t, "opened manually by the GM")

    @property
    def hit_table(self):
        return SYSTEM_HIT_TABLES.get(self.hit_table_var.get(), SYSTEM_HIT_TABLE)

    def on_hit_table_change(self):
        self.log(f"System hit table set to {self.hit_table_var.get()}.")
        self.changed()

    def roll_system_hit_clicked(self):
        roll, sysname = roll_system_hit(self.rng, self.hit_table)
        self.last_system_hit = sysname
        self.log(f"System Hit Generator (d{self.hit_table[-1][1]}): {roll} -> {sysname}.")
        self.refresh_all()

    def breach_last_hit(self):
        t = self.target
        if t is None or not self.last_system_hit:
            self.show_error("System hit", "Select a target and roll a system hit first.")
            return
        self._add_breach(t, self.last_system_hit, 1, "System Hit Generator")
        self.changed()

    def adjust_breach(self, sysname, delta):
        t = self.target
        if t is None:
            return
        new = max(0, t.breaches.get(sysname, 0) + delta)
        if new == t.breaches.get(sysname, 0):
            return
        t.breaches[sysname] = new
        if new == 0:
            if sysname in t.devastating_systems:
                t.devastating_systems.remove(sysname)
            t.breach_conditions[sysname] = ""
        self.log(f"GM {'adds' if delta > 0 else 'removes'} a breach: {t.name} {sysname} -> {new}.",
                 "alert" if delta > 0 else "info")
        if delta > 0:
            self.resolve_breach_nature(t, sysname, "added manually by the GM")
        self.changed()

    def toggle_target_shields(self):
        t = self.target
        if t is None:
            return
        if self.tgt_shields_up_var.get():
            self._raise_shields(t)
        else:
            self._lower_shields(t)
        self.changed()

    def _raise_shields(self, ship) -> bool:
        if not ship.raise_shields():
            self.log(f"{ship.name} cannot raise shields while cloaked.", "alert")
            return False
        self.log(f"{ship.name} raises shields: {ship.shields}/{ship.max_shields}.", "success")
        return True

    def _lower_shields(self, ship) -> None:
        if ship.shields_up:
            ship.lower_shields()
            self.log(f"{ship.name} lowers shields (Shields count as 0; {ship.stored_shields} "
                     "restored when raised).", "alert")

    def toggle_target_cloak(self):
        if self.target is not None:
            self.toggle_cloak(self.target)

    def toggle_cloak(self, ship=None):
        ship = ship or self.attacker
        if ship is None:
            return
        if not ship.has_talent("Cloaking Device"):
            self.show_error("Cloaking Device", f"{ship.name} does not have the Cloaking Device "
                                               "talent.")
            return
        if ship.cloaked:
            self._decloak(ship)
        else:
            ship.engage_cloak()
            self.log(f"{ship.name} engages its cloaking device: Cloaked trait, Shields 0 and "
                     "cannot be raised, no attacks until it decloaks. Enemies must Reveal it.",
                     "alert")
        self.changed()

    def _decloak(self, ship, reason=""):
        ship.disengage_cloak()
        self.log(f"{ship.name} decloaks (Minor Action){reason}. Shields remain DOWN - use "
                 "Tactical > Prepare to raise them.", "alert")

    def toggle_target_flag(self, attr, var):
        t = self.target
        if t is None:
            return
        setattr(t, attr, bool(var.get()))
        self.log(f"{t.name}: {attr.replace('_', ' ')} -> {'Yes' if var.get() else 'No'}.")
        self.changed()

    def _set_target_shield_value(self, t, value, verb):
        """Manual GM shield edits; while shields are lowered (or cloaked) the stored value
        that returns when they are raised is edited instead."""
        value = clamp(value, 0, t.max_shields)
        if t.shields_up:
            t.shields = value
            self.log(f"GM {verb} {t.name} Shields -> {t.shields}/{t.max_shields}.")
        else:
            t.stored_shields = value
            self.log(f"GM {verb} {t.name}'s lowered Shields -> {value}/{t.max_shields} "
                     "(applied when raised).")
        self.changed()

    def _target_shield_value(self, t):
        if t.shields_up:
            return t.shields
        return t.stored_shields if t.stored_shields >= 0 else t.max_shields

    def adjust_target_shields(self, delta):
        t = self.target
        if t is not None:
            self._set_target_shield_value(t, self._target_shield_value(t) + delta,
                                          f"adjusts ({delta:+d})")

    def set_target_shields(self):
        t = self.target
        if t is not None:
            self._set_target_shield_value(
                t, int_var_value(self.tgt_set_shields_var, self._target_shield_value(t)), "sets")

    def restore_target_shields(self):
        t = self.target
        if t is not None:
            self._set_target_shield_value(t, t.max_shields, "restores")

    def add_complication(self):
        t = self.target
        if t is None:
            return
        text = self.ask_string("Complication", f"New complication for {t.name}:")
        if text and text.strip():
            t.complications.append(text.strip())
            self.log(f"{t.name} gains complication: {text.strip()}.", "alert")
            self.changed()

    def remove_complication(self):
        t = self.target
        sel = self.comp_lb.curselection()
        if t is None or not sel or sel[0] >= len(t.complications):
            return
        removed = t.complications.pop(sel[0])
        self.log(f"{t.name}: complication removed ({removed}).")
        self.changed()

    def clear_target_effects(self):
        t = self.target
        if t is None:
            return
        t.clear_temporary_effects()
        self.log(f"{t.name}: all temporary effects cleared by the GM.")
        self.changed()

    # ========================================================= roster editing
    def new_ship(self):
        ship = ShipEditor.ask(self.root, None, [s.name for s in self.ships], "Custom Ship Creator")
        if ship:
            self.ships.append(ship)
            self.log(f"Custom ship added: {ship.name} (Scale {ship.scale}, {ship.crew_quality} "
                     "crew).")
            self.changed()

    def edit_ship(self):
        ship = self.selected_roster_ship() or self.attacker
        if ship is None:
            return
        old = ship.name
        edited = ShipEditor.ask(self.root, ship, [s.name for s in self.ships],
                                f"Edit Ship - {ship.name}")
        if not edited:
            return
        self.ships[self.ships.index(ship)] = edited
        if old != edited.name:
            for var in (self.attacker_var, self.target_var):
                if var.get() == old:
                    var.set(edited.name)
            if self.pending_attack:
                for key in ("attacker", "target"):
                    if self.pending_attack[key] == old:
                        self.pending_attack[key] = edited.name
            if self._last_attacker == old:
                self._last_attacker = edited.name
        self.log(f"Ship updated: {edited.name}.")
        self.changed()

    def duplicate_ship(self):
        ship = self.selected_roster_ship() or self.attacker
        if ship is None:
            return
        dup = copy.deepcopy(ship)
        dup.name = self.unique_name(ship.name)
        self.ships.append(dup)
        self.log(f"Duplicated {ship.name} as {dup.name}.")
        self.changed()

    def delete_ship(self):
        ship = self.selected_roster_ship()
        if ship is None:
            self.show_info("Delete", "Select a ship in the roster list first.")
            return
        if not self.ask_yes_no("Delete ship", f"Remove {ship.name} from the roster?"):
            return
        self.ships.remove(ship)
        if self.pending_attack and ship.name in (self.pending_attack["attacker"],
                                                 self.pending_attack["target"]):
            self.pending_attack = None
        self.log(f"{ship.name} removed from the roster.")
        self.changed()

    def full_repair_selected(self):
        ship = self.selected_roster_ship() or self.target
        if ship is None:
            return
        if self.ask_yes_no("Full Repair", f"Fully repair {ship.name}? (Shields, breaches, "
                                          "complications and all effects reset.)"):
            ship.full_repair()
            self.log(f"{ship.name} fully repaired.")
            self.changed()

    def generate_npc(self):
        quality = self.gen_quality_var.get()
        profile = self.gen_profile_var.get()
        scale = clamp(int_var_value(self.gen_scale_var, 4), 1, 7)
        name = self.gen_name_var.get().strip() or f"NPC {profile.split(' ')[0]} S{scale}"
        ship = generate_npc_ship(self.unique_name(name), scale, quality, profile, self.rng,
                                 talents=self.gen_talents.selected())
        self.ships.append(ship)
        if self.attacker is not None and self.attacker.side == "Player":
            self.target_var.set(ship.name)
        self.gen_name_var.set("")
        self.log(f"Generated NPC: {ship.name} - Scale {scale}, {quality} crew, Shields "
                 f"{ship.max_shields}, Resistance {ship.effective_resistance}"
                 + (f", talents: {', '.join(ship.talents)}" if ship.talents else "") + ".")
        self.changed()

    # ============================================================ persistence
    def roster_to_dict(self):
        return {
            "app": APP_NAME, "format_version": SAVE_FORMAT_VERSION,
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "round": self.round, "threat": self.threat, "momentum": self.momentum,
            "gm_modifier": int_var_value(self.gm_mod_var, 0),
            "system_hit_table": self.hit_table_var.get(),
            "attacker": self.attacker_var.get(), "target": self.target_var.get(),
            "scene_traits": list(self.scene_traits),
            "ships": [s.to_dict() for s in self.ships],
        }

    def save_roster(self, path=None) -> bool:
        path = path or self.data_file
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.roster_to_dict(), fh, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            self.show_error("Save failed", f"Could not save roster to\n{path}\n\n{exc}\n\n"
                                           "Try File > Save Roster As... to pick another folder.")
            return False
        if os.path.abspath(path) == os.path.abspath(self.data_file):
            self.dirty = False
        self.log(f"Roster saved ({len(self.ships)} ships) to {path}.")
        self.refresh_all()
        return True

    def load_roster(self, path=None, quiet=False) -> bool:
        path = path or self.data_file
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            ships, meta, errors = parse_roster_data(data)
            # Validate everything before touching the current roster.
            round_ = max(1, to_int(meta.get("round", 1), 1))
            threat = max(0, to_int(meta.get("threat", 0), 0))
            momentum = clamp(to_int(meta.get("momentum", 0), 0), 0, MOMENTUM_MAX)
            gm_mod = clamp(to_int(meta.get("gm_modifier", 0), 0), -3, 5)
            table = meta.get("system_hit_table", DEFAULT_HIT_TABLE)
            if not isinstance(table, str) or table not in SYSTEM_HIT_TABLES:
                table = DEFAULT_HIT_TABLE
            attacker = meta.get("attacker", "")
            traits = meta.get("scene_traits", [])
            traits = [str(t) for t in traits if isinstance(t, (str, int, float))] \
                if isinstance(traits, list) else []
            target = meta.get("target", "")
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            if not quiet:
                self.show_error("Load failed", f"Could not load roster from\n{path}\n\n{exc}")
            else:
                self.log(f"Could not load {path}: {exc}", "alert")
            return False
        if not ships:
            if not quiet:
                self.show_error("Load failed", f"No valid ships found in\n{path}")
            return False
        self.ships = []
        for ship in ships:            # guarantee unique names
            ship.name = self.unique_name(ship.name)
            self.ships.append(ship)
        self.round, self.threat, self.momentum = round_, threat, momentum
        self.gm_mod_var.set(gm_mod)
        self.override_var.set(False)
        self.hit_table_var.set(table)
        self.attacker_var.set(attacker if isinstance(attacker, str) else "")
        self.target_var.set(target if isinstance(target, str) else "")
        self.scene_traits = traits
        self.pending_attack = None
        self._last_attacker = None
        self.dirty = os.path.abspath(path) != os.path.abspath(self.data_file)
        self.log(f"Roster loaded from {path}: {len(self.ships)} ships, round {self.round}.")
        for err in errors:
            self.log(f"Skipped invalid ship ({err}).", "alert")
        self.refresh_all()
        return True

    def _startup_load(self, autoload):
        self.log(f"{APP_NAME} v{APP_VERSION} ready. Data file: {self.data_file}")
        loaded = False
        if autoload and os.path.exists(self.data_file):
            loaded = self.load_roster(self.data_file, quiet=True)
            if not loaded:
                self.root.after(200, lambda: self.show_error(
                    "Roster file problem",
                    f"{self.data_file} could not be read, so the preset ships were loaded "
                    "instead.\nThe file was NOT overwritten - fix or remove it, or save to "
                    "replace it."))
        if not loaded:
            self._load_presets()
        self.on_station_change()

    def _load_presets(self):
        self.ships = preset_ships()
        self.round, self.threat, self.momentum = 1, 0, 0
        self.scene_traits = []
        self.override_var.set(False)
        self.attacker_var.set(self.ships[0].name)
        self.target_var.set(self.ships[1].name)
        self.pending_attack = None
        self._last_attacker = None
        self.dirty = False
        self.log("Preset ships loaded: USS Aurora, D'Deridex Warbird.")
        self.refresh_all()

    def _confirm_discard(self) -> bool:
        return not self.dirty or self.ask_yes_no(
            "Unsaved changes", "The current roster has unsaved changes.\n\nDiscard them?")

    def save_roster_clicked(self):
        self.save_roster(self.data_file)

    def load_roster_clicked(self):
        if not os.path.exists(self.data_file):
            self.show_info("Load Roster", f"No saved roster found yet:\n{self.data_file}\n\n"
                                          "Use 'Save Roster to JSON' first.")
            return
        if self._confirm_discard():
            self.load_roster(self.data_file)

    def save_roster_as(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save Roster As", defaultextension=".json",
            initialfile="sta2e_ships.json", filetypes=[("JSON files", "*.json")])
        if path:
            self.save_roster(path)

    def load_roster_from(self):
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(parent=self.root, title="Load Roster",
                                          filetypes=[("JSON files", "*.json"),
                                                     ("All files", "*.*")])
        if path:
            self.load_roster(path)

    def import_ships(self):
        path = filedialog.askopenfilename(parent=self.root, title="Import Ship(s)",
                                          filetypes=[("JSON files", "*.json"),
                                                     ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                ships, _meta, errors = parse_roster_data(json.load(fh))
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            self.show_error("Import failed", f"Could not import from\n{path}\n\n{exc}")
            return
        for ship in ships:
            ship.name = self.unique_name(ship.name)
            self.ships.append(ship)
        self.log(f"Imported {len(ships)} ship(s) from {path}: "
                 + ", ".join(s.name for s in ships))
        for err in errors:
            self.log(f"Skipped invalid ship ({err}).", "alert")
        self.changed()

    def export_ship(self):
        ship = self.selected_roster_ship() or self.attacker
        if ship is None:
            return
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in ship.name).strip()
        path = filedialog.asksaveasfilename(
            parent=self.root, title=f"Export {ship.name}", defaultextension=".json",
            initialfile=f"{safe or 'ship'}.json", filetypes=[("JSON files", "*.json")])
        if not path:
            return
        data = {"app": APP_NAME, "format_version": SAVE_FORMAT_VERSION,
                "ships": [ship.to_dict()]}
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            self.show_error("Export failed", str(exc))
            return
        self.log(f"Exported {ship.name} to {path}.")

    def reset_to_presets(self):
        if self.ask_yes_no("Reset Roster", "Replace the current roster with the preset ships?"
                                           "\n(Your JSON file is not changed until you save.)"):
            self._load_presets()
            self.dirty = True
            self.refresh_all()

    def on_close(self):
        if self.dirty:
            ans = self.ask_yes_no_cancel("Save before exit?",
                                         f"Save the roster to {self.data_file} before exiting?")
            if ans is None:
                return
            if ans and not self.save_roster(self.data_file):
                return
        self.root.destroy()

    # ================================================================== help
    def show_reference(self):
        win = tk.Toplevel(self.root)
        win.title("STA 2e Quick Reference")
        win.geometry("760x640")
        txt = ScrolledText(win, wrap="word", padx=8, pady=8)
        txt.pack(fill="both", expand=True)
        txt.tag_configure("h", font=self.font_big, foreground="#5b2c83")
        txt.insert("end", "Crew Quality (NPC rolls)\n", "h")
        for q, (a, d) in CREW_QUALITY.items():
            txt.insert("end", f"  {q:<12} Attribute {a}, Department {d}\n")
        txt.insert("end", "\nShaken / Minor Damage (d20)\n", "h")
        for lo, hi, name, desc in MINOR_DAMAGE_TABLE:
            txt.insert("end", f"  {lo}-{hi}: {name} - {desc}\n")
        txt.insert("end", "  Shields < 50% or < 25% -> Shaken. Dropping below 25% after "
                          "already being Shaken by the same attack -> Breach instead.\n")
        for table_name, table in SYSTEM_HIT_TABLES.items():
            txt.insert("end", f"\nSystem Hit Table - {table_name}\n", "h")
            for lo, hi, sysname in table:
                txt.insert("end", f"  {lo}-{hi}: {sysname}\n" if lo != hi
                           else f"  {lo}: {sysname}\n")
        txt.insert("end", "\nNature of Breach (d20)\n", "h")
        for lo, hi, name, desc in BREACH_NATURE_TABLE:
            txt.insert("end", f"  {lo}-{hi}: {name} - {desc}\n")
        txt.insert("end", "  A system keeps its most severe condition; it clears when the "
                          "system's last breach is patched. Restore (standard Minor Action) "
                          "lets a Malfunctioning subsystem be used for the rest of the turn.\n")
        txt.insert("end", "\nBreach triggers\n", "h")
        txt.insert("end", "  Shields reduced to 0; any damaging hit while Shields are 0; "
                          "< 25% when already Shaken in the same attack. High Yield adds +1.\n")
        txt.insert("end", "\nWeapon Qualities\n", "h")
        for q, (has_x, desc) in WEAPON_QUALITIES.items():
            txt.insert("end", f"  {q}{' X' if has_x else ''}: {desc}\n")
        txt.insert("end", "\nWeapon Auto-Calculator (Core Rulebook pp. 228-230)\n", "h")
        txt.insert("end", "  Energy weapon = Energy Type + Delivery Method; Damage = Scale + "
                          "delivery bonus + Weapons System Damage Bonus.\n")
        for name, (rng, bonus, quals) in ENERGY_DELIVERY_METHODS.items():
            q = ", ".join(quals) or "-"
            txt.insert("end", f"  {name}: Range {rng}, Damage Scale + {bonus}; {q}\n")
        for name, quals in ENERGY_TYPES.items():
            q = Weapon(qualities=quals).quality_text() or "-"
            txt.insert("end", f"  {name}: {q}\n")
        txt.insert("end", "  Torpedoes (Damage = listed + Weapons System Damage Bonus):\n")
        for name, (rng, dmg, quals) in TORPEDO_TYPES.items():
            q = ", ".join(quals) or "-"
            txt.insert("end", f"  {name}: Range {rng}, Damage {dmg}; {q}\n")
        prev = 0
        bands = []
        for highest, bonus in WEAPONS_DAMAGE_BONUS_TABLE:
            bands.append(f"{prev + 1}-{highest}: +{bonus}" if prev else f"<={highest}: +{bonus}")
            prev = highest
        bands.append(f"{prev + 1}+: +{WEAPONS_DAMAGE_BONUS_MAX}")
        txt.insert("end", "  Weapons System Damage Bonus by Weapons rating: "
                          + ", ".join(bands) + "\n")
        txt.insert("end", "\nStarship Talents & Special Rules\n", "h")
        for t, (kind, desc) in STARSHIP_TALENTS.items():
            txt.insert("end", f"  {t}{' (Special Rule)' if kind == SPECIAL_RULE else ''}: "
                              f"{desc}\n")
        txt.insert("end", "\nCloaking\n", "h")
        txt.insert("end", "  Cloak: Tactical Major Action, Control + Engineering Diff 2 (assist "
                          "Engines + Security), needs Reserve Power. Decloak: Minor Action. A "
                          "cloaked ship has Shields 0 (cannot raise them) and cannot attack. "
                          "Enemies must Reveal it (Reason + Science, Diff 3) before targeting "
                          "it, and the Cloaked trait still adds +1 Difficulty.\n")
        txt.insert("end", "\nBridge Stations & Actions\n", "h")
        for station, actions in BRIDGE_STATIONS.items():
            txt.insert("end", f"  {station}\n")
            for name, a in actions.items():
                task = f"{a['attr']} + {a['dept']}, " if a["attr"] and a["roll"] else ""
                diff = f"Diff {a['base']}" if a["roll"] else "no roll"
                txt.insert("end", f"    - {name} ({a['kind']}; {task}{diff}): {a['reminder']}\n")
        txt.insert("end", "\nDifficulty\n", "h")
        txt.insert("end", "  Total = Base + Weapon modifiers (Cumbersome +1) + context "
                          "(range, Evasive, Jammed, ...) + GM Modifier (-3..+5).\n"
                          "  Bonus d20s: 3rd costs 1, 4th 2, 5th 3 Momentum (NPC: Threat).\n"
                          "  Opposed tasks (Evasive Action / Defensive Fire): the defender "
                          "rolls first; their successes replace the base Difficulty, other "
                          "modifiers still apply, ties go to the attacker.\n"
                          "  Attack Pattern: attacks against that ship are -1 Difficulty.\n"
                          "  Persistent: after a hit spend 1-3 Momentum; the target takes half "
                          "the weapon damage (rounded up) at each End Round for that many "
                          "rounds.\n")
        txt.configure(state="disabled")

    def show_about(self):
        self.show_info("About", f"{APP_NAME} v{APP_VERSION}\n\nGM helper for Star Trek "
                                "Adventures 2nd Edition starship combat.\n\nRoster file:\n"
                                f"{self.data_file}\n\nUnofficial fan tool - Star Trek "
                                "Adventures is published by Modiphius Entertainment.")


def _enable_windows_dpi_awareness():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main():
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    CombatHelperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
