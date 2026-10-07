"""Rules-engine tests for main.py (no window is created).

Run with:  python -m unittest discover -s tests
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from main import (  # noqa: E402
    AREA_OR_SPREAD, ENERGY_DELIVERY_METHODS, ENERGY_TYPES, TORPEDO_TYPES, calculate_weapon,
    format_weapon_calc, infer_weapon_profile, resolve_area_or_spread, weapons_damage_bonus,
    BRIDGE_STATIONS, CREW_QUALITY, Die, Ship, Weapon, bonus_damage_cost_each, bonus_dice_cost,
    compute_difficulty, devastating_attack_cost, evaluate_task, generate_npc_ship,
    minor_damage_lookup, outcome_from_successes, parse_roster_data, preset_ships,
    resolve_shield_damage, roll_minor_damage, system_hit_lookup,
)


def action(station, name):
    return BRIDGE_STATIONS[station][name]


class FixedRng:
    """Returns queued values from randint, for deterministic dice."""

    def __init__(self, values):
        self.values = list(values)

    def randint(self, _lo, _hi):
        return self.values.pop(0)


class CrewQualityTests(unittest.TestCase):
    def test_table(self):
        self.assertEqual(CREW_QUALITY["Basic"], (8, 1))
        self.assertEqual(CREW_QUALITY["Proficient"], (9, 2))
        self.assertEqual(CREW_QUALITY["Talented"], (10, 3))
        self.assertEqual(CREW_QUALITY["Exceptional"], (11, 4))

    def test_ship_crew_ratings_default(self):
        self.assertEqual(Ship(name="x").crew_ratings(), (10, 3))


class TableTests(unittest.TestCase):
    def test_minor_damage_ranges(self):
        self.assertEqual(minor_damage_lookup(1), "Brace for Impact!")
        self.assertEqual(minor_damage_lookup(6), "Brace for Impact!")
        self.assertEqual(minor_damage_lookup(7), "Losing Power!")
        self.assertEqual(minor_damage_lookup(12), "Losing Power!")
        self.assertEqual(minor_damage_lookup(13), "Casualties and Minor Damage")
        self.assertEqual(minor_damage_lookup(18), "Casualties and Minor Damage")
        self.assertEqual(minor_damage_lookup(19), "Re-roll")
        self.assertEqual(minor_damage_lookup(20), "Re-roll")

    def test_minor_damage_rerolls_automatically(self):
        rolls, name = roll_minor_damage(FixedRng([20, 19, 9]))
        self.assertEqual(rolls, [20, 19, 9])
        self.assertEqual(name, "Losing Power!")

    def test_system_hit_table(self):
        expected = {1: "Communications", 2: "Communications", 3: "Computers", 4: "Computers",
                    5: "Engines", 6: "Engines", 7: "Sensors", 8: "Sensors", 9: "Structure",
                    10: "Structure", 11: "Weapons", 12: "Weapons"}
        for roll, system in expected.items():
            self.assertEqual(system_hit_lookup(roll), system)
        self.assertEqual(main.SYSTEM_HIT_DIE, 12)


class DamageTests(unittest.TestCase):
    def test_resistance_reduces_damage(self):
        out = resolve_shield_damage(21, 21, 8, 6)
        self.assertEqual(out.final_damage, 2)
        self.assertEqual(out.shields_after, 19)
        self.assertEqual(out.shaken_reasons, [])
        self.assertEqual(out.breach_reasons, [])

    def test_piercing_ignores_resistance(self):
        out = resolve_shield_damage(21, 21, 8, 6, piercing=True)
        self.assertEqual(out.final_damage, 8)
        self.assertEqual(out.resistance_applied, 0)

    def test_fully_absorbed(self):
        out = resolve_shield_damage(10, 20, 5, 7)
        self.assertEqual(out.final_damage, 0)
        self.assertEqual(out.shields_after, 10)

    def test_below_half_is_shaken(self):
        out = resolve_shield_damage(20, 20, 12, 1)   # 20 -> 9 (45%)
        self.assertEqual(len(out.shaken_reasons), 1)
        self.assertEqual(out.breach_reasons, [])

    def test_below_quarter_alone_is_shaken(self):
        out = resolve_shield_damage(8, 20, 5, 1)     # 40% -> 20%
        self.assertEqual(out.shaken_reasons, ["Shields dropped below 25%"])
        self.assertEqual(out.breach_reasons, [])

    def test_both_thresholds_in_one_attack_is_shaken_plus_breach(self):
        out = resolve_shield_damage(20, 20, 17, 1)   # 20 -> 4 (20%)
        self.assertEqual(len(out.shaken_reasons), 1)
        self.assertEqual(len(out.breach_reasons), 1)
        self.assertIn("already Shaken", out.breach_reasons[0])

    def test_reduced_to_zero_breaches(self):
        out = resolve_shield_damage(4, 20, 10, 0)      # already below 25% -> breach only
        self.assertEqual(out.shields_after, 0)
        self.assertEqual(out.breach_reasons, ["Shields reduced to 0"])
        self.assertEqual(out.shaken_reasons, [])

    def test_reduced_to_zero_from_below_half_is_shaken_plus_breach(self):
        out = resolve_shield_damage(8, 20, 10, 0)      # 40% -> 0: crosses 25%
        self.assertEqual(out.shaken_reasons, ["Shields dropped below 25%"])
        self.assertEqual(out.breach_reasons, ["Shields reduced to 0"])

    def test_full_to_zero_is_shaken_and_one_breach(self):
        out = resolve_shield_damage(21, 21, 30, 6)     # 21 -> 0 in one hit
        self.assertEqual(out.shaken_reasons, ["Shields dropped below 50%"])
        self.assertEqual(len(out.breach_reasons), 1)
        self.assertIn("reduced to 0", out.breach_reasons[0])

    def test_hit_at_zero_breaches(self):
        out = resolve_shield_damage(0, 20, 4, 1)
        self.assertEqual(out.breach_reasons, ["hit while Shields at 0"])

    def test_staying_above_half_no_effect(self):
        out = resolve_shield_damage(20, 20, 9, 0)    # 20 -> 11 (55%)
        self.assertEqual(out.shaken_reasons, [])
        self.assertEqual(out.breach_reasons, [])


class DiceTests(unittest.TestCase):
    def test_successes_and_crits(self):
        self.assertEqual(Die(3, 13, 3).successes, 2)
        self.assertEqual(Die(4, 13, 3).successes, 1)
        self.assertEqual(Die(13, 13, 3).successes, 1)
        self.assertEqual(Die(14, 13, 3).successes, 0)
        self.assertTrue(Die(20, 13, 3).complication)

    def test_assist_needs_crew_success(self):
        dice = [Die(18, 13, 3), Die(19, 13, 3), Die(2, 15, 4, "ship")]
        out = evaluate_task(dice, 1)
        self.assertEqual(out.successes, 0)
        self.assertTrue(out.assist_ignored)
        self.assertFalse(out.success)

    def test_excess_successes(self):
        dice = [Die(2, 13, 3), Die(10, 13, 3), Die(4, 15, 4, "ship")]
        out = evaluate_task(dice, 2)
        self.assertEqual(out.successes, 5)
        self.assertTrue(out.success)
        self.assertEqual(out.excess, 3)

    def test_difficulty_zero_always_succeeds(self):
        out = outcome_from_successes(0, 0)
        self.assertTrue(out.success)
        self.assertEqual(out.excess, 0)

    def test_opposed_difficulty_replaces_base(self):
        parts = [("Base (Energy)", 2), ("Weapon mods (Cumbersome)", 1), ("GM Modifier", 0)]
        self.assertEqual(main.opposed_difficulty(parts, 3), 4)
        self.assertEqual(main.opposed_difficulty([("Base", 2), ("GM Modifier", -3)], 1), 0)

    def test_opposed_ties_go_to_attacker(self):
        out = outcome_from_successes(3, 3, opposition=3)
        self.assertTrue(out.success)
        self.assertEqual(out.excess, 0)
        self.assertFalse(outcome_from_successes(2, 3, opposition=3).success)

    def test_bonus_dice_cost(self):
        self.assertEqual([bonus_dice_cost(n) for n in (1, 2, 3, 4, 5)], [0, 0, 1, 3, 6])


class DifficultyTests(unittest.TestCase):
    def setUp(self):
        self.ship = Ship(name="A")
        self.energy = Weapon("Phasers", "Energy", 5, "Medium")
        self.torp = Weapon("Torps", "Torpedo", 6, "Long", {"Cumbersome": 0})

    def test_fire_energy(self):
        total, _ = compute_difficulty("Fire", action("Tactical", "Fire"), self.ship, self.energy)
        self.assertEqual(total, 2)

    def test_fire_torpedo_cumbersome_and_gm(self):
        total, parts = compute_difficulty("Fire", action("Tactical", "Fire"), self.ship,
                                          self.torp, gm_modifier=1)
        self.assertEqual(total, 3 + 1 + 1)
        self.assertIn(("Base (Torpedo)", 3), parts)

    def test_evasive_attacker_penalty(self):
        self.ship.evasive = True
        total, _ = compute_difficulty("Fire", action("Tactical", "Fire"), self.ship, self.energy)
        self.assertEqual(total, 3)

    def test_sensor_range_penalty(self):
        adef = action("Sensor Operations", "Sensor Sweep")
        self.assertEqual(compute_difficulty("Sensor Sweep", adef, self.ship, None, "Close")[0], 1)
        self.assertEqual(compute_difficulty("Sensor Sweep", adef, self.ship, None, "Long")[0], 3)
        adef = action("Sensor Operations", "Scan for Weakness")
        self.assertEqual(compute_difficulty("Scan for Weakness", adef, self.ship, None,
                                            "Medium")[0], 3)

    def test_regenerate_shields_at_zero(self):
        adef = action("Operations / Engineering", "Regenerate Shields")
        self.assertEqual(compute_difficulty("Regenerate Shields", adef, self.ship)[0], 2)
        self.ship.shields = 0
        self.assertEqual(compute_difficulty("Regenerate Shields", adef, self.ship)[0], 3)

    def test_losing_power_penalty(self):
        adef = action("Operations / Engineering", "Regain Power")
        self.ship.regain_power_penalty = 1
        self.assertEqual(compute_difficulty("Regain Power", adef, self.ship)[0], 2)

    def test_gm_modifier_floor_zero(self):
        adef = action("Command", "Rally")
        self.assertEqual(compute_difficulty("Rally", adef, self.ship, gm_modifier=-3)[0], 0)

    def test_no_roll_action(self):
        total, parts = compute_difficulty("Modulate Shields",
                                          action("Tactical", "Modulate Shields"), self.ship)
        self.assertIsNone(total)
        self.assertEqual(parts, [])

    def test_quality_costs(self):
        self.assertEqual(bonus_damage_cost_each(None), 2)
        self.assertEqual(bonus_damage_cost_each(Weapon(qualities={"Intense": 0})), 1)
        self.assertEqual(bonus_damage_cost_each(Weapon(qualities={"Depleting": 0})), 1)
        self.assertEqual(devastating_attack_cost(None), 2)
        self.assertEqual(devastating_attack_cost(Weapon(qualities={"Spread": 0})), 1)


class ShipStateTests(unittest.TestCase):
    def test_presets(self):
        aurora, warbird = preset_ships()
        self.assertEqual((aurora.scale, aurora.max_shields), (5, 19))
        self.assertEqual((aurora.base_resistance, aurora.effective_resistance), (5, 7))
        self.assertEqual(aurora.systems["Sensors"], 11)
        self.assertEqual(aurora.departments["Security"], 4)
        self.assertEqual(aurora.tractor_strength_rating, 4)
        self.assertEqual({w.name: w.damage for w in aurora.weapons},
                         {"Phaser Arrays": 8, "Photon Torpedoes": 7})
        self.assertEqual(set(aurora.weapon("Phaser Arrays").qualities),
                         {"Versatile", "Area", "Spread"})
        for t in ("Ablative Armor", "Extensive Shuttlebays", "Rapid-Fire Torpedo Launcher",
                  "Advanced Sensor Suites", "Emergency Medical Hologram", "Experimental Vessel",
                  "Specialized Shuttlebay"):
            self.assertTrue(aurora.has_talent(t), t)
        self.assertEqual((warbird.scale, warbird.max_shields, warbird.effective_resistance),
                         (6, 21, 6))
        self.assertEqual(warbird.crew_quality, "Talented")
        self.assertEqual(warbird.departments["Command"], 3)
        self.assertEqual(warbird.tractor_strength_rating, 5)
        self.assertEqual({w.name: w.damage for w in warbird.weapons},
                         {"Disruptor Banks": 9, "Plasma Torpedoes": 7})
        self.assertEqual(set(warbird.weapon("Plasma Torpedoes").qualities),
                         {"Persistent", "Calibration", "Cumbersome"})
        for t in ("Cloaking Device", "Electronic Warfare Systems", "Fast Targeting Systems",
                  "Improved Damage Control", "Reduced Sensor Silhouette", "Secondary Reactors",
                  "Abundant Personnel"):
            self.assertTrue(warbird.has_talent(t), t)
        for t in aurora.talents + warbird.talents:
            self.assertIn(t, main.STARSHIP_TALENTS)

    def test_reset_round_keeps_lasting_state(self):
        s = Ship(name="X", shields=3)
        s.turns_used, s.systems_used = 4, ["Weapons"]
        s.resistance_bonus, s.evasive, s.shaken, s.jammed = 2, True, True, True
        s.breaches["Engines"] = 2
        s.calibrated_weapons = True
        s.reset_round()
        self.assertEqual((s.turns_used, s.systems_used, s.resistance_bonus), (0, [], 0))
        self.assertFalse(s.evasive or s.shaken or s.jammed)
        self.assertEqual(s.breaches["Engines"], 2)
        self.assertTrue(s.calibrated_weapons)
        self.assertEqual(s.shields, 3)

    def test_round_trip(self):
        aurora = preset_ships()[0]
        aurora.breaches["Weapons"] = 1
        aurora.persistent_effects.append({"amount": 4, "rounds": 2, "source": "Plasma",
                                          "piercing": False})
        aurora.talents.append("My Custom Talent")
        clone = Ship.from_dict(aurora.to_dict())
        self.assertEqual(clone, aurora)

    def test_from_dict_is_forgiving(self):
        ship = Ship.from_dict({"name": "Junk", "scale": "5", "shields_max": 10, "shields": 99,
                               "crew_quality": "Legendary", "systems": {"Weapons": "12"},
                               "weapons": [{"name": "Gun", "type": "Torpedo",
                                            "qualities": ["Piercing", "Bogus"]}]})
        self.assertEqual(ship.scale, 5)
        self.assertEqual(ship.shields, 10)
        self.assertEqual(ship.crew_quality, "Talented")
        self.assertEqual(ship.systems["Weapons"], 12)
        self.assertEqual(ship.systems["Engines"], 8)
        self.assertEqual(ship.weapons[0].wtype, "Torpedo")
        self.assertEqual(ship.weapons[0].qualities, {"Piercing": 0})

    def test_v1_save_migration(self):
        old = {"name": "Old", "shields_max": 18, "shields": 10, "resistance": 7,
               "weapons": [{"name": "Plasma", "wtype": "Torpedo", "damage": 7,
                            "qualities": {"Persistent": 2}}],
               "persistent_effects": [{"amount": 2, "source": "x"}]}
        ship = Ship.from_dict(old)
        self.assertEqual((ship.base_shields, ship.max_shields, ship.shields), (18, 18, 10))
        self.assertEqual((ship.base_resistance, ship.effective_resistance), (7, 7))
        self.assertEqual(ship.weapons[0].qualities, {"Persistent": 0})
        self.assertEqual(ship.persistent_effects[0]["rounds"], 1)

    def test_parse_roster_variants(self):
        d = preset_ships()[0].to_dict()
        ships, meta, errors = parse_roster_data({"round": 3, "ships": [d, {"bad": 1}]})
        self.assertEqual(len(ships), 1)
        self.assertEqual(meta["round"], 3)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(parse_roster_data([d, d])[0]), 2)
        self.assertEqual(len(parse_roster_data(d)[0]), 1)
        with self.assertRaises(ValueError):
            parse_roster_data({"foo": "bar"})

    def test_generator(self):
        rng = random.Random(7)
        for profile in main.GENERATOR_PROFILES:
            for scale in range(1, 8):
                ship = generate_npc_ship("G", scale, "Proficient", profile, rng)
                self.assertEqual(ship.scale, scale)
                self.assertEqual(ship.crew_ratings(), (9, 2))
                self.assertEqual(ship.base_shields, ship.systems["Structure"]
                                 + ship.departments["Security"] + scale)
                self.assertEqual(ship.shields, ship.max_shields)
                self.assertTrue(all(5 <= v <= 14 for v in ship.systems.values()))
                self.assertTrue(all(0 <= v <= 5 for v in ship.departments.values()))
                self.assertTrue(ship.weapons)


class MigrationHardeningTests(unittest.TestCase):
    def test_v1_lowered_shields_are_stored_not_live(self):
        ship = Ship.from_dict({"name": "Low", "shields_max": 20, "shields": 15,
                               "resistance": 2, "shields_up": False})
        self.assertEqual((ship.shields, ship.stored_shields), (0, 15))
        self.assertTrue(ship.raise_shields())
        self.assertEqual(ship.shields, 15)

    def test_v1_lowered_at_zero_stays_zero_when_raised(self):
        ship = Ship.from_dict({"name": "Z", "shields_max": 20, "shields": 0,
                               "shields_up": False})
        self.assertEqual(ship.stored_shields, 0)
        ship.raise_shields()
        self.assertEqual(ship.shields, 0)

    def test_cloaked_ship_loaded_with_shields_up_is_lowered(self):
        ship = Ship.from_dict({"name": "C", "base_shields": 21, "shields": 12,
                               "talents": ["Cloaking Device"], "cloaked": True,
                               "shields_up": True})
        self.assertEqual((ship.shields, ship.stored_shields, ship.shields_up), (0, 12, False))

    def test_v1_persistent_keeps_ignoring_resistance(self):
        ship = Ship.from_dict({"name": "P", "persistent_effects": [{"amount": 2,
                                                                    "source": "x"}]})
        self.assertTrue(ship.persistent_effects[0]["piercing"])
        v2 = Ship.from_dict({"name": "Q", "persistent_effects": [
            {"amount": 4, "rounds": 2, "source": "y", "piercing": False}]})
        self.assertFalse(v2.persistent_effects[0]["piercing"])

    def test_string_booleans_and_counter_clamps(self):
        ship = Ship.from_dict({"name": "S", "scale": 1, "cloaked": "false",
                               "reserve_power": "no", "crew_support_used": 50,
                               "small_craft_deployed": 3, "turns_used": -3})
        self.assertFalse(ship.cloaked)
        self.assertFalse(ship.reserve_power)
        self.assertEqual(ship.crew_support_used, ship.crew_support_max)
        self.assertEqual((ship.small_craft_deployed, ship.turns_used), (0, 0))

    def test_overflow_and_bad_ships_value(self):
        self.assertEqual(main.to_int(float("inf"), 7), 7)
        self.assertEqual(main.to_int("1e999", 3), 3)
        ship = Ship.from_dict({"name": "Big", "base_shields": float("inf")})
        self.assertEqual(ship.base_shields, 12)
        with self.assertRaises(ValueError):
            parse_roster_data({"ships": 5})
        with self.assertRaises(ValueError):
            parse_roster_data({"ships": {"name": "x"}})


class TalentTests(unittest.TestCase):
    def test_resistance_and_shield_talents(self):
        s = Ship(name="T", base_shields=10, shields=10, base_resistance=4)
        s.talents = ["Ablative Armor", "Improved Hull Integrity", "Advanced Shields"]
        self.assertEqual(s.effective_resistance, 7)
        self.assertEqual(s.max_shields, 15)
        s.resistance_bonus = 2
        self.assertEqual(s.effective_resistance, 9)
        self.assertIn("+2 Ablative Armor", s.resistance_text())

    def test_from_dict_clamps_to_effective_max(self):
        d = Ship(name="T", base_shields=10, shields=15, talents=["Advanced Shields"]).to_dict()
        self.assertEqual(Ship.from_dict(d).shields, 15)
        d["talents"] = []
        self.assertEqual(Ship.from_dict(d).shields, 10)

    def test_cloak_and_shields(self):
        s = Ship(name="W", base_shields=21, shields=15, talents=["Cloaking Device"])
        s.engage_cloak()
        self.assertTrue(s.cloaked)
        self.assertEqual(s.shields, 0)
        self.assertFalse(s.raise_shields())
        self.assertEqual(s.shields, 0)
        s.disengage_cloak()
        self.assertFalse(s.shields_up)          # still down after decloaking
        self.assertTrue(s.raise_shields())
        self.assertEqual(s.shields, 15)
        s.lower_shields()
        self.assertEqual((s.shields, s.stored_shields), (0, 15))

    def test_cloak_dropped_without_talent_on_load(self):
        d = Ship(name="X", cloaked=True).to_dict()
        self.assertFalse(Ship.from_dict(d).cloaked)

    def test_derived_pools(self):
        s = Ship(name="P", scale=5)
        self.assertEqual((s.crew_support_max, s.small_craft_readiness), (5, 0))
        s.talents = ["Abundant Personnel", "Extensive Shuttlebays"]
        self.assertEqual((s.crew_support_max, s.small_craft_readiness), (10, 4))
        self.assertEqual(s.max_small_craft_scale, 2)

    def test_assist_dice_talents(self):
        s = Ship(name="S", talents=["Advanced Sensor Suites", "Experimental Vessel"])
        self.assertEqual(s.ship_assist_dice("Sensors"), 2)
        self.assertEqual(s.ship_assist_dice("Weapons"), 1)
        s.breaches["Sensors"] = 1
        self.assertEqual(s.ship_assist_dice("Sensors"), 1)
        self.assertEqual(s.assist_complication_from, 18)
        self.assertTrue(Die(18, 10, 1, "ship", comp_from=18).complication)
        self.assertFalse(Die(17, 10, 1, "ship", comp_from=18).complication)
        self.assertFalse(Die(19, 10, 1).complication)

    def test_target_talent_difficulty(self):
        attacker = Ship(name="A")
        target = Ship(name="B", talents=["Point Defense System"])
        torp = Weapon("T", "Torpedo", 6, "Long")
        fire = action("Tactical", "Fire")
        total, parts = compute_difficulty("Fire", fire, attacker, torp, target=target)
        self.assertEqual(total, 4)
        self.assertIn(("Point Defense (Cover)", 1), parts)
        target.point_defense_active = False
        self.assertEqual(compute_difficulty("Fire", fire, attacker, torp, target=target)[0], 3)
        target.attack_pattern = True
        self.assertEqual(compute_difficulty("Fire", fire, attacker, torp, target=target)[0], 2)
        target.talents.append("Cloaking Device")
        target.cloaked = True
        self.assertEqual(compute_difficulty("Fire", fire, attacker, torp, target=target)[0], 3)
        self.assertEqual(compute_difficulty("Fire", fire, attacker, torp, target=attacker)[0], 3)

    def test_reroll_only_failed_dice(self):
        dice = [Die(3, 13, 3), Die(12, 13, 3)]
        self.assertIsNone(main.reroll_worst(dice, FixedRng([1])))
        dice = [Die(3, 13, 3), Die(18, 13, 3)]
        self.assertEqual(main.reroll_worst(dice, FixedRng([5])), (18, 5))

    def test_system_hit_tables(self):
        d20 = main.SYSTEM_HIT_TABLE_D20
        self.assertEqual(system_hit_lookup(1, d20), "Communications")
        self.assertEqual(system_hit_lookup(6, d20), "Engines")
        self.assertEqual(system_hit_lookup(17, d20), "Structure")
        self.assertEqual(system_hit_lookup(20, d20), "Weapons")
        for table in main.SYSTEM_HIT_TABLES.values():
            covered = [r for lo, hi, _s in table for r in range(lo, hi + 1)]
            self.assertEqual(covered, list(range(1, table[-1][1] + 1)))

    def test_pending_damage_bonus(self):
        self.assertEqual(main.pending_damage_bonus(None), 0)
        self.assertEqual(main.pending_damage_bonus(
            {"calibrate": 1, "scan_damage": 2, "rapid_fire": 1}), 4)

    def test_generator_talents(self):
        ship = generate_npc_ship("G", 4, "Basic", "Warship", random.Random(3),
                                 talents=["Advanced Shields", "Ablative Armor"])
        self.assertEqual(ship.max_shields, ship.base_shields + 5)
        self.assertEqual(ship.shields, ship.max_shields)
        self.assertEqual(ship.effective_resistance, ship.base_resistance + 2)


class BreachNatureTests(unittest.TestCase):
    def test_table_ranges(self):
        expected = {1: "Damaged", 4: "Damaged", 5: "Malfunctioning", 8: "Malfunctioning",
                    9: "Primary Offline", 12: "Primary Offline", 13: "Failing", 16: "Failing",
                    17: "Offline", 20: "Offline"}
        for roll, name in expected.items():
            self.assertEqual(main.breach_nature_lookup(roll), name)
        self.assertEqual(main.roll_breach_nature(FixedRng([14])), (14, "Failing"))

    def test_most_severe_condition_wins(self):
        s = Ship(name="B")
        s.breaches["Engines"] = 2
        self.assertEqual(s.set_breach_condition("Engines", "Failing"), "Failing")
        self.assertEqual(s.set_breach_condition("Engines", "Damaged"), "Failing")
        self.assertEqual(s.set_breach_condition("Engines", "Offline"), "Offline")
        self.assertEqual(s.set_breach_condition("Engines", "Damaged", force=True), "Damaged")
        self.assertEqual(s.breach_condition("Engines"), "Damaged")

    def test_condition_needs_a_breach(self):
        s = Ship(name="B")
        s.breach_conditions["Sensors"] = "Failing"
        self.assertEqual(s.breach_condition("Sensors"), "")
        s.normalize()
        self.assertEqual(s.breach_conditions["Sensors"], "")

    def test_restore_tracking(self):
        s = Ship(name="R")
        s.breaches["Engines"] = 1
        s.set_breach_condition("Engines", "Malfunctioning")
        self.assertTrue(s.needs_restore("Engines"))
        s.restored_systems.append("Engines")
        self.assertFalse(s.needs_restore("Engines"))
        s.reset_round()
        self.assertTrue(s.needs_restore("Engines"))

    def test_breach_difficulty(self):
        s = Ship(name="D")
        warp = action("Conn / Helm", "Warp")
        self.assertEqual(compute_difficulty("Warp", warp, s)[0], 1)
        s.breaches["Engines"] = 1
        for cond, extra in (("Damaged", 0), ("Malfunctioning", 0), ("Primary Offline", 1),
                            ("Failing", 1), ("Offline", 0)):
            s.set_breach_condition("Engines", cond, force=True)
            total, parts = compute_difficulty("Warp", warp, s, gm_modifier=1)
            self.assertEqual(total, 1 + extra + 1, cond)
        s.set_breach_condition("Engines", "Failing", force=True)
        total, parts = compute_difficulty("Warp", warp, s, gm_modifier=1)
        self.assertIn(("Failing breach: Engines", 1), parts)
        self.assertEqual(main.format_difficulty_hint(total, parts),
                         "Base 1 + 1 (Failing breach: Engines) + 1 (GM Modifier) = "
                         "Total Difficulty 3")

    def test_assist_system_breach_counts(self):
        s = Ship(name="A")
        scan = action("Sensor Operations", "Scan for Weakness")      # Sensors + Security
        self.assertEqual(main.action_systems(scan), ["Sensors"])
        create = action("Command", "Create Trait")
        self.assertEqual(main.action_systems(create), ["Computers"])
        s.breaches["Computers"] = 1
        s.set_breach_condition("Computers", "Primary Offline")
        self.assertEqual(compute_difficulty("Create Trait", create, s)[0], 3)

    def test_override_and_other_task_base(self):
        s = Ship(name="O")
        fire = action("Tactical", "Fire")
        self.assertEqual(compute_difficulty("Fire", fire, s, Weapon(), override=True)[0], 3)
        other = action(main.STANDARD_STATION, "Other Tasks")
        self.assertEqual(compute_difficulty("Other Tasks", other, s, custom_base=4)[0], 4)
        self.assertEqual(compute_difficulty("Other Tasks", other, s, custom_base=0)[0], 0)

    def test_persistence(self):
        s = Ship(name="P")
        s.breaches["Weapons"] = 1
        s.set_breach_condition("Weapons", "Failing")
        s.restored_systems = ["Weapons"]
        clone = Ship.from_dict(s.to_dict())
        self.assertEqual(clone.breach_condition("Weapons"), "Failing")
        self.assertEqual(clone.restored_systems, ["Weapons"])
        d = s.to_dict()
        d["breach_conditions"] = {"Weapons": "Exploded", "Engines": 5}
        self.assertEqual(Ship.from_dict(d).breach_conditions["Weapons"], "")


class StationTests(unittest.TestCase):
    def test_every_station_has_create_trait(self):
        for station, actions in BRIDGE_STATIONS.items():
            names = [n for n in actions if "Trait" in n]
            self.assertTrue(names, station)
            for n in names:
                self.assertEqual(actions[n]["base"], 2)
                self.assertEqual(actions[n]["kind"], "Major")

    def test_standard_actions_station(self):
        std = BRIDGE_STATIONS[main.STANDARD_STATION]
        for n in ("Change Position", "Interact", "Prepare", "Restore"):
            self.assertEqual(std[n]["kind"], "Minor", n)
        for n in ("Create / Alter Trait", "Assist", "Override", "Pass", "Ready", "Other Tasks"):
            self.assertEqual(std[n]["kind"], "Major", n)

    def test_station_lists(self):
        for station in ("Command", "Operations / Engineering", "Communications"):
            for n in ("Prepare", "Restore", "Interact", "Change Position"):
                self.assertIn(n, BRIDGE_STATIONS[station], (station, n))
        comms = BRIDGE_STATIONS["Communications"]
        self.assertEqual(comms["Send / Respond to Hail"]["kind"], "Free")
        self.assertEqual(comms["Internal Comms"]["kind"], "Free")
        self.assertIn("Damage Control", comms)
        self.assertEqual(BRIDGE_STATIONS["Operations / Engineering"]["Transport"]["base"], 1)
        self.assertEqual(comms["Transport"]["base"], 1)
        for station, n in (("Conn / Helm", "Impulse"), ("Tactical", "Fire"),
                           ("Sensor Operations", "Reveal"), ("Command", "Rally")):
            self.assertIn(n, BRIDGE_STATIONS[station])


class WeaponCalculatorTests(unittest.TestCase):
    """Auto-Calculate Weapon Stats (Core Rulebook pp. 228-230)."""

    def test_weapons_damage_bonus_bands(self):
        expected = {1: 0, 6: 0, 7: 1, 8: 1, 9: 2, 10: 2, 11: 3, 12: 3, 13: 4, 16: 4}
        for rating, bonus in expected.items():
            self.assertEqual(weapons_damage_bonus(rating), bonus, rating)
        self.assertEqual(weapons_damage_bonus("junk"), 0)

    def test_delivery_methods(self):
        expected = {"Cannon": ("Close", 2), "Banks": ("Medium", 1), "Arrays": ("Medium", 0),
                    "Spinal Lance": ("Long", 3)}
        for delivery, (rng, plus) in expected.items():
            w, parts = calculate_weapon("Energy", 4, 6, "Free Electron Laser", delivery)
            self.assertEqual((w.range, w.damage), (rng, 4 + plus), delivery)
            self.assertEqual(sum(v for _l, v in parts), w.damage)
        self.assertEqual(ENERGY_DELIVERY_METHODS["Arrays"][2], {AREA_OR_SPREAD: 0})
        self.assertEqual(ENERGY_DELIVERY_METHODS["Spinal Lance"][2], {"Cumbersome": 0})

    def test_energy_type_qualities(self):
        expected = {
            "Antiproton Beam": {"High Yield"}, "Disruptor": {"Intense"},
            "Electromagnetic / Ionic": {"Dampening", "Piercing"}, "Free Electron Laser": set(),
            "Graviton Beam": {"Devastating", "Piercing"}, "Phase / Pulse": {"Versatile"},
            "Phased Polaron Beam": {"Intense", "Piercing"}, "Phaser": {"Versatile"},
            "Proton Beam": {"Persistent"}, "Tetryon Beam": {"Depleting"}}
        self.assertEqual(set(ENERGY_TYPES), set(expected))
        for etype, quals in expected.items():
            self.assertEqual(set(ENERGY_TYPES[etype]), quals, etype)
        self.assertEqual(ENERGY_TYPES["Phaser"]["Versatile"], 2)
        self.assertEqual(ENERGY_TYPES["Phase / Pulse"]["Versatile"], 1)

    def test_combined_examples(self):
        w, parts = calculate_weapon("Energy", 5, 11, "Phaser", "Arrays")
        self.assertEqual(w.name, "Phaser Arrays")
        self.assertEqual((w.range, w.damage), ("Medium", 5 + 0 + 3))
        self.assertEqual(w.qualities, {"Versatile": 2, AREA_OR_SPREAD: 0})
        self.assertEqual(w.quality_text(), "Versatile 2, Area or Spread")
        self.assertEqual(format_weapon_calc(parts),
                         "Scale 5 + 0 (Arrays) + 3 (Weapons 11 bonus) = Damage 8")
        w, _ = calculate_weapon("Energy", 6, 9, "Disruptor", "Spinal Lance")
        self.assertEqual(w.name, "Disruptor Spinal Lance")
        self.assertEqual((w.range, w.damage), ("Long", 6 + 3 + 2))
        self.assertEqual(w.qualities, {"Intense": 0, "Cumbersome": 0})
        self.assertEqual((w.energy_type, w.delivery, w.torpedo_type),
                         ("Disruptor", "Spinal Lance", ""))

    def test_bonus_can_be_left_out(self):
        w, parts = calculate_weapon("Energy", 5, 11, "Phaser", "Cannon", include_bonus=False)
        self.assertEqual(w.damage, 7)
        self.assertEqual(len(parts), 2)

    def test_torpedo_table(self):
        expected = {
            "Chroniton": ("Long", 3, {"Calibration", "Slowing"}),
            "Gravimetric": ("Long", 5, {"Calibration", "Cumbersome", "High Yield", "Piercing"}),
            "Neutronic": ("Long", 4, {"Calibration", "Dampening"}),
            "Nuclear": ("Medium", 3, {"Calibration", "Intense"}),
            "Photon": ("Long", 3, {"High Yield"}),
            "Photonic": ("Long", 2, {"High Yield"}),
            "Plasma": ("Long", 5, {"Calibration", "Cumbersome", "Persistent"}),
            "Polaron": ("Long", 3, {"Calibration", "Piercing"}),
            "Positron": ("Long", 5, {"Calibration", "Cumbersome", "Dampening"}),
            "Quantum": ("Long", 4, {"Calibration", "High Yield", "Intense"}),
            "Spatial": ("Medium", 2, set()),
            "Tetryonic": ("Long", 2, {"Depleting", "High Yield"}),
            "Transphasic": ("Long", 4, {"Calibration", "Devastating", "Piercing"}),
            "Tricobalt": ("Long", 6, {"Area", "Calibration", "Cumbersome"}),
        }
        self.assertEqual(set(TORPEDO_TYPES), set(expected))
        for ttype, (rng, dmg, quals) in expected.items():
            w, _ = calculate_weapon("Torpedo", 5, 6, torpedo_type=ttype)   # bonus +0
            self.assertEqual((w.name, w.wtype, w.range, w.damage, set(w.qualities)),
                             (f"{ttype} Torpedoes", "Torpedo", rng, dmg, quals), ttype)
        w, _ = calculate_weapon("Torpedo", 5, 13, torpedo_type="Photon")
        self.assertEqual(w.damage, 3 + 4)

    def test_every_calculated_quality_is_known(self):
        for etype in ENERGY_TYPES:
            for delivery in ENERGY_DELIVERY_METHODS:
                w, _ = calculate_weapon("Energy", 4, 9, etype, delivery)
                self.assertTrue(set(w.qualities) <= set(main.WEAPON_QUALITIES), w)
                self.assertEqual(Weapon.from_dict(w.to_dict()), w)
        for ttype in TORPEDO_TYPES:
            w, _ = calculate_weapon("Torpedo", 4, 9, torpedo_type=ttype)
            self.assertTrue(set(w.qualities) <= set(main.WEAPON_QUALITIES), w)
            self.assertEqual(Weapon.from_dict(w.to_dict()), w)

    def test_incomplete_selection(self):
        self.assertEqual(calculate_weapon("Energy", 5, 9, "Phaser", ""), (None, []))
        self.assertEqual(calculate_weapon("Energy", 5, 9, "", "Banks"), (None, []))
        self.assertEqual(calculate_weapon("Torpedo", 5, 9, "Phaser", "Banks"), (None, []))
        self.assertEqual(calculate_weapon("Torpedo", 5, 9, torpedo_type="Nope"), (None, []))

    def test_presets_match_the_calculator(self):
        aurora, warbird = preset_ships()
        for ship, wname, args in ((aurora, "Phaser Arrays", ("Energy", "Phaser", "Arrays", "")),
                                  (warbird, "Disruptor Banks",
                                   ("Energy", "Disruptor", "Banks", "")),
                                  (warbird, "Plasma Torpedoes", ("Torpedo", "", "", "Plasma"))):
            std, _ = calculate_weapon(args[0], ship.scale, ship.systems["Weapons"], *args[1:])
            self.assertEqual(std.damage, ship.weapon(wname).damage, wname)
            self.assertEqual(std.range, ship.weapon(wname).range, wname)

    def test_profile_persistence_and_sanitising(self):
        w = Weapon.from_dict({"name": "X", "wtype": "Energy", "energy_type": "Phaser",
                              "delivery": "Warp Core", "torpedo_type": "Photon"})
        self.assertEqual((w.energy_type, w.delivery, w.torpedo_type), ("Phaser", "", ""))
        w = Weapon.from_dict({"name": "T", "wtype": "Torpedo", "energy_type": "Phaser",
                              "torpedo_type": "Quantum"})
        self.assertEqual((w.energy_type, w.delivery, w.torpedo_type), ("", "", "Quantum"))
        old = Weapon.from_dict({"name": "Old", "wtype": "Energy", "energy_type": None})
        self.assertEqual((old.energy_type, old.delivery, old.torpedo_type), ("", "", ""))
        self.assertTrue(old.include_bonus)                     # older files: bonus counted
        self.assertFalse(Weapon.from_dict({"name": "N", "include_bonus": "false"}).include_bonus)
        nob = calculate_weapon("Energy", 5, 11, "Phaser", "Arrays", include_bonus=False)[0]
        self.assertFalse(nob.include_bonus)
        self.assertEqual(Weapon.from_dict(nob.to_dict()), nob)
        ship = preset_ships()[0]
        ship.weapons.append(calculate_weapon("Energy", 5, 11, "Phaser", "Cannon")[0])
        clone = Ship.from_dict(ship.to_dict())
        self.assertEqual(clone.weapons[-1].delivery, "Cannon")

    def test_infer_profile_from_names(self):
        self.assertEqual(infer_weapon_profile("Phaser Arrays", "Energy"), ("Phaser", "Arrays", ""))
        self.assertEqual(infer_weapon_profile("Disruptor Banks", "Energy"),
                         ("Disruptor", "Banks", ""))
        self.assertEqual(infer_weapon_profile("Phased Polaron Beam", "Energy")[0],
                         "Phased Polaron Beam")
        self.assertEqual(infer_weapon_profile("Photon Torpedoes", "Torpedo"), ("", "", "Photon"))
        self.assertEqual(infer_weapon_profile("Photonic Torpedo", "Torpedo"),
                         ("", "", "Photonic"))
        self.assertEqual(infer_weapon_profile("Torpedo Launchers", "Torpedo"), ("", "", ""))
        self.assertEqual(infer_weapon_profile("Main Gun", "Energy"), ("", "", ""))

    def test_area_or_spread_choice(self):
        w, _ = calculate_weapon("Energy", 5, 11, "Phaser", "Arrays")
        spread = resolve_area_or_spread(w, "Spread")
        self.assertEqual(spread.qualities, {"Versatile": 2, "Spread": 0})
        self.assertEqual(devastating_attack_cost(spread), 1)
        area = resolve_area_or_spread(w, "Area")
        self.assertTrue(area.has("Area") and not area.has("Spread"))
        self.assertEqual(devastating_attack_cost(area), 2)
        self.assertTrue(w.has(AREA_OR_SPREAD))            # original untouched
        self.assertEqual(resolve_area_or_spread(w, None).qualities, w.qualities)


if __name__ == "__main__":
    unittest.main()
