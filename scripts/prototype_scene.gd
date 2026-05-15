extends Node2D

@onready var _consumed_label: Label = $HUD/ConsumedLabel
@onready var _ending_panel: ColorRect = $HUD/EndingPanel
@onready var _ending_label: Label = $HUD/EndingPanel/EndingLabel
@onready var _goal: Area2D = $Goal

var _ended: bool = false


func _ready() -> void:
	GameState.reset()
	GameState.consumed_changed.connect(_on_consumed_changed)
	_goal.goal_reached.connect(_on_goal_reached)
	_ending_panel.visible = false
	_consumed_label.text = "Consumed: 0"


func _on_consumed_changed(count: int) -> void:
	_consumed_label.text = "Consumed: %d" % count


func _on_goal_reached(_player: Node) -> void:
	if _ended:
		return
	_ended = true
	if GameState.consumed_objects == 0:
		_ending_label.text = "Completaste la escena sin consumir colores.\nRuta pacifista desbloqueada.\n\nPress R to retry."
	else:
		_ending_label.text = "Scene complete.\nConsumed: %d\n\nPress R to retry." % GameState.consumed_objects
	_ending_panel.visible = true


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_R:
		get_tree().reload_current_scene()
