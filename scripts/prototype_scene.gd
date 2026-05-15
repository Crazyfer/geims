extends Node2D

@onready var _consumed_label: Label = $HUD/ConsumedLabel


func _ready() -> void:
	GameState.reset()
	GameState.consumed_changed.connect(_on_consumed_changed)
	_consumed_label.text = "Consumed: 0"


func _on_consumed_changed(count: int) -> void:
	_consumed_label.text = "Consumed: %d" % count
