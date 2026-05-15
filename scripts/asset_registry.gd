extends Node

# Autoload. Reads data/object_registry.json and serves lookups for sprite
# paths and metadata by object UID. The Discord agent writes to the JSON;
# game code reads through this singleton.

const REGISTRY_PATH: String = "res://data/object_registry.json"

var _entries: Dictionary = {}


func _ready() -> void:
	reload()


func reload() -> void:
	_entries = {}
	var f := FileAccess.open(REGISTRY_PATH, FileAccess.READ)
	if f == null:
		push_warning("asset_registry: %s not found" % REGISTRY_PATH)
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if typeof(data) != TYPE_DICTIONARY:
		push_warning("asset_registry: registry root is not an object")
		return
	_entries = data


func has(uid: String) -> bool:
	return _entries.has(uid)


func get_entry(uid: String) -> Dictionary:
	return _entries.get(uid, {})


func get_metadata(uid: String) -> Dictionary:
	return get_entry(uid).get("metadata", {})


# Returns "" if not registered.
func get_sprite(uid: String, animation: String = "default") -> String:
	var sprites: Dictionary = get_entry(uid).get("sprites", {})
	return sprites.get(animation, "")


# Load and return the Texture2D for a uid+animation, or null if absent.
func load_sprite(uid: String, animation: String = "default") -> Texture2D:
	var path: String = get_sprite(uid, animation)
	if path == "":
		return null
	if not ResourceLoader.exists(path):
		push_warning("asset_registry: sprite path missing on disk: %s" % path)
		return null
	return load(path)


# Apply the registered sprite (if any) to a Sprite2D child of `node`.
# Looks for $Sprite2D by default; pass a different name as needed.
func apply_sprite(node: Node, uid: String, animation: String = "default", child_name: String = "Sprite2D") -> bool:
	var tex: Texture2D = load_sprite(uid, animation)
	if tex == null:
		return false
	var sprite: Node = node.get_node_or_null(child_name)
	if sprite == null or not (sprite is Sprite2D):
		return false
	(sprite as Sprite2D).texture = tex
	return true


func all_uids() -> Array:
	return _entries.keys()
