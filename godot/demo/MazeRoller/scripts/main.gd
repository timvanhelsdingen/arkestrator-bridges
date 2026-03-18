
extends Node3D

@onready var marble: RigidBody3D = $Marble
@onready var goal: Area3D = $Goal
@onready var cam: Camera3D = $Camera3D
@onready var win_label: Label = $UI/WinLabel

var won := false
var cam_offset := Vector3(0.0, 10.0, 10.0)

func _ready() -> void:
	if goal != null:
		goal.body_entered.connect(_on_goal_body_entered)
	if win_label != null:
		win_label.visible = false

func _physics_process(_delta: float) -> void:
	if marble != null:
		var target := marble.global_position
		var desired := target + cam_offset
		cam.global_position = cam.global_position.lerp(desired, 0.08)
		cam.look_at(target, Vector3.UP)

	if Input.is_action_just_pressed("restart"):
		_restart()

func _on_goal_body_entered(body: Node) -> void:
	if won:
		return
	if body == marble:
		won = true
		win_label.text = "You Win! Press R to restart"
		win_label.visible = true

func _restart() -> void:
	won = false
	if win_label != null:
		win_label.visible = false
	if marble != null and marble.has_method("reset_to_spawn"):
		marble.call("reset_to_spawn")
