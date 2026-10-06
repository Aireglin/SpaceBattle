# STA 2e Combat Helper

A Gamemaster desktop tool for **Star Trek Adventures 2nd Edition** starship combat.
It handles Bridge Actions, task Difficulty, dice, damage, Shaken results, breaches,
turn budgets and the ship roster. It is a single file (`main.py`) that uses only the
Python standard library (`tkinter` / `ttk`), and it builds into one Windows `.exe`
with PyInstaller.

## Run from source

Requires Python 3.10 or newer with Tk (the python.org Windows installer includes it).

```bash
python main.py
```

On Debian or Ubuntu, install Tk first with `sudo apt install python3-tk`.

## Build the Windows executable

Run these commands on Windows, from this folder:

```bat
pip install pyinstaller
pyinstaller --onefile --windowed --name STA2e_Combat_Helper main.py
```

The result is `dist\STA2e_Combat_Helper.exe`. Without `--name`, the plain
`pyinstaller --onefile --windowed main.py` command produces the same program, called
`dist\main.exe`. You can also run `build_exe.bat`, which does both steps.

PyInstaller does not cross-compile, so build the `.exe` on Windows.

## Saving and loading (`sta2e_ships.json`)

* The roster file is kept **next to the executable**, or next to `main.py` when you
  run from source. If it exists, it loads automatically on startup. Otherwise the
  app starts with the two preset ships.
* **Save Roster to JSON** and **Load Roster from JSON** are on the top bar and in the
  File menu, with `Ctrl+S` as a shortcut. A save stores every ship's full combat
  state (shields, breaches, effects, turns used) plus Round, Threat, Momentum, GM
  Modifier and the Attacker / Target selection.
* The File menu also has: *Save Roster As…*, *Load Roster From File…*,
  *Import Ship(s)…* (accepts a roster file, a ship export, a list of ships or a
  single ship), *Export Selected Ship…*, *Export Combat Log…* and *Reset Roster to
  Presets*.
* If the roster has unsaved changes, the app asks whether to save before it exits.

## Screen layout

| Area | Contents |
|---|---|
| **Top bar** | Threat and Momentum counters (Momentum is capped at 6), Round counter, **END ROUND** button, GM Modifier spinbox (−3…+5), Save / Load buttons |
| **Left** | Ship roster (`[A]` = attacker, `[T]` = target), Attacker / Target pickers, New / Edit / Duplicate / Delete / Export / Import / Full Repair, the **NPC Generator** (Scale, Crew Quality, role profile), **Active Ship Status** and the **Turn Tracker** ("Turns used: X / Scale") |
| **Middle** | Two-level **Station → Action** selector, action options (weapon, salvo, range, Targeting Solution and Scan for Weakness choices), live **Difficulty** breakdown, **Rule Hints** box, and the **Action Resolver** (crew Attribute + Department, Focus, dice pool, ship assist, auto-roll or manual successes, opposed defender successes) |
| **Right** | Target status with shield bar and the 50% / 25% markers, Resistance, effects, Reserve Power / shields / weapons toggles, manual shield adjustment, the **Damage Resolver**, **System Hit Generator**, **Shaken Resolver**, **Breach Tracker** and complications |
| **Bottom** | Scrollable, colour-coded **Combat History Log** |

## Rules automation

* **Turn budget:** each Major Action uses one of the ship's turns. You get a warning
  when a ship goes past its Scale. If an NPC ship uses the same system twice in a
  round, you're asked to spend 1 Threat (or to override, or to cancel).
* **End Round:** advances the Round counter by 1. It resets turn counters and the
  per-round effects (Modulate Shields +2 Resistance, Evasive Action, Defensive Fire,
  Attack Pattern, Jammed, Slowed, Shaken) and applies any Persistent damage. Then it
  logs `--- END OF ROUND X ---`.
* **Crew Quality** sets the NPC crew's Attribute / Department: Basic 8/1,
  Proficient 9/2, Talented 10/3, Exceptional 11/4.
* **Difficulty** = Base + Weapon modifiers (Cumbersome +1) + context + GM Modifier.
  Context covers range beyond Close for sensor tasks, the ship's own Evasive Action,
  Shields at 0 for Regenerate Shields, Losing Power for Regain Power, Jammed for
  Comms / Sensors tasks, and Devastating breaches for Damage Control.
* **Dice:** each d20 that rolls ≤ Attribute + Department is a success, and a roll ≤
  the Department (with a Focus) counts double. A 20 is a complication. Assist dice
  count only if the crew scored a success. Bonus dice cost 1 / 2 / 3 Momentum
  (Threat for NPCs). Excess successes go to Momentum for player ships and to Threat
  for NPC ships.
* **Costs:** Direct costs 1 Momentum (NPC: 1 Threat). A torpedo adds 1 Threat when a
  player ship fires it, or 3 for a salvo; NPC ships spend Threat instead. When a
  player ship doesn't have enough Momentum, the shortfall is added to Threat.
* **Damage:** Resistance is deducted unless the attack is Piercing. If Shields drop
  below 50% or below 25%, the Shaken Resolver opens. In it you can pick a result from
  the Minor Damage table or click **Auto-Roll d20**; a 19–20 re-rolls automatically.
  A breach is triggered when Shields hit 0, when a ship is hit at 0 Shields, or when
  Shields drop below 25% after the ship was already Shaken by the same attack. Each
  breach rolls on the System Hit table (d12: 1–2 Comms … 11–12 Weapons). With
  Targeting Solution set to *choose*, you pick the system instead.
* **Weapon qualities:** automated where the rule is mechanical:
  * Cumbersome, Piercing
  * Intense / Depleting (1 Momentum per +1 damage)
  * Spread (Devastating Attack costs 1)
  * High Yield (+1 breach)
  * Devastating (+1 Damage Control Difficulty)
  * Dampening (drains Reserve Power)
  * Jamming, Slowing
  * Persistent X (X damage at every End Round)
  * Versatile X (+X Momentum)

  Area, Calibration and Hidden X appear as reminders only.

### Calls I made where the spec was silent

These are easy to change in `main.py`, where each one is a constant or a short
function:

* **Opposed tasks** (the target is using Evasive Action or Defensive Fire): the
  attacker has to reach the Difficulty **and** score more successes than the
  defender; a tie goes to the defender. In auto mode the defender's roll is made
  for you.
* **Bonus damage** costs 2 Momentum per +1. **Devastating Attack** costs 2 Momentum
  and adds one extra system hit / breach.
* **Ram:** the suggested collision damage is the other ship's Scale, and you can
  edit it.
* **Persistent** damage lasts until a successful Damage Control (or *Clear Temp
  Effects*).
* **Breaches** don't change task Difficulty automatically. You get an alert, and you
  apply any penalty your table uses through the GM Modifier.
* The spec didn't give weapon profiles for the **preset ships** (USS Aurora and the
  D'Deridex Warbird), so those are editable samples. Their scale, shields,
  resistance, systems and departments match the spec.

## Tests

```bash
python -m unittest discover -s tests
```

These tests cover the rules engine (damage thresholds, dice, Difficulty, tables,
save-file parsing and the generator). No window opens.

---
*Unofficial fan tool. Star Trek Adventures is published by Modiphius Entertainment.*
