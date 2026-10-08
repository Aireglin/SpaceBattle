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
* **Save Roster to JSON** and **Load Roster from JSON** are in the *Fleet & Roster*
  tab and in the File menu, with `Ctrl+S` as a shortcut. A save stores every ship's full combat
  state (shields, breaches with their Nature of Breach, talents, cloak, effects, turns
  used) plus Round, Threat, Momentum, GM Modifier, the system hit table, the Scene
  Traits and the Attacker / Target selection.
* The File menu also has: *Save Roster As…*, *Load Roster From File…*,
  *Import Ship(s)…* (accepts a roster file, a ship export, a list of ships or a
  single ship), *Export Selected Ship…*, *Export Combat Log…* and *Reset Roster to
  Presets*.
* Rosters saved by the first version of the app (format 1) still load. Their Shields
  and Resistance totals become the ships' base values. A ship saved with its shields
  lowered keeps that value in reserve (it counts as 0 until raised). Old Persistent
  effects become one End Round tick that still ignores Resistance.
* Hand-edited files are checked on load: text booleans such as `"false"`, negative or
  oversized counters, and unknown hit tables are corrected. A file that can't be used
  at all leaves the current roster untouched (at startup, the presets load instead).
* If the roster has unsaved changes, the app asks whether to save before it exits.

## Screen layout

The window has a **global header** that is always visible, and three tabs that follow
the game flow. Switch tabs with a click, the **View** menu or `Ctrl+1` / `Ctrl+2` /
`Ctrl+3`.

**Header (all tabs):** Threat and Momentum counters with − / + (Momentum is capped at
6), the Round counter with **END ROUND** and **END SCENE**, the GM Modifier spinbox
(−3…+5) and the roster file name, which flags unsaved changes. The **Combat** menu
has End Round, *End Scene / Reset Scene* and *New Adventure*.

### Tab 1 – Combat Dashboard (the GM's view during turns)

| Column | Contents |
|---|---|
| **Step 1 · Active Combatants** | Attacker / Target dropdowns with **Swap**. The **Active Attacker** card shows name, class, Scale, crew, shield bar, Shields and Resistance (talent bonuses broken out), **Turns used / Scale** with +1 / −1 / Reset, systems used this round, a **Reserve Power** toggle, the **Cloak** button, Crew Support and Small Craft trackers, and *Show ship details* for the full stat block. **Target Quick Status** shows the target's shield bar with the 50% / 25% markers, Resistance, its **breaches** (with Nature of Breach), effects, quick shield buttons (−1 / +1 / Set / Reset), and toggles for Reserve Power, shields, weapons, Point Defense and cloak. Below them sit the target's **Complications** and the **Scene Traits**. |
| **Step 2 · Action & Rule Guidance** | **Station → Action** selector with the Major / Minor / Free badge and a red **breach warning box**. **Action Parameters** shows only the options that apply to the chosen action: weapon, torpedo salvo, range, Targeting Solution, Scan for Weakness, Regenerate Shields, Secondary Reactors, Override, Other Task base Difficulty. The **Difficulty** box shows the breakdown `Base + Weapon Mods + Context + GM Mod = Final Difficulty`. The **Rule Hint Card** gives the Attribute + Department TN, ship-assist TN, critical range, rule text and warnings, with the active talent and weapon-quality reminders underneath. **Roll & Resolve** has crew ratings, Focus, dice pool, ship assist, auto-roll or manual successes, and opposed defender successes. |
| **Step 3 · Damage & Breach Resolution** | The **Tactical Combat Resolver**: pending hit, weapon, base damage rating, extra damage bought with Momentum, Piercing and Devastating Attack, a live preview and **APPLY DAMAGE TO TARGET**. The **System Hit & Breach Roller**: *Roll System Hit* with the table's distribution shown, *Add Breach There*, **Roll Nature of Breach (d20)** and the **Breach Manager** (breaches, Nature of Breach per system, *→ Offline*). The **Shaken Handler**: the target's thresholds and Shaken state (detected automatically when damage is applied), plus the Shaken Resolver with Auto-Roll d20 or a manual choice. |
| **Combat Log** (bottom) | Scrollable, colour-coded log with highlighted `=== ROUND n ===` / `END OF ROUND` separators |

### Tab 2 – Fleet & Roster

A **summary table** of every ship in the scene: role (A = attacker,
blue row; T = target, red row), name, side, class, Scale, Shields, Resistance, breach
count, turns used and a status column (Shaken, cloak, lowered shields, breach
conditions, missing Reserve Power and so on). Double-clicking a row makes it the
Attacker. Below the table are **Set as Attacker / Set as Target / Swap**, **New Ship…**,
**Edit in Ship Creator**, **Duplicate**, **Delete** and **Full Repair**. On the right:
**Save / Load Roster to/from JSON**, *Save As…*, *Load From File…*, *Reset Roster to
Presets*, **Import Ship(s)…** / **Export Selected Ship…**, and the full details of the
selected ship.

### Tab 3 – Ship Creator & Generator

* **NPC Quick Generator** (left): name, Scale, Crew Quality, *Spaceframe Profile*
  (Balanced, Warship, …) and the Starship Talents multi-select. **Generate NPC →
  Roster** adds the ship straight away. **Generate into Ship Creator** opens it in the
  creator so you can tweak it before saving. *Edit a roster ship* loads any roster ship
  into the creator.
* **Custom Ship Creator** (middle): name, spaceframe / class, side, Scale, Crew
  Quality, base Shields and Resistance (with *Auto-calc*), Tractor Beam, systems,
  departments, the **talents and special rules multi-select** (custom talents work as
  reminders) and notes. A live line shows the effective Shields, Resistance, Tractor
  and Small Craft values once talents are applied. **Save Changes** / **Save to
  Roster** and **Save as New Ship** sit at the top.
* **Weapons & Auto-Calculator** (right): the ship's weapon list and an inline weapon
  form with the calculator (see below). Select a weapon to load it into the form, then
  **Update Selected Weapon**, or use **Add as New Weapon** / **Remove Selected** /
  **Recalc Damage**.
* The creator works on a copy. Saving writes your changes onto the **live** roster
  ship, so damage, breaches and turns it took while you were editing are kept. A
  rename carries over to the Attacker / Target selection. Unsaved creator edits are
  marked with `*` on the tab and `● unsaved edits`, and so is a weapon that is still
  in the weapon form but not added or updated. The app asks before discarding them
  (loading another ship, *New Blank Ship*, or exiting). When you save the ship with a
  weapon still in the form, it asks whether to add or update that weapon first.
* After *Load Roster* or *Reset to Presets*, the creator reloads the ship it was
  editing. If it held unsaved edits, they are kept as an unlinked copy that *Save*
  adds as a new ship, so a freshly loaded ship is never overwritten.

## Weapon Auto-Calculator

The weapon form in the Ship Creator tab has an **Auto-Calculate Weapon Stats**
section. It fills in the standard stats from the Core Rulebook weapon tables
(pp. 228–230).

* **Energy weapons** take two selectors, **Energy Type** and **Delivery Method**:

  | Delivery Method | Range | Damage | Qualities |
  |---|---|---|---|
  | Cannon | Close | Scale + 2 | – |
  | Banks | Medium | Scale + 1 | – |
  | Arrays | Medium | Scale | Area or Spread |
  | Spinal Lance | Long | Scale + 3 | Cumbersome |

  | Energy Type | Qualities |
  |---|---|
  | Antiproton Beam | High Yield |
  | Disruptor | Intense |
  | Electromagnetic / Ionic | Dampening, Piercing |
  | Free Electron Laser | – |
  | Graviton Beam | Devastating, Piercing |
  | Phase / Pulse | Versatile 1 |
  | Phased Polaron Beam | Intense, Piercing |
  | Phaser | Versatile 2 |
  | Proton Beam | Persistent |
  | Tetryon Beam | Depleting |

  Once both are picked, the dialog fills in the name (e.g. *Phaser Arrays*,
  *Disruptor Spinal Lance*), the range, the damage and the merged qualities from both
  tables. For example, Phaser Arrays get *Versatile 2, Area or Spread*.
* **Torpedoes** use one **Torpedo Type** selector:

  | Torpedo | Range | Damage | Qualities |
  |---|---|---|---|
  | Chroniton | Long | 3 | Calibration, Slowing |
  | Gravimetric | Long | 5 | Calibration, Cumbersome, High Yield, Piercing |
  | Neutronic | Long | 4 | Calibration, Dampening |
  | Nuclear | Medium | 3 | Calibration, Intense |
  | Photon | Long | 3 | High Yield |
  | Photonic | Long | 2 | High Yield |
  | Plasma | Long | 5 | Calibration, Cumbersome, Persistent |
  | Polaron | Long | 3 | Calibration, Piercing |
  | Positron | Long | 5 | Calibration, Cumbersome, Dampening |
  | Quantum | Long | 4 | Calibration, High Yield, Intense |
  | Spatial | Medium | 2 | – |
  | Tetryonic | Long | 2 | Depleting, High Yield |
  | Transphasic | Long | 4 | Calibration, Devastating, Piercing |
  | Tricobalt | Long | 6 | Area, Calibration, Cumbersome |

* **Weapons System Damage Bonus:** the dialog takes the ship's Scale and Weapons
  rating from the editor (you can change them for a what-if) and shows the bonus:
  Weapons ≤6 +0, 7–8 +1, 9–10 +2, 11–12 +3, 13+ +4. The bonus is added to the Damage
  rating by default, because the app treats a weapon's Damage as its full rating. A
  checkbox turns this off, and that choice is saved with the weapon. The breakdown
  reads like
  `Scale 5 + 0 (Arrays) + 3 (Weapons 11 bonus) = Damage 8`.
* **Everything stays editable:** name, damage, range and every quality. A status
  line shows whether the weapon still *matches the standard values* or is
  *customised*, and what differs (e.g. `Damage 10 (standard 8); qualities edited`).
  **Auto-Populate** re-applies the standard values at any time. With *Auto-fill when
  a selection changes* ticked (the default), picking a different type fills the
  fields straight away; re-picking the same entry changes nothing. Changing Scale,
  Weapons or the bonus box updates the damage only while it still equals the
  standard, so a hand-set damage is kept. Untick auto-fill to change the selectors
  without touching your fields.
* **Linking:** a weapon is linked to the calculator once you pick a type in a
  dropdown or click Auto-Populate. The chosen Energy Type / Delivery Method /
  Torpedo Type and the bonus setting are then saved with the weapon in the roster
  file. A new weapon starts as a custom (unlinked) weapon. When you edit an older
  weapon, the dropdowns are pre-set from a guess based on its name (*Photon
  Torpedoes* → Photon). The guess doesn't link the weapon or change any value.
* **Recalc Damage** in the Ship Creator updates the damage of linked weapons after a
  Scale or Weapons change, using each weapon's own bonus setting. When several
  weapons would change, you can update all of them or confirm weapon by weapon, so a
  hand-set damage can be kept. Range, name and qualities stay as they are. Unlinked
  weapons are listed and left alone.
* **Area or Spread** (Arrays): when the weapon hits, the app asks which of the two
  this attack uses. Spread makes the Devastating Attack cost 1. If you skip the
  question, it is asked again when damage is applied. The ship's weapon keeps *Area
  or Spread* for the next attack.

## Starship talents and special rules

| Talent / rule | What the app does |
|---|---|
| **Ablative Armor** | +2 Resistance, added automatically |
| **Improved Hull Integrity** | +1 Resistance, added automatically |
| **Advanced Shields** | +5 maximum Shields, added automatically |
| **Cloaking Device** | Enables the **Cloak toggle** (Active Attacker card, or *Toggle Target Cloak*) and the Tactical actions **Cloak** (Major: Control + Engineering, Difficulty 2, assisted by Engines + Security, needs Reserve Power) and **Decloak** (Minor). While cloaked the ship has the *Cloaked* trait and its Shields drop to 0 and can't be raised. If it tries to Fire, Ram or use the Tractor Beam, the app offers to decloak it first (a Minor Action); its shields stay down until it uses Prepare. Enemies must **Reveal** it (Reason + Science, Difficulty 3) before they can target it, or the GM overrides. After that, the Cloaked trait still adds **+1 Difficulty** until End Round. |
| **Extensive Shuttlebays** | Small Craft Readiness = Scale − 1, supports craft up to Scale 2 (runabouts). Comes with a deployed-craft tracker |
| **Rapid-Fire Torpedo Launcher** | A torpedo salvo gets +1 Damage automatically, plus a reminder that Tactical may re-roll 1d20. In auto-roll mode the re-roll is done for you |
| **Fast Targeting Systems** | Targeting Solution gives **both** the d20 re-roll **and** the choice of system hit |
| **Advanced Sensor Suites** | When the ship assists a Sensors task it rolls 2d20 instead of 1d20, unless Sensors has breaches |
| **Experimental Vessel / Prototype** | The ship's assist dice cause a complication on 18–20 |
| **Abundant Personnel** | Doubles the Crew Support pool (Scale × 2). Comes with a used / available tracker |
| **Point Defense System** | While active (a toggle in Target Quick Status), torpedo attacks against the ship are +1 Difficulty (Cover) |
| **Secondary Reactors** | During **Reroute Power** (once per scene): a prompt after the action, and a button in Action Parameters, spend **2 Momentum (Immediate) to restore Reserve Power**. END SCENE resets it |
| **Rugged Design** | Damage Control re-rolls a failed d20. On success you're offered a second breach patch for 2 Momentum |
| **Backup EPS Conduits** | When *Losing Power!* (Shaken) would drain the Reserve Power, the app offers a **1d20 roll: on Structure or less the ship keeps its Reserve Power** (and the Regain Power penalty doesn't apply) |
| **I'm Giving It All She's Got!** | Once per scene, while the ship has no Reserve Power: **add 2 Threat** (an NPC ship spends 2 Threat) to regain it. There's a button in the Active Attacker card and under the warning box, and the app offers it when you try a power action |
| **Improved Power Systems** | Regain Power is **1 Difficulty lower** (never below 1) |
| **Improved Damage Control** | Reminder during Damage Control |
| **Electronic Warfare Systems, Reduced Sensor Silhouette, Emergency Medical Hologram, Specialized Shuttlebay** | Reminder text in the alerts panel |

The **Active Quality & Talent Alerts** panel lists the attacker's and target's talents
with their live state, for example "Rapid-Fire ACTIVE on this salvo", "Advanced
Sensor Suites SUPPRESSED (Sensors breached)", "Point Defense ACTIVE" or "CLOAKED".
It also lists every quality of the weapon in use.

## Bridge stations

The Station dropdown has seven entries. Every station lists its Minor actions first,
then its Major actions, and every station has its own **Create Trait** (Major,
Difficulty 2), with the Attribute + Department and ship assist the Rule Hint Card suggests.

| Station | Minor | Major |
|---|---|---|
| **Command** | Change Position, Interact, Prepare, Restore | Direct, Rally, Assist (two allies), Create Trait (Control / Insight / Reason + Command, assisted by Computers + Command) |
| **Conn / Helm** | Impulse, Thrusters | Attack Pattern, Evasive Action, Maneuver, Ram, Warp, Create Trait (Control / Daring + Conn, Engines + Conn) |
| **Tactical** | Prepare, Calibrate Weapons, Targeting Solution, Decloak | Fire, Defensive Fire, Modulate Shields, Tractor Beam, Cloak, Create Trait (Control / Reason + Security, Weapons + Security) |
| **Sensor Operations** | Calibrate Sensors, Launch Probe | Sensor Sweep, Scan for Weakness, Reveal, Create Trait (Reason / Control + Science, Sensors + Science) |
| **Operations / Engineering** | Change Position, Interact, Prepare, Restore | Damage Control, Regenerate Shields, Regain Power, Reroute Power, Transport (Difficulty 1+), Create Trait (Control / Reason + Engineering, Engines + Engineering) |
| **Communications** | Change Position, Interact, Prepare, Restore, plus the **free** actions Send / Respond to Hail and Internal Comms | Damage Control, Transport, Create Trait (Control / Reason + Engineering / Command, Communications + Engineering) |
| **Starship Standard Actions** | Change Position, Interact, Prepare, Restore | Create / Alter Trait, Assist (one ally), Override, Pass, Ready, Other Tasks |

* **Free** actions use neither a turn nor the Minor Action.
* **Create Trait** asks on success whether to create a new trait, alter one or remove
  one. Traits live in the **Scene Traits** list (Step 1 column), which is saved with the
  roster. *Combat → New Scene* offers to clear it.
* **Override** asks which station you control. It switches the selector to that
  station, preselects its first Major Action and ticks the *Override* box, so the task
  you then pick is +1 Difficulty. Override itself uses no extra turn. The box stays
  ticked through Minor and Free actions, clears after the Major Action or task roll,
  and is also cleared when the acting ship changes, at End Round and when a roster is
  loaded.
* **Pass** uses the turn without a Major Action, and is allowed while Bracing for
  Impact. **Ready** records the trigger and the readied action until End Round. When
  that ship next resolves a Major Action, the app asks whether it's the readied
  reaction. If yes, it uses no extra turn (even when the turn budget is spent), skips
  the Brace for Impact prompt and clears the readied action.
* **Prepare** isn't blocked by an Offline subsystem in general. Only the choices that
  need it are: *Weapons: Arm* needs Weapons and *Prepare for Warp* needs Engines (GM
  override possible). Lowering or raising Shields always works.
* **Other Tasks** takes its base Difficulty from the *Other Task base Difficulty*
  box. You set its Attribute and Department in Roll & Resolve.
* The **Rule Hint Card** always shows the Difficulty in the form
  `Base 2 + 1 (Failing breach: Engines) + 1 (GM Modifier) = Total Difficulty 4`. It
  also shows the suggested Attribute + Department and ship assist, plus warnings:
  Restore required, subsystem offline, and Threat spends.

## Nature of Breach

Whenever a breach is inflicted on a ship system, the **Nature of Breach** resolver
opens. That covers weapon hits, Devastating Attack, *Add Breach There* and the
tracker's **+** button. You can click **Auto-Roll d20** or pick the condition from
the dropdown; *Skip* leaves the system's condition unchanged.

| d20 | Condition | Effect in the app |
|---|---|---|
| 1–4 | **Damaged** | Mostly functional. A reminder suggests the GM spend Threat on a complication |
| 5–8 | **Malfunctioning** | Before any task or Major Action that uses the subsystem, a **Restore** minor action is needed that turn. The app offers to take it (or a GM override). A Restore lasts until the ship's turn ends |
| 9–12 | **Primary Offline** (switching to backup) | +1 Difficulty to every task using the subsystem, added automatically |
| 13–16 | **Failing** | +1 Difficulty to every task using the subsystem, added automatically. **Spend 1 Threat → Set Offline** appears below the warning box when the acting ship's chosen action uses the Failing subsystem; the Breach Manager's **→ Offline** button does the same for the target |
| 17–20 | **Offline** | Actions using the subsystem are blocked (GM override only) |

* A task "uses" a subsystem when it's the action's station system or its
  ship-assist system. For example, Fire uses Weapons and Damage Control uses
  Structure.
* Each system keeps its **most severe** condition. A milder new result doesn't
  downgrade it, though the GM can set any condition in the tracker's dropdown.
* The condition clears when the system's last breach is patched, by Damage Control,
  Rugged Design's second patch, the tracker's **−** button or Full Repair.
* Conditions show in the Breach Manager, Target Quick Status, the Fleet table's
  status column, the reminders under the Rule Hint Card (for example "Engines:
  Malfunctioning" or "Sensors: Primary Offline (+1 Diff)") and the red warning box
  in Step 2. **Roll Nature of Breach (d20)** in Step 3 rolls it again for any breached
  target system.

## Other rules automation

* **Turn budget:** each Major Action uses one of the ship's turns. You get a warning
  when a ship goes past its Scale. If a ship uses the same system twice in a round,
  you're asked to pay 1 Threat, or to override, or to cancel. An NPC ship spends the
  Threat; a player ship adds it to the pool.
* **End Round:** advances the Round counter by 1. It applies Persistent damage and
  resets turn counters and the per-round effects: Modulate Shields +2 Resistance,
  Evasive Action, Defensive Fire, Attack Pattern, Jammed, Slowed, Shaken, and a
  cloaked ship's Revealed status. Then it logs `--- END OF ROUND X ---`. It never
  restores Reserve Power.
* **Reserve Power** is a once-per-scene resource (`reserve_power`, also available as
  `has_reserve_power`; every ship starts the scene with it):
  * **Warp**, **Regenerate Shields** and **Reroute Power** (and **Cloak**) need it and
    use it up as soon as the action is resolved, whether or not the task succeeds.
  * Without it, Step 2 shows **⚠ Requires Reserve Power! (Currently Expended)**,
    ROLL & RESOLVE is blocked and no shields are restored. To override as GM, tick
    *Reserve Power* in the Active Attacker card.
  * **Regain Power** (Control + Engineering) starts at **Difficulty 1** and gets
    **+1 for every earlier attempt this scene**, successful or not. *Losing Power!*
    adds +1 more to the next attempt, which uses the penalty up. Success restores
    Reserve Power. The Active Attacker card shows the next attempt's Difficulty.
  * **Losing Power!** (Shaken) and a hit by a **Dampening** weapon drain it.
  * **END SCENE** (header button, or *Combat → End Scene / Reset Scene*) asks for
    confirmation. It then restores Reserve Power for every ship and resets the Regain
    Power attempts, the Losing Power penalty and the once-per-scene talents. Damage,
    breaches and the round counter stay as they are. *New Adventure* does the same.
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
  * earlier attempts this scene and Losing Power for Regain Power (−1 with Improved
    Power Systems, minimum 1)
  * Jammed for Comms / Sensors tasks
  * Devastating breaches for Damage Control
* **Opposed tasks** (the target used Evasive Action or Defensive Fire). The Rule Hint Card
  shows `Defender's successes ? + 1 (GM Modifier) = Total Difficulty ?` until the
  defender has rolled. The defender rolls first, Daring + Conn or Daring + Security
  with the ship assisting. Their
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
  shields are raised with Prepare or the Target Quick Status toggle.
* **Damage:** Resistance (with talent bonuses) is deducted unless the attack is
  Piercing. If Shields drop below 50% or below 25%, the Shaken Resolver opens. In it
  you can pick a result from the Minor Damage table or click **Auto-Roll d20**; a
  19–20 re-rolls automatically. A breach is triggered when Shields hit 0, when a ship
  is hit at 0 Shields, or when Shields drop below 25% after the ship was already
  Shaken by the same attack. A hit that takes Shields to 0 also makes the ship Shaken
  for each threshold it crosses. One hit causes at most one breach from these
  triggers, and High Yield adds one more. Each breach rolls on the System Hit table,
  or you pick the system when Targeting Solution allows it. Every breach gets its own
  Nature of Breach roll, so a High Yield hit opens the resolver twice.
* **System Hit table:** the default is the d12 table you specified (1–2 Comms …
  11–12 Weapons). A weighted d20 table (1 Comms, 2 Computers, 3–6 Engines, 7–9
  Sensors, 10–17 Structure, 18–20 Weapons) can be selected in the System Hit
  Generator, and the choice is saved with the roster.
* **Weapon qualities:** automated where the rule is mechanical:
  * Cumbersome, Piercing
  * Intense / Depleting (1 Momentum per +1 damage)
  * Spread (Devastating Attack costs 1)
  * Area or Spread (the attacker picks one each time the weapon hits)
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
  Hologram and Specialized Shuttlebay. These are reminders, not automation. Backup EPS
  Conduits, I'm Giving It All She's Got! and Improved Power Systems follow your spec.
* **Reveal** lasts until End Round. **Crew Support** and small craft refill with
  *Combat → New Adventure*.
* **Bonus damage** costs 2 Momentum per +1. **Devastating Attack** costs 2 Momentum
  and adds one extra system hit / breach.
* **Ram:** the suggested collision damage is the other ship's Scale, and you can
  edit it.
* **Breaches:** the breach count alone doesn't change task Difficulty. The Nature of
  Breach does: Primary Offline and Failing add +1 automatically (see above). Any other
  penalty your table uses goes through the GM Modifier.
* **Weapons System Damage Bonus bands** (≤6 +0, 7–8 +1, 9–10 +2, 11–12 +3, 13+ +4)
  couldn't be checked online from this environment. They reproduce the preset
  weapons exactly (Phaser Arrays 8, Disruptor Banks 9, Plasma Torpedoes 7). The bands
  are one table, `WEAPONS_DAMAGE_BONUS_TABLE`, in `main.py`.
* The **preset ships are unchanged**. The USS Aurora's Phaser Arrays keep both Area
  and Spread, as before. A weapon built with the calculator gets *Area or Spread*
  and asks at attack time instead.

## Tests

```bash
python -m unittest discover -s tests
```

These tests cover the rules engine: Nature of Breach, station action lists, damage
thresholds, dice, Difficulty, talent
effects, cloaking, both system hit tables, save-file parsing including the v1
migration, and the generator. No window opens.

---
*Unofficial fan tool. Star Trek Adventures is published by Modiphius Entertainment.*
