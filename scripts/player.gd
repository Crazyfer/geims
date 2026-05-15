extends CharacterBody2D

const SPEED: float = 220.0
const JUMP_VELOCITY: float = -450.0
const GRAVITY: float = 1200.0

@onready var _interaction_area: Area2D = $InteractionArea
@onready var _visual: Polygon2D = $Visual

var _absorb_lock: bool = false


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += GRAVITY * delta

	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	var direction: float = Input.get_axis("move_left", "move_right")
	velocity.x = direction * SPEED

	move_and_slide()

	if Input.is_action_just_pressed("interact"):
		_try_absorb()


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
	var tween := create_tween()
	tween.tween_property(_visual, "scale", Vector2(1.15, 0.85), 0.08)
	tween.tween_property(_visual, "scale", Vector2(1.0, 1.0), 0.12)
	tween.tween_callback(func() -> void: _absorb_lock = false)
