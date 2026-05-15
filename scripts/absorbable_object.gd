extends Area2D

signal absorption_started
signal absorption_finished
signal object_consumed

@export var can_be_absorbed: bool = true
@export var fade_duration: float = 0.6
@export var capsule_color: Color = Color(0.3, 0.85, 0.4, 1.0)

@onready var _visual: Polygon2D = $Visual

var _absorbing: bool = false


func _ready() -> void:
	_visual.color = capsule_color


func absorb() -> void:
	if not can_be_absorbed or _absorbing:
		return
	_absorbing = true
	can_be_absorbed = false
	absorption_started.emit()
	var tween := create_tween()
	tween.tween_property(_visual, "modulate:a", 0.0, fade_duration)
	tween.parallel().tween_property(_visual, "scale", Vector2(0.6, 0.6), fade_duration)
	tween.tween_callback(_on_fade_complete)


func _on_fade_complete() -> void:
	absorption_finished.emit()
	GameState.register_consumption()
	object_consumed.emit()
	queue_free()
