# STA 2e Combat Helper

A Gamemaster desktop tool for **Star Trek Adventures 2nd Edition** starship combat.
It handles Bridge Actions, task Difficulty, dice, damage, Shaken results, breaches,
weapon qualities, **starship talents and special rules**, turn budgets and the ship
roster. It is a single file (`main.py`) that uses only the Python standard library
(`tkinter` / `ttk`), and it builds into one Windows `.exe` with PyInstaller.

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
  state (shields, breaches, talents, cloak, effects, turns used) plus Round, Threat,
  Momentum, GM Modifier, the system hit table and the Attacker / Target selection.
* The File menu also has: *Save Roster As…*, *Load Roster From File…*,
  *Import Ship(s)…* (accepts a roster file, a ship export, a list of ships or a
  single ship), *Export Selected Ship…*, *Export Combat Log…* and *Reset Roster to
  Presets*.
* Rosters saved by the first version of the app (format 1) still load. Their Shields
  and Resistance totals become the ships' base values.
* If the roster has unsaved changes, the app asks whether to save before it exits.

## Screen layout

| Area | Contents |
|---|---|
| **Top bar** | Threat and Momentum counters (Momentum is capped at 6), Round counter, **END ROUND** button, GM Modifier spinbox (−3…+5), Save / Load buttons. The **Combat** menu has End Round, *New Scene* and *New Adventure*. |
| **Left** | Ship roster (`[A]` = attacker, `[T]` = target), Attacker / Target pickers, New / Edit / Duplicate / Delete / Export / Import / Full Repair, the **Custom Ship / NPC Generator** (Scale, Crew Quality, role profile, **Starship Talents multi-selector**), **Active Ship Status** (shield bar, Shields and Resistance with their talent bonuses broken out, **Cloak toggle**, Crew Support and Small Craft trackers, talents, effects) and the **Turn Tracker** ("Turns used: X / Scale") |
| **Middle** | Two-level **Station → Action** selector, action options (weapon, salvo, range, Targeting Solution and Scan for Weakness choices, Secondary Reactors button), live **Difficulty** breakdown, **Rule Hints** box, and the **Action Resolver** (crew Attribute + Department, Focus, dice pool, ship assist, auto-roll or manual successes, opposed defender successes) |
| **Right** | Target status with shield bar and the 50% / 25% markers, Resistance, effects, toggles for Reserve Power, shields, weapons, Point Defense and the target's cloak, manual shield adjustment, **Active Quality & Talent Alerts**, the **Damage Resolver**, the **System Hit Generator** (switchable table), the **Shaken Resolver**, the **Breach Tracker** and complications |
| **Bottom** | Scrollable, colour-coded **Combat History Log** |

The ship editor (*New…* / *Edit…*) sets base Shields and Resistance, Tractor Beam
Strength, systems, departments, weapons with qualities, and a **talents and special
rules multi-select**. You can also add custom talents there, which show up as
reminders. A live line shows the effective Shields, Resistance, Tractor and Small
Craft values once talents are applied.

## Starship talents and special rules

| Talent / rule | What the app does |
|---|---|
| **Ablative Armor** | +2 Resistance, added automatically |
| **Improved Hull Integrity** | +1 Resistance, added automatically |
| **Advanced Shields** | +5 maximum Shields, added automatically |
| **Cloaking Device** | Enables the **Cloak toggle** (Active Ship Status, or *Toggle Target Cloak*) and the Tactical actions **Cloak** (Major: Control + Engineering, Difficulty 2, assisted by Engines + Security, needs Reserve Power) and **Decloak** (Minor). While cloaked the ship has the *Cloaked* trait and its Shields drop to 0 and can't be raised. If it tries to Fire, Ram or use the Tractor Beam, the app offers to decloak it first (a Minor Action); its shields stay down until it uses Prepare. Enemies must **Reveal** it (Reason + Science, Difficulty 3) before they can target it, or the GM overrides. After that, the Cloaked trait still adds **+1 Difficulty** until End Round. |
| **Extensive Shuttlebays** | Small Craft Readiness = Scale − 1, supports craft up to Scale 2 (runabouts). Comes with a deployed-craft tracker |
| **Rapid-Fire Torpedo Launcher** | A torpedo salvo gets +1 Damage automatically, plus a reminder that Tactical may re-roll 1d20. In auto-roll mode the re-roll is done for you |
| **Fast Targeting Systems** | Targeting Solution gives **both** the d20 re-roll **and** the choice of system hit |
| **Advanced Sensor Suites** | When the ship assists a Sensors task it rolls 2d20 instead of 1d20, unless Sensors has breaches |
| **Experimental Vessel / Prototype** | The ship's assist dice cause a complication on 18–20 |
| **Abundant Personnel** | Doubles the Crew Support pool (Scale × 2). Comes with a used / available tracker |
| **Point Defense System** | While active (a toggle in Target Status), torpedo attacks against the ship are +1 Difficulty (Cover) |
| **Secondary Reactors** | After a Reroute Power action, a prompt offers **2 Momentum (Immediate) to restore Reserve Power**, once per scene. There's also a context button in Action Options. *Combat → New Scene* resets it |
| **Rugged Design** | Damage Control re-rolls a failed d20. On success you're offered a second breach patch for 2 Momentum |
| **Backup EPS Conduits, Improved Damage Control** | Reminders that pop up during Reroute Power, power loss (*Losing Power!*) and Damage Control |
| **Electronic Warfare Systems, Reduced Sensor Silhouette, Emergency Medical Hologram, Specialized Shuttlebay** | Reminder text in the alerts panel |

The **Active Quality & Talent Alerts** panel lists the attacker's and target's talents
with their live state, for example "Rapid-Fire ACTIVE on this salvo", "Advanced
Sensor Suites SUPPRESSED (Sensors breached)", "Point Defense ACTIVE" or "CLOAKED".
It also lists every quality of the weapon in use.

## Other rules automation

* **Turn budget:** each Major Action uses one of the ship's turns. You get a warning
  when a ship goes past its Scale. If an NPC ship uses the same system twice in a
  round, you're asked to spend 1 Threat (or to override, or to cancel).
* **End Round:** advances the Round counter by 1. It applies Persistent damage and
  resets turn counters and the per-round effects: Modulate Shields +2 Resistance,
  Evasive Action, Defensive Fire, Attack Pattern, Jammed, Slowed, Shaken, and a
  cloaked ship's Revealed status. Then it logs `--- END OF ROUND X ---`.
* **Crew Quality** sets the NPC crew's Attribute / Department: Basic 8/1,
  Proficient 9/2, Talented 10/3, Exceptional 11/4.
* **Difficulty** = Base + Weapon modifiers (Cumbersome +1) + context + GM Modifier.
  Context covers:
  * range beyond Close for sensor tasks
  * the ship's own Evasive Action (+1)
  * the target's Attack Pattern (−1)
  * Point Defense (+1 vs torpedoes)
  * a Cloaked target (+1)
  * Shields at 0 for Regenerate Shields
  * Losing Power for Regain Power
  * Jammed for Comms / Sensors tasks
  * Devastating breaches for Damage Control
* **Opposed tasks** (the target used Evasive Action or Defensive Fire): the defender
  rolls first, Daring + Conn or Daring + Security with the ship assisting. Their
  successes **replace the base Difficulty**; every other modifier still applies, and a
  tie goes to the attacker. In auto mode the defender roll is made for you.
* **Dice:** each d20 that rolls ≤ Attribute + Department is a success, and a roll ≤
  the Department (with a Focus) counts double. A 20 is a complication, or 18–20 on
  Experimental ship dice. Assist dice count only if the crew scored a success.
  Re-roll effects (Targeting Solution, Calibrated Sensors, Rapid-Fire, Rugged Design)
  re-roll the worst *failed* crew die. Bonus dice cost 1 / 2 / 3 Momentum (Threat
  for NPCs). Excess successes go to Momentum for player ships and to Threat for NPC
  ships.
* **Costs:** Direct costs 1 Momentum (NPC: 1 Threat). A torpedo adds 1 Threat when a
  player ship fires it, or 3 for a salvo; NPC ships spend Threat instead. When a
  player ship doesn't have enough Momentum, the shortfall is added to Threat.
* **Shields:** lowered shields count as 0. The previous value comes back when the
  shields are raised with Prepare or the Target Status toggle.
* **Damage:** Resistance (with talent bonuses) is deducted unless the attack is
  Piercing. If Shields drop below 50% or below 25%, the Shaken Resolver opens. In it
  you can pick a result from the Minor Damage table or click **Auto-Roll d20**; a
  19–20 re-rolls automatically. A breach is triggered when Shields hit 0, when a ship
  is hit at 0 Shields, or when Shields drop below 25% after the ship was already
  Shaken by the same attack. Each breach rolls on the System Hit table, or you pick
  the system when Targeting Solution allows it.
* **System Hit table:** the default is the d12 table you specified (1–2 Comms …
  11–12 Weapons). A weighted d20 table (1 Comms, 2 Computers, 3–6 Engines, 7–9
  Sensors, 10–17 Structure, 18–20 Weapons) can be selected in the System Hit
  Generator, and the choice is saved with the roster.
* **Weapon qualities:** automated where the rule is mechanical:
  * Cumbersome, Piercing
  * Intense / Depleting (1 Momentum per +1 damage)
  * Spread (Devastating Attack costs 1)
  * High Yield (+1 breach)
  * Devastating (+1 Damage Control Difficulty)
  * Dampening (drains Reserve Power)
  * Jamming, Slowing
  * Versatile X (+X Momentum)
  * **Persistent**: after a hit, the attacker may spend 1–3 Momentum. The target then
    takes half the weapon's damage (rounded up) at each End Round for that many
    rounds, with Resistance applying unless the original hit was Piercing.

  Area, Calibration and Hidden X appear as reminders only.

### Calls I made where the spec was silent

A background research pass checked the less-documented talents against public
sources. Most 2e talent text isn't freely available online, so where your spec
defines a mechanic, the app follows the spec. The calls below are easy to change in
`main.py`:

* **From research:** Cloak as a Tactical Major task; the +1 Difficulty for attacking
  a revealed cloaked ship; 2e Persistent; 2e opposed tasks; Secondary Reactors; and
  Rugged Design's re-roll plus second patch.
* **Unconfirmed online:** the exact 2e text for Backup EPS Conduits, Improved Damage
  Control, Electronic Warfare Systems, Reduced Sensor Silhouette, Emergency Medical
  Hologram and Specialized Shuttlebay. These are reminders, not automation.
* **Reveal** lasts until End Round. **Crew Support** and small craft refill with
  *Combat → New Adventure*.
* **Bonus damage** costs 2 Momentum per +1. **Devastating Attack** costs 2 Momentum
  and adds one extra system hit / breach.
* **Ram:** the suggested collision damage is the other ship's Scale, and you can
  edit it.
* **Breaches** don't change task Difficulty automatically. You get an alert, and you
  apply any penalty your table uses through the GM Modifier.

## Tests

```bash
python -m unittest discover -s tests
```

These tests cover the rules engine: damage thresholds, dice, Difficulty, talent
effects, cloaking, both system hit tables, save-file parsing including the v1
migration, and the generator. No window opens.

---
*Unofficial fan tool. Star Trek Adventures is published by Modiphius Entertainment.*
