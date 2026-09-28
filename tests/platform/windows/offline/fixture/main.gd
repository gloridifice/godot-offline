extends Node

var checks: Array[Dictionary] = []
var snapshots: Array[Dictionary] = []
var cancellations: Array = []
var unexpected_dialog_callbacks: int = 0
var marker: ColorRect
var output: String

func check(condition: bool, description: String) -> void:
	checks.append({"pass": condition, "description": description})
	if not condition:
		push_error("ACCEPTANCE: " + description)

func write_json(filename: String, data: Variant) -> void:
	var file := FileAccess.open(output.path_join(filename), FileAccess.WRITE)
	file.store_string(JSON.stringify(data, "\t"))

func frames(count: int = 3) -> void:
	for i in count:
		await RenderingServer.frame_post_draw

func snapshot(label: String) -> void:
	await frames()
	var image := get_viewport().get_texture().get_image()
	check(image != null and not image.is_empty(), label + ": nonempty viewport image")
	if image == null or image.is_empty():
		return
	check(image.save_png(output.path_join(label + ".png")) == OK, label + ": save PNG")
	check(get_window().size.x > 32 and get_window().size.y > 32, label + ": valid client size")
	check(image.get_size() == get_window().size, label + ": image matches client size")
	if image.get_width() > 60 and image.get_height() > 60:
		check(image.get_pixel(60, 60).is_equal_approx(marker.color), label + ": expected marker content")
	snapshots.append({
		"label": label,
		"size": [image.get_width(), image.get_height()],
		"window_size": [get_window().size.x, get_window().size.y],
		"mode": DisplayServer.window_get_mode(),
		"frames_drawn": Engine.get_frames_drawn(),
	})

func file_result(ok: bool, files: PackedStringArray, index: int) -> void:
	cancellations.append([ok, files.size(), index])

func options_result(ok: bool, files: PackedStringArray, index: int, options: Dictionary) -> void:
	cancellations.append([ok, files.size(), index, options])

func unexpected_callback(_value: Variant) -> void:
	unexpected_dialog_callbacks += 1

func _ready() -> void:
	output = OS.get_environment("GODOT_OFFLINE_TEST_OUTPUT")
	var info := {
		"pid": OS.get_process_id(),
		"display": DisplayServer.get_name(),
		"method": RenderingServer.get_current_rendering_method(),
		"driver": RenderingServer.get_current_rendering_driver_name(),
		"adapter": RenderingServer.get_video_adapter_name(),
		"user_args": OS.get_cmdline_user_args(),
		"embedding_available": DisplayServer.has_feature(DisplayServer.FEATURE_WINDOW_EMBEDDING),
	}
	write_json("ready.json", info)
	if DisplayServer.get_name() == "headless":
		write_json("result.json", {"info": info, "checks": checks, "snapshots": snapshots})
		get_tree().quit()
		return

	var world := Node3D.new()
	world.name = "World"
	add_child(world)
	var cube := MeshInstance3D.new()
	cube.name = "BlueCube"
	cube.mesh = BoxMesh.new()
	cube.rotation = Vector3(0.3, 0.4, 0.0)
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color(0.1, 0.25, 1.0)
	cube.material_override = material
	world.add_child(cube)
	var camera := Camera3D.new()
	camera.name = "Camera"
	camera.position = Vector3(0, 0, 4)
	world.add_child(camera)
	camera.current = true
	var canvas := CanvasLayer.new()
	add_child(canvas)
	marker = ColorRect.new()
	marker.position = Vector2(24, 24)
	marker.size = Vector2(96, 96)
	marker.color = Color.RED
	canvas.add_child(marker)

	if OS.get_cmdline_user_args().has("--restore-initial-minimized"):
		check(DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_MINIMIZED, "initial minimize preserved")
		await get_tree().create_timer(0.3).timeout
		check(not get_window().can_draw(), "initial minimize still disables drawing")
		get_window().mode = Window.MODE_WINDOWED
		check(get_window().size == Vector2i(640, 480), "initial minimized window restores client size")
		check(get_window().can_draw(), "initial minimized window resumes drawing")

	await snapshot("a")
	marker.color = Color.GREEN
	await snapshot("b")

	if OS.get_cmdline_user_args().has("--hold"):
		await get_tree().create_timer(8).timeout

	if OS.get_cmdline_user_args().has("--exercise"):
		var window := get_window()
		var original_size := window.size
		for mode in [Window.MODE_MAXIMIZED, Window.MODE_WINDOWED, Window.MODE_FULLSCREEN, Window.MODE_WINDOWED]:
			window.mode = mode
			await snapshot("mode_%d_%d" % [mode, snapshots.size()])
			check(DisplayServer.window_get_mode() == mode, "requested window mode %d" % mode)
		check(window.size == original_size, "restore original windowed size")
		window.borderless = true
		await snapshot("borderless")
		window.borderless = false
		window.size = Vector2i(720, 520)
		await snapshot("resize")
		check(window.size == Vector2i(720, 520), "requested resize")

		var child := Window.new()
		child.title = "Offline Acceptance Child"
		child.size = Vector2i(240, 160)
		child.position = Vector2i(100, 100)
		child.visible = false
		add_child(child)
		child.show()
		await frames()
		check(child.get_window_id() != DisplayServer.INVALID_WINDOW_ID, "native child created")
		child.hide()
		child.show()
		await frames()
		child.queue_free()
		await frames()

		for cycle in 2:
			window.mode = Window.MODE_MINIMIZED
			await get_tree().create_timer(0.3).timeout
			check(DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_MINIMIZED, "explicit minimize preserved")
			check(not window.can_draw(), "explicit minimize still disables drawing")
			window.mode = Window.MODE_WINDOWED
			await snapshot("restored_%d" % cycle)
			check(window.size == Vector2i(720, 520), "minimize/restore preserves client size")
			check(window.can_draw(), "restored window resumes drawing")
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN)
		check(DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_WINDOWED, "exclusive fullscreen rejected without state change")
		DisplayServer.window_move_to_foreground()
		DisplayServer.window_request_attention()
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		Input.warp_mouse(Vector2(1, 1))
		await get_tree().create_timer(0.1).timeout
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

		check(DisplayServer.file_dialog_show("offline", "", "", false, DisplayServer.FILE_DIALOG_MODE_OPEN_FILE, PackedStringArray(), file_result) == OK, "file request accepted")
		check(DisplayServer.file_dialog_with_options_show("offline", "", "", "", false, DisplayServer.FILE_DIALOG_MODE_OPEN_FILE, PackedStringArray(), [], options_result) == OK, "options request accepted")
		check(cancellations.is_empty(), "file cancellation is asynchronous")
		check(DisplayServer.dialog_show("offline", "test", PackedStringArray(["OK"]), unexpected_callback) == ERR_UNAVAILABLE, "native message unavailable")
		check(DisplayServer.dialog_input_text("offline", "test", "", unexpected_callback) == ERR_UNAVAILABLE, "native input unavailable")
		OS.alert("offline acceptance nonblocking alert", "acceptance")
		await frames(8)
		check(cancellations.size() == 2, "exactly one cancellation per file request")
		for cancellation in cancellations:
			check(cancellation[0] == false and cancellation[1] == 0, "file cancellation payload")
		check(unexpected_dialog_callbacks == 0, "no native dialog result callbacks")
		await snapshot("end")

	write_json("result.json", {"info": info, "checks": checks, "snapshots": snapshots, "cancellations": cancellations})
	var success := true
	for entry in checks:
		success = success and entry["pass"]
	get_tree().quit(0 if success else 1)
