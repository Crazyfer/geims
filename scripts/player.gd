extends CharacterBody2D

const SPEED: float = 220.0
const JUMP_VELOCITY: float = -450.0
const GRAVITY: float = 1200.0
const MAX_JUMPS: int = 2
const DOUBLE_JUMP_FACTOR: float = 0.9
const COMBO_WINDOW: float = 0.8
const COMBO_FINISHER_DISTANCE: float = 280.0
const COMBO_FINISHER_EVERY: int = 3

enum State { IDLE, RUN, JUMP, FALL }

signal combo_changed(count: int)

@onready var _interaction_area: Area2D = $InteractionArea
@onready var _visual: Polygon2D = $Visual
@onready var _fists: Array[Node] = [$Fists/FistLeft, $Fists/FistRight]
@onready var _fist_visuals: Array[Polygon2D] = [$Fists/FistLeft/Visual, $Fists/FistRight/Visual]

var _state: State = State.IDLE
var _facing: float = 1.0
var _was_on_floor: bool = true
var _absorb_lock: bool = false
var _land_squash: float = 0.0
var _jumps_used: int = 0
var _combo_count: int = 0
var _combo_timer: float = 0.0


func _ready() -> void:
	for fist in _fists:
		fist.hit_absorbable.connect(_on_fist_hit)


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += GRAVITY * delta

	if Input.is_action_just_pressed("jump") and _jumps_used < MAX_JUMPS:
		var v: float = JUMP_VELOCITY if _jumps_used == 0 else JUMP_VELOCITY * DOUBLE_JUMP_FACTOR
		velocity.y = v
		_jumps_used += 1

	var direction: float = Input.get_axis("move_left", "move_right")
	velocity.x = direction * SPEED

	move_and_slide()

	if direction != 0.0:
		_facing = sign(direction)

	var on_floor: bool = is_on_floor()
	if on_floor and not _was_on_floor:
		_land_squash = 1.0
		_jumps_used = 0
	_was_on_floor = on_floor

	if not on_floor:
		_state = State.JUMP if velocity.y < 0.0 else State.FALL
	elif absf(velocity.x) > 1.0:
		_state = State.RUN
	else:
		_state = State.IDLE

	if _combo_timer > 0.0:
		_combo_timer -= delta
		if _combo_timer <= 0.0 and _combo_count > 0:
			_combo_count = 0
			combo_changed.emit(_combo_count)

	if Input.is_action_just_pressed("interact"):
		_try_absorb()

	if Input.is_action_just_pressed("throw_fists"):
		_try_throw_punch()

	_update_visual(delta)


func _try_throw_punch() -> void:
	var prospective_combo: int = _combo_count + 1
	var is_finisher: bool = prospective_combo % COMBO_FINISHER_EVERY == 0
	var distance: float = COMBO_FINISHER_DISTANCE if is_finisher else -1.0

	var launched: bool = false
	for fist in _fists:
		if fist.launch(_facing, distance):
			launched = true

	if not launched:
		return

	_combo_count = prospective_combo
	_combo_timer = COMBO_WINDOW
	combo_changed.emit(_combo_count)


func _try_absorb() -> void:
	if _absorb_lock:
		return
	var target: Node = _interaction_area.current_target
	if target == null or not target.has_method("absorb"):
		return
	var absorbed_color: Color = target.capsule_color
	_absorb_lock = true
	_play_absorb_animation()
	target.absorb()
	_tint_to(absorbed_color)


func _on_fist_hit(_absorbable: Node, color: Color) -> void:
	_tint_to(color)


func _tint_to(color: Color) -> void:
	var tween: Tween = create_tween()
	tween.set_parallel(true)
	tween.tween_property(_visual, "color", color, 0.4)
	for fv in _fist_visuals:
		tween.tween_property(fv, "color", color, 0.4)


func _play_absorb_animation() -> void:
	var tween: Tween = create_tween()
	tween.tween_property(_visual, "scale", Vector2(1.2 * _facing, 0.82), 0.08)
	tween.tween_property(_visual, "scale", Vector2(1.0 * _facing, 1.0), 0.12)
	tween.tween_callback(func() -> void: _absorb_lock = false)


func _update_visual(delta: float) -> void:
	if _absorb_lock:
		return

	var target_scale: Vector2 = Vector2(1.0, 1.0)

	match _state:
		State.IDLE:
			var bob: float = sin(Time.get_ticks_msec() / 280.0) * 0.02
			target_scale = Vector2(1.0, 1.0 + bob)
		State.RUN:
			var wob: float = sin(Time.get_ticks_msec() / 90.0) * 0.04
			target_scale = Vector2(1.0 - wob, 1.0 + wob)
		State.JUMP:
			target_scale = Vector2(0.88, 1.18)
		State.FALL:
			target_scale = Vector2(1.06, 0.94)

	if _land_squash > 0.0:
		target_scale = target_scale.lerp(Vector2(1.2, 0.8), _land_squash)
		_land_squash = maxf(0.0, _land_squash - delta * 6.0)

	target_scale.x *= _facing
	_visual.scale = _visual.scale.lerp(target_scale, clampf(delta * 18.0, 0.0, 1.0))
