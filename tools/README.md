# test harness

Headless test harness that drives the Godot game with scripted inputs.
Two equivalent orchestrators are provided: `run_tests.py` (Python) and
`run_tests.ps1` (PowerShell, for Windows without Python).

## How it works

1. `tools/run_tests.py` iterates over every `*.json` under `tests/scenarios/`.
2. For each scenario it spawns:
   ```
   <godot> --headless --path <project> res://tests/test_runner.tscn -- --scenario res://tests/scenarios/<file>.json
   ```
3. `tests/test_runner.gd` instantiates `PrototypeScene`, replays the scenario's
   timed `actions` via `Input.action_press` / `Input.action_release`, and
   evaluates each `assertion` against a small whitelist of game properties
   (player position, velocity, jumps_used, combo_count, `GameState.consumed_objects`,
   etc.).
4. Godot exits 0 on full PASS, 1 otherwise. Python aggregates a summary.

## Pointing the harness at Godot

Set `GODOT_BIN` to the absolute path of the Godot 4 executable, or put it on PATH.

```powershell
$env:GODOT_BIN = "C:\Tools\Godot_v4.6-stable_win64.exe"
python tools/run_tests.py
```

## Running

Python (cross-platform):
```
python tools/run_tests.py                # all scenarios
python tools/run_tests.py --scenario smoke
python tools/run_tests.py -v             # full Godot stdout for each run
```

PowerShell (Windows):
```powershell
.\tools\run_tests.ps1
.\tools\run_tests.ps1 -Scenario double_jump
.\tools\run_tests.ps1 -ShowFull
```

## Scenario format

```json
{
  "description": "what this exercises",
  "max_duration": 5.0,
  "actions": [
    {"at": 0.4, "action": "move_right", "press": true},
    {"at": 1.8, "action": "move_right", "press": false},
    {"at": 2.0, "action": "interact",   "duration": 0.05}
  ],
  "assertions": [
    {"at": 3.5, "property": "GameState.consumed_objects", "op": "==", "expected": 1}
  ]
}
```

- `action` must be one of the registered input actions (`move_left`, `move_right`,
  `jump`, `interact`, `throw_fists`).
- An action with `duration` is auto-released after that many seconds; otherwise
  use explicit `{"press": true}` / `{"press": false}` pairs.
- `op` is one of `==`, `!=`, `>`, `<`, `>=`, `<=`.
- `property` must be in the whitelist in `tests/test_runner.gd::_read_property`.
  Extend that match block if you need to assert on something new.
