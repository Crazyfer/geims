extends Node

# Autoload. Tracks pacifist-route state across the scene.

signal consumed_changed(count: int)

var consumed_objects: int = 0


func register_consumption() -> void:
	consumed_objects += 1
	consumed_changed.emit(consumed_objects)


func reset() -> void:
	consumed_objects = 0
	consumed_changed.emit(consumed_objects)
