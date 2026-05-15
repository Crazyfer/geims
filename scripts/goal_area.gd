extends Area2D

signal goal_reached(player: Node)


func _ready() -> void:
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player"):
		goal_reached.emit(body)
