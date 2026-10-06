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
        out = resolve_shield_damage(5, 20, 10, 0)
        self.assertEqual(out.shields_after, 0)
        self.assertEqual(out.breach_reasons, ["Shields reduced to 0"])
        self.assertEqual(out.shaken_reasons, [])

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

    def test_opposed_ties_favour_defender(self):
        self.assertFalse(outcome_from_successes(3, 2, opposition=3).success)
        win = outcome_from_successes(4, 2, opposition=3)
        self.assertTrue(win.success)
        self.assertEqual(win.excess, 1)

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
        self.assertEqual((aurora.scale, aurora.shields_max, aurora.resistance), (5, 19, 7))
        self.assertEqual(aurora.systems["Sensors"], 11)
        self.assertEqual(aurora.departments["Security"], 4)
        self.assertEqual((warbird.scale, warbird.shields_max, warbird.resistance), (6, 21, 6))
        self.assertEqual(warbird.crew_quality, "Talented")
        self.assertEqual(warbird.departments["Command"], 3)

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
        aurora.persistent_effects.append({"amount": 2, "source": "Plasma"})
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
                self.assertEqual(ship.shields_max, ship.systems["Structure"]
                                 + ship.departments["Security"] + scale)
                self.assertTrue(all(5 <= v <= 14 for v in ship.systems.values()))
                self.assertTrue(all(0 <= v <= 5 for v in ship.departments.values()))
                self.assertTrue(ship.weapons)


if __name__ == "__main__":
    unittest.main()
