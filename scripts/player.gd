extends CharacterBody2D

const SPEED: float = 220.0
const JUMP_VELOCITY: float = -450.0
const GRAVITY: float = 1200.0

enum State { IDLE, RUN, JUMP, FALL }

@onready var _interaction_area: Area2D = $InteractionArea
@onready var _visual: Polygon2D = $Visual

var _state: State = State.IDLE
var _facing: float = 1.0
var _was_on_floor: bool = true
var _absorb_lock: bool = false
var _land_squash: float = 0.0


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += GRAVITY * delta

	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	var direction: float = Input.get_axis("move_left", "move_right")
	velocity.x = direction * SPEED

	move_and_slide()

	if direction != 0.0:
		_facing = sign(direction)

	var on_floor: bool = is_on_floor()
	if on_floor and not _was_on_floor:
		_land_squash = 1.0
	_was_on_floor = on_floor

	if not on_floor:
		_state = State.JUMP if velocity.y < 0.0 else State.FALL
	elif absf(velocity.x) > 1.0:
		_state = State.RUN
	else:
		_state = State.IDLE

	if Input.is_action_just_pressed("interact"):
		_try_absorb()

	_update_visual(delta)


func _try_absorb() -> void:
	if _absorb_lock:
		return
	var target: Node = _interaction_area.current_target
	if target == null or not target.has_method("absorb"):
		return
	_absorb_lock = true
	_play_absorb_animation()
	target.absorb()


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
