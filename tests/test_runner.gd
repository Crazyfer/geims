extends Node

# Drives a scripted scenario against a live PrototypeScene.
# Scenario JSON shape:
#   { "description": "...",
#     "max_duration": 10.0,
#     "actions":    [ {"at": 0.5, "action": "move_right", "press": true},
#                     {"at": 0.7, "action": "interact",   "duration": 0.05} ],
#     "assertions": [ {"at": 1.0, "property": "GameState.consumed_objects",
#                                 "op": "==", "expected": 1} ] }

const DEFAULT_SCENARIO: String = "res://tests/scenarios/smoke.json"
const PROTOTYPE_SCENE: PackedScene = preload("res://scenes/PrototypeScene.tscn")

var _scenario: Dictionary = {}
var _actions: Array = []
var _assertions: Array = []
var _time: float = 0.0
var _next_action: int = 0
var _next_assertion: int = 0
var _results: Array = []
var _max_duration: float = 10.0
var _scenario_path: String = ""
var _prototype: Node = null
var _player: Node = null


func _ready() -> void:
	_scenario_path = _get_scenario_arg()
	if _scenario_path == "":
		_scenario_path = DEFAULT_SCENARIO

	if not _load_scenario(_scenario_path):
		_emit("error", "could_not_load", _scenario_path)
		_quit(2)
		return

	_max_duration = float(_scenario.get("max_duration", 10.0))

	_prototype = PROTOTYPE_SCENE.instantiate()
	get_parent().add_child.call_deferred(_prototype)
	_player = _prototype.get_node_or_null("Player")
	if _player == null:
		_emit("error", "no_player_found", _scenario_path)
		_quit(2)
		return

	_emit("start", _scenario.get("description", ""), _scenario_path)


func _physics_process(delta: float) -> void:
	_time += delta

	while _next_action < _actions.size() and float(_actions[_next_action]["at"]) <= _time:
		_execute_action(_actions[_next_action])
		_next_action += 1

	while _next_assertion < _assertions.size() and float(_assertions[_next_assertion]["at"]) <= _time:
		_check_assertion(_assertions[_next_assertion])
		_next_assertion += 1

	var done: bool = _next_action >= _actions.size() and _next_assertion >= _assertions.size()
	if done or _time > _max_duration:
		_finish(_time > _max_duration)


func _execute_action(a: Dictionary) -> void:
	var action_name: String = String(a["action"])
	if a.has("duration"):
		Input.action_press(action_name)
		var d: float = float(a["duration"])
		get_tree().create_timer(d).timeout.connect(
			func() -> void: Input.action_release(action_name)
		)
		_emit("action", "tap", "%s %.3fs" % [action_name, d])
	else:
		var press: bool = bool(a.get("press", true))
		if press:
			Input.action_press(action_name)
		else:
			Input.action_release(action_name)
		_emit("action", "press" if press else "release", action_name)


func _check_assertion(a: Dictionary) -> void:
	var prop: String = String(a["property"])
	var op: String = String(a.get("op", "=="))
	var expected: Variant = a["expected"]
	var actual: Variant = _read_property(prop)
	var passed: bool = _compare(actual, op, expected)
	_results.append({
		"property": prop, "op": op, "expected": expected,
		"actual": actual, "passed": passed,
	})
	var status: String = "PASS" if passed else "FAIL"
	_emit("assert", status, "%s %s %s | actual=%s" % [prop, op, str(expected), str(actual)])


func _read_property(path: String) -> Variant:
	match path:
		"GameState.consumed_objects": return GameState.consumed_objects
		"Player.position.x": return _player.position.x
		"Player.position.y": return _player.position.y
		"Player.velocity.x": return _player.velocity.x
		"Player.velocity.y": return _player.velocity.y
		"Player.is_on_floor": return _player.is_on_floor()
		"Player.combo_count": return _player.get("_combo_count")
		"Player.jumps_used": return _player.get("_jumps_used")
		"Player.facing": return _player.get("_facing")
	push_warning("test_runner: unknown property " + path)
	return null


func _compare(actual: Variant, op: String, expected: Variant) -> bool:
	match op:
		"==": return actual == expected
		"!=": return actual != expected
		">":  return actual > expected
		"<":  return actual < expected
		">=": return actual >= expected
		"<=": return actual <= expected
	return false


func _finish(timed_out: bool) -> void:
	var total: int = _results.size()
	var passed: int = _results.filter(func(r: Dictionary) -> bool: return r.passed).size()
	var failed_specs: Array = _results.filter(func(r: Dictionary) -> bool: return not r.passed)
	var status: String = "TIMEOUT" if timed_out else ("PASS" if passed == total and total > 0 else ("EMPTY" if total == 0 else "FAIL"))
	_emit("summary", status, "%d/%d" % [passed, total])
	for f in failed_specs:
		_emit("fail_detail", "", "%s %s %s actual=%s" % [f.property, f.op, str(f.expected), str(f.actual)])
	var exit_code: int = 0 if status == "PASS" else 1
	_quit(exit_code)


func _emit(kind: String, status: String, info: String) -> void:
	print("[TEST] t=%.3f %s %s %s" % [_time, kind, status, info])


func _quit(code: int) -> void:
	get_tree().quit(code)


func _load_scenario(path: String) -> bool:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return false
	var text: String = f.get_as_text()
	var data: Variant = JSON.parse_string(text)
	if typeof(data) != TYPE_DICTIONARY:
		return false
	_scenario = data
	_actions = _scenario.get("actions", [])
	_assertions = _scenario.get("assertions", [])
	return true


func _get_scenario_arg() -> String:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	for i in args.size():
		if args[i] == "--scenario" and i + 1 < args.size():
			return args[i + 1]
	return ""
