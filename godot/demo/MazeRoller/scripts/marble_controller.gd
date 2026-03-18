
extends RigidBody3D

@export var torque_strength := 18.0
@export var max_angular_speed := 14.0
var spawn_position := Vector3.ZERO

func _ready() -> void:
	spawn_position = global_position
	add_to_group("player")

func _physics_process(delta: float) -> void:
	var input_vec := Vector2(
		Input.get_action_strength("move_right") - Input.get_action_strength("move_left"),
		Input.get_action_strength("move_backward") - Input.get_action_strength("move_forward")
	)
	if input_vec.length() > 0.01:
		var torque := Vector3(input_vec.y, 0.0, -input_vec.x) * torque_strength * delta * 60.0
		apply_torque_impulse(torque)
		angular_velocity = angular_velocity.limit_length(max_angular_speed)

	if Input.is_action_just_pressed("restart"):
		reset_to_spawn()

func reset_to_spawn() -> void:
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO
	global_position = spawn_position + Vector3(0, 0.2, 0)
