extends Area2D

# Tracks the nearest absorbable target inside the player's reach.
# Other code (player.gd) reads current_target and triggers absorption.

signal target_changed(target: Node)

var current_target: Node = null


func _ready() -> void:
	area_entered.connect(_on_area_entered)
	area_exited.connect(_on_area_exited)


func _on_area_entered(area: Area2D) -> void:
	if area.has_method("absorb") and area.get("can_be_absorbed"):
		current_target = area
		target_changed.emit(current_target)


func _on_area_exited(area: Area2D) -> void:
	if area == current_target:
		current_target = null
		target_changed.emit(current_target)
