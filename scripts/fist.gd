extends Area2D

signal hit_absorbable(absorbable: Node, color: Color)

@export var rest_position: Vector2 = Vector2.ZERO
@export var extend_distance: float = 180.0
@export var extend_speed: float = 1400.0
@export var return_speed: float = 900.0
@export var hold_time: float = 0.06

enum State { REST, EXTENDING, HOLD, RETURNING }

@onready var _visual: Polygon2D = $Visual

var _state: State = State.REST
var _facing: float = 1.0
var _extension: float = 0.0
var _hold_timer: float = 0.0


func _ready() -> void:
	position = rest_position
	area_entered.connect(_on_area_entered)


func launch(facing: float) -> void:
	if _state != State.REST:
		return
	_facing = facing
	_state = State.EXTENDING


func set_visual_color(c: Color) -> void:
	_visual.color = c


func _process(delta: float) -> void:
	match _state:
		State.EXTENDING:
			_extension = minf(_extension + extend_speed * delta, extend_distance)
			if _extension >= extend_distance:
				_state = State.HOLD
				_hold_timer = hold_time
		State.HOLD:
			_hold_timer -= delta
			if _hold_timer <= 0.0:
				_state = State.RETURNING
		State.RETURNING:
			_extension = maxf(_extension - return_speed * delta, 0.0)
			if _extension <= 0.0:
				_state = State.REST

	position = rest_position + Vector2(_extension * _facing, 0.0)


func _on_area_entered(area: Area2D) -> void:
	if _state != State.EXTENDING and _state != State.HOLD:
		return
	if not area.has_method("absorb") or not area.get("can_be_absorbed"):
		return
	var absorbed_color: Color = area.capsule_color
	_visual.color = absorbed_color
	hit_absorbable.emit(area, absorbed_color)
	area.absorb()
	_state = State.RETURNING
