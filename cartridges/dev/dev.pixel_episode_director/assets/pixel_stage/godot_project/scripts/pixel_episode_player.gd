extends Node2D

const DEFAULT_VIEW_SIZE := Vector2i(1280, 720)

var plan: Dictionary = {}
var asset_manifest: Dictionary = {}
var cartridge_root := ""
var asset_manifest_path := ""
var character_assets: Dictionary = {}
var location_assets: Dictionary = {}
var elapsed := 0.0
var view_size := DEFAULT_VIEW_SIZE
var explicit_duration := 0.0


func _ready() -> void:
    _parse_runtime_args()
    plan = _load_plan()
    asset_manifest = _load_asset_manifest()
    character_assets = _load_character_assets()
    location_assets = _load_location_assets()
    view_size = _resolve_view_size()
    if view_size.x > 0 and view_size.y > 0:
        DisplayServer.window_set_size(view_size)
    queue_redraw()


func _process(delta: float) -> void:
    elapsed += delta
    queue_redraw()
    var duration := explicit_duration if explicit_duration > 0.0 else _timeline_duration()
    if duration > 0.0 and elapsed >= duration:
        get_tree().quit()


func _draw() -> void:
    view_size = Vector2i(get_viewport_rect().size)
    draw_rect(Rect2(Vector2.ZERO, view_size), Color("#10151d"))
    var shot: Dictionary = _current_shot()
    var item: Dictionary = _current_timeline_item()
    var progress: float = float(item.get("progress", 0.0))
    var camera: Dictionary = _camera_values(shot.get("camera", {}), progress)
    _draw_background(camera, progress)
    _draw_stage(shot, camera, progress)
    _draw_camera_effect(shot.get("camera", {}), progress)
    _draw_overlay(shot)


func _load_plan() -> Dictionary:
    var shot_plan_path := "../test_output/pixel_episode/shot_plan.json"
    var args := OS.get_cmdline_user_args()
    for i in range(args.size()):
        if args[i] == "--shot-plan" and i + 1 < args.size():
            shot_plan_path = args[i + 1]
    if not FileAccess.file_exists(shot_plan_path):
        return {"title": "Pixel Episode", "style": {"resolution": "1280x720", "fps": 24}, "shots": []}
    var text := FileAccess.get_file_as_string(shot_plan_path)
    var parsed = JSON.parse_string(text)
    if typeof(parsed) == TYPE_DICTIONARY:
        return parsed
    return {"title": "Pixel Episode", "style": {"resolution": "1280x720", "fps": 24}, "shots": []}


func _parse_runtime_args() -> void:
    var args := OS.get_cmdline_user_args()
    for i in range(args.size()):
        if args[i] == "--duration" and i + 1 < args.size():
            explicit_duration = float(args[i + 1])
        elif args[i] == "--asset-manifest" and i + 1 < args.size():
            asset_manifest_path = args[i + 1]
        elif args[i] == "--cartridge-root" and i + 1 < args.size():
            cartridge_root = args[i + 1]


func _load_asset_manifest() -> Dictionary:
    var path := asset_manifest_path
    if path == "":
        path = _resolve_asset_path("assets/asset_manifest.json")
    if path == "" or not FileAccess.file_exists(path):
        return {}
    var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
    return parsed if typeof(parsed) == TYPE_DICTIONARY else {}


func _load_character_assets() -> Dictionary:
    var loaded := {}
    var approved: Dictionary = asset_manifest.get("approved_assets", {})
    var characters: Dictionary = approved.get("characters", {})
    for character_id in characters.keys():
        var entry: Dictionary = characters.get(character_id, {})
        var profile := _read_json_asset(str(entry.get("profile", "")))
        var metadata_path := str(entry.get("metadata", ""))
        if metadata_path == "" and profile.has("asset"):
            metadata_path = str(profile.get("asset", {}).get("metadata", ""))
        var metadata := _read_json_asset(metadata_path)
        var sheet_path := str(entry.get("spritesheet", ""))
        if sheet_path == "" and profile.has("asset"):
            sheet_path = str(profile.get("asset", {}).get("spritesheet", ""))
        if sheet_path == "":
            sheet_path = str(metadata.get("image", ""))
        var texture := _load_texture_asset(sheet_path)
        if texture and metadata.has("animations"):
            loaded[str(character_id)] = {
                "texture": texture,
                "metadata": metadata,
                "profile": profile
            }
    return loaded


func _load_location_assets() -> Dictionary:
    var loaded := {}
    var approved: Dictionary = asset_manifest.get("approved_assets", {})
    var locations: Dictionary = approved.get("locations", {})
    for location_id in locations.keys():
        var entry: Dictionary = locations.get(location_id, {})
        var profile := _read_json_asset(str(entry.get("profile", "")))
        var raw_layers: Array = []
        if profile.has("layers") and typeof(profile.get("layers")) == TYPE_ARRAY:
            raw_layers = profile.get("layers", [])
        elif entry.has("layers") and typeof(entry.get("layers")) == TYPE_ARRAY:
            raw_layers = entry.get("layers", [])
        var layers: Array = []
        for raw_layer in raw_layers:
            if typeof(raw_layer) != TYPE_DICTIONARY:
                continue
            var layer: Dictionary = raw_layer
            var image_path := str(layer.get("image", ""))
            if image_path == "":
                image_path = str(layer.get("path", ""))
            var texture := _load_texture_asset(image_path)
            if texture:
                layers.append({
                    "id": str(layer.get("id", "")),
                    "texture": texture,
                    "parallax": float(layer.get("parallax", 1.0)),
                    "z_index": int(layer.get("z_index", layers.size() * 10))
                })
        layers.sort_custom(func(a, b): return int(a.get("z_index", 0)) < int(b.get("z_index", 0)))
        if not layers.is_empty():
            loaded[str(location_id)] = {
                "profile": profile,
                "layers": layers
            }
    return loaded


func _read_json_asset(path: String) -> Dictionary:
    var resolved := _resolve_asset_path(path)
    if resolved == "" or not FileAccess.file_exists(resolved):
        return {}
    var parsed = JSON.parse_string(FileAccess.get_file_as_string(resolved))
    return parsed if typeof(parsed) == TYPE_DICTIONARY else {}


func _load_texture_asset(path: String) -> Texture2D:
    var resolved := _resolve_asset_path(path)
    if resolved == "" or not FileAccess.file_exists(resolved):
        return null
    var image := Image.new()
    var err := image.load(resolved)
    if err != OK:
        return null
    return ImageTexture.create_from_image(image)


func _resolve_asset_path(path: String) -> String:
    if path == "":
        return ""
    if path.is_absolute_path():
        return path
    var normalized := path.replace("\\", "/")
    if cartridge_root != "":
        if normalized.begins_with("assets/"):
            return cartridge_root.path_join(normalized)
        return cartridge_root.path_join(normalized)
    return ProjectSettings.globalize_path("res://../").path_join(normalized)


func _resolve_view_size() -> Vector2i:
    var args := OS.get_cmdline_user_args()
    var width := 0
    var height := 0
    for i in range(args.size()):
        if args[i] == "--width" and i + 1 < args.size():
            width = int(args[i + 1])
        elif args[i] == "--height" and i + 1 < args.size():
            height = int(args[i + 1])
    if width > 0 and height > 0:
        return Vector2i(width, height)
    var style: Dictionary = plan.get("style", {})
    var resolution := str(style.get("resolution", "1280x720")).to_lower()
    var parts := resolution.split("x")
    if parts.size() == 2:
        width = int(parts[0])
        height = int(parts[1])
        if width > 0 and height > 0:
            return Vector2i(width, height)
    return DEFAULT_VIEW_SIZE


func _timeline_duration() -> float:
    var total := 0.0
    for shot in plan.get("shots", []):
        if typeof(shot) == TYPE_DICTIONARY:
            total += max(1.0, float(shot.get("duration", 4)))
    return total if total > 0.0 else 4.0


func _current_shot() -> Dictionary:
    return _current_timeline_item().get("shot", {})


func _current_timeline_item() -> Dictionary:
    var shots: Array = plan.get("shots", [])
    if shots.is_empty():
        return {"shot": {}, "progress": 0.0}
    var cursor := 0.0
    for shot in shots:
        if typeof(shot) != TYPE_DICTIONARY:
            continue
        var duration: float = max(1.0, float(shot.get("duration", 4)))
        if elapsed >= cursor and elapsed < cursor + duration:
            return {
                "shot": shot,
                "progress": clamp((elapsed - cursor) / duration, 0.0, 1.0)
            }
        cursor += duration
    return {"shot": shots.back(), "progress": 1.0}


func _camera_values(camera: Dictionary, progress: float) -> Dictionary:
    var kind := str(camera.get("type", "wide_establishing"))
    var cam_x := 0.0
    var zoom := float(camera.get("zoom", 1.0))
    if kind == "tracking_side":
        var from_pos: Array = camera.get("from", [0, 0])
        var to_pos: Array = camera.get("to", [0, 0])
        cam_x = lerpf(float(from_pos[0]), float(to_pos[0]), progress)
    elif kind == "push_in":
        zoom = lerpf(float(camera.get("zoom_from", 1.0)), float(camera.get("zoom_to", 1.45)), progress)
        cam_x = 2.5 * progress
    elif kind == "wide_establishing":
        var position: Array = camera.get("position", [0, 0])
        cam_x = float(position[0])
        zoom = float(camera.get("zoom", 0.85))
    elif kind == "close_up":
        zoom = float(camera.get("zoom", 1.65))
        cam_x = 3.8
    elif kind == "over_shoulder":
        var os_from: Array = camera.get("from", [5, 0])
        var os_to: Array = camera.get("to", [7, 0])
        cam_x = lerpf(float(os_from[0]), float(os_to[0]), progress)
        zoom = float(camera.get("zoom", 1.25))
    elif kind == "reveal":
        zoom = lerpf(float(camera.get("zoom_from", 1.05)), float(camera.get("zoom_to", 1.35)), progress)
        cam_x = 1.5 + 3.0 * progress
    return {"x": cam_x, "zoom": clamp(zoom, 0.7, 2.0), "kind": kind}


func _draw_background(camera: Dictionary, progress: float) -> void:
    if _draw_location_layers(camera):
        return

    var w := float(view_size.x)
    var h := float(view_size.y)
    var cam_x := float(camera.get("x", 0.0))
    for y in range(0, view_size.y, 3):
        var amount: float = float(y) / max(1.0, h)
        var col := Color(0.04 + amount * 0.06, 0.055 + amount * 0.025, 0.09 + amount * 0.07)
        draw_rect(Rect2(0, y, w, 3), col)

    var horizon := int(h * 0.58)
    for layer in range(2):
        var parallax := 0.16 + 0.2 * float(layer)
        var spacing := int(112 - layer * 16)
        for i in range(12):
            var x := fposmod(float(i * spacing) - cam_x * 42.0 * parallax, w + 180.0) - 90.0
            var bw := 58.0 + float((i * 13 + layer * 11) % 48)
            var bh := 120.0 + float((i * 29 + layer * 17) % 150)
            var base := horizon + layer * 48
            var tone := Color("#171d2a") if layer == 0 else Color("#202638")
            draw_rect(Rect2(x, base - bh, bw, bh), tone)
            for wy in range(int(base - bh + 18), int(base - 16), 28):
                for wx in range(int(x + 12), int(x + bw - 10), 24):
                    var lit := int(i + wx + wy + elapsed * 3.0) % 4 == 0
                    draw_rect(Rect2(wx, wy, 8, 10), Color("#f1b24d", 0.78 if lit else 0.16))

    var ground_y := int(h * 0.72)
    draw_rect(Rect2(0, ground_y, w, h - ground_y), Color("#222028"))
    for i in range(-5, 14):
        var sx := int(i * 150 - cam_x * 36.0)
        draw_line(Vector2(sx, ground_y + 32), Vector2(sx + 320, h + 20), Color("#42394b"), 3)
    for i in range(7):
        var rx := fposmod(70.0 + i * 235.0 - cam_x * 50.0, w + 180.0) - 90.0
        draw_rect(Rect2(rx, ground_y + 58, 96, 8), Color("#e88c45", 0.26))
        draw_rect(Rect2(rx + 38, ground_y + 128, 150, 7), Color("#4895d4", 0.20))

    _draw_market_layer(cam_x, ground_y)
    _draw_foreground_lamps(cam_x, ground_y)


func _draw_location_layers(camera: Dictionary) -> bool:
    var shot := _current_shot()
    var location_id := str(shot.get("location_id", ""))
    if location_id == "":
        location_id = str(shot.get("location", ""))
    if location_id == "":
        location_id = str(plan.get("location", "night_alley"))
    if not location_assets.has(location_id):
        if location_assets.has("night_alley"):
            location_id = "night_alley"
        else:
            return false

    var asset: Dictionary = location_assets.get(location_id, {})
    var layers: Array = asset.get("layers", [])
    if layers.is_empty():
        return false

    var cam_x := float(camera.get("x", 0.0))
    var drew := false
    for layer in layers:
        if typeof(layer) != TYPE_DICTIONARY:
            continue
        var texture: Texture2D = layer.get("texture", null)
        if texture == null:
            continue
        var tex_w: float = max(1.0, float(texture.get_width()))
        var tex_h: float = max(1.0, float(texture.get_height()))
        var scale: float = max(float(view_size.x) / tex_w, float(view_size.y) / tex_h)
        var draw_w := tex_w * scale
        var draw_h := tex_h * scale
        var y := (float(view_size.y) - draw_h) * 0.5
        var parallax := float(layer.get("parallax", 1.0))
        var offset := -cam_x * 42.0 * parallax
        var start_x := fposmod(offset, draw_w) - draw_w
        for i in range(4):
            draw_texture_rect(texture, Rect2(start_x + draw_w * i, y, draw_w, draw_h), false)
        drew = true
    return drew


func _draw_market_layer(cam_x: float, ground_y: int) -> void:
    var w := float(view_size.x)
    for i in range(6):
        var x := fposmod(48.0 + i * 225.0 - cam_x * 72.0, w + 240.0) - 120.0
        var y := ground_y - 132 + (i % 2) * 10
        var body := Color("#453039") if i % 2 else Color("#32404c")
        var awning := Color("#b84841") if i % 2 else Color("#d28a38")
        draw_rect(Rect2(x, y + 34, 156, 100), body)
        draw_rect(Rect2(x - 12, y, 180, 36), awning)
        for stripe in range(0, 180, 30):
            draw_rect(Rect2(x - 8 + stripe, y, 14, 36), Color("#f2bd63"))
        draw_rect(Rect2(x + 20, y + 66, 112, 34), Color("#655143"))
        draw_rect(Rect2(x + 38, y + 48, 30, 26), Color("#e8a846"))
        draw_rect(Rect2(x + 84, y + 46, 38, 28), Color("#5ca0bd"))
        if i % 2 == 0:
            draw_rect(Rect2(x + 42, y - 58, 86, 34), Color("#101620"))
            draw_rect(Rect2(x + 48, y - 52, 74, 22), Color("#cc4d5d"))
            for dot in range(5):
                draw_rect(Rect2(x + 56 + dot * 13, y - 45, 7, 7), Color("#ffd98a"))


func _draw_foreground_lamps(cam_x: float, ground_y: int) -> void:
    var w := float(view_size.x)
    for i in range(4):
        var x := fposmod(90.0 + i * 350.0 - cam_x * 118.0, w + 320.0) - 160.0
        var top := ground_y - 230
        var flicker := 0.18 + 0.10 * (0.5 + 0.5 * sin(elapsed * 8.0 + i))
        draw_rect(Rect2(x, top, 8, 260), Color("#17191f"))
        draw_circle(Vector2(x + 4, top + 10), 54, Color("#f0a741", flicker))
        draw_rect(Rect2(x - 14, top - 10, 36, 26), Color("#f4ad42"))
        draw_rect(Rect2(x - 6, top - 3, 20, 12), Color("#ffe28a"))
        for j in range(3):
            var lx := x + 72 + j * 43
            var ly := top + 36 + ((i + j) % 2) * 18
            draw_rect(Rect2(lx, ly, 20, 28), Color("#c83b3a"))
            draw_rect(Rect2(lx + 6, ly + 6, 8, 16), Color("#ffc75b"))


func _draw_stage(shot: Dictionary, camera: Dictionary, progress: float) -> void:
    var actors: Array = shot.get("actors", [])
    actors.sort_custom(func(a, b): return _actor_depth(a) < _actor_depth(b))
    for actor in actors:
        if typeof(actor) == TYPE_DICTIONARY:
            _draw_actor(actor, camera, progress)


func _actor_depth(actor: Variant) -> float:
    if typeof(actor) != TYPE_DICTIONARY:
        return 0.0
    var pos: Array = actor.get("position", [0, 0, 0])
    return float(pos[2]) if pos.size() > 2 else 0.0


func _draw_actor(actor: Dictionary, camera: Dictionary, progress: float) -> void:
    var actor_id := str(actor.get("id", ""))
    if character_assets.has(actor_id):
        if _draw_sprite_actor(character_assets[actor_id], actor, camera, progress):
            return

    var pos: Array = actor.get("position", [6, 6, 1])
    var x := float(pos[0]) if pos.size() > 0 else 6.0
    var y := float(pos[1]) if pos.size() > 1 else 6.0
    var move_to = actor.get("move_to", null)
    if typeof(move_to) == TYPE_ARRAY and move_to.size() >= 2:
        x = lerpf(x, float(move_to[0]), progress)
        y = lerpf(y, float(move_to[1]), progress)

    var zoom := float(camera.get("zoom", 1.0))
    var cam_x := float(camera.get("x", 0.0))
    var unit := view_size.y / 360.0
    var screen_x := view_size.x * 0.38 + (x - 5.5 - cam_x) * 44.0 * unit * zoom
    var foot_y := view_size.y * 0.47 + y * 14.0 * unit
    var walking := str(actor.get("animation", "")).find("walk") >= 0
    var bob := sin(progress * PI * 6.0) * 4.0 * unit if walking else 0.0
    var swing := sin(progress * PI * 6.0) * 7.0 * unit if walking else 0.0
    var scale: float = max(9.0 * unit, 10.0 * unit * zoom)
    var body := Color("#4992dc") if actor_id == "hero" else Color("#d67c3c")
    var trim := Color("#77bdf0") if actor_id == "hero" else Color("#f4b24a")
    var pants := Color("#131823") if actor_id == "hero" else Color("#28221f")
    var skin := Color("#e8b586")
    var hair := Color("#201818") if actor_id == "hero" else Color("#36261b")
    var outline := Color("#05070b")

    var head_top := foot_y - scale * 8.8 + bob
    var head_h := scale * 2.25
    var body_top := head_top + head_h + scale * 0.55
    var body_h := scale * 4.3
    var torso_w := scale * 4.6
    var leg_top := body_top + body_h

    _px_rect(screen_x - scale * 1.35, head_top - 4, scale * 2.7, head_h + 8, outline)
    _px_rect(screen_x - scale * 1.15, head_top, scale * 2.3, head_h, skin)
    _px_rect(screen_x - scale * 1.2, head_top, scale * 2.4, scale * 0.72, hair)
    _px_rect(screen_x - scale * 1.35, head_top + scale * 0.55, scale * 0.7, head_h * 0.72, hair)
    _px_rect(screen_x - scale * 0.55, head_top + scale * 1.15, 3, 3, outline)
    _px_rect(screen_x + scale * 0.48, head_top + scale * 1.15, 3, 3, outline)

    _px_rect(screen_x - scale * 0.45, body_top - scale * 0.55, scale * 0.9, scale * 0.8, skin)
    _px_rect(screen_x - torso_w * 0.5 - 4, body_top - 4, torso_w + 8, body_h + 8, outline)
    _px_rect(screen_x - torso_w * 0.5, body_top, torso_w, body_h, body)
    _px_rect(screen_x - torso_w * 0.5, body_top, torso_w, scale * 0.7, trim)
    _px_rect(screen_x - 2, body_top + scale * 0.7, 4, body_h - scale * 0.8, body.darkened(0.35))

    _px_rect(screen_x - torso_w * 0.5 - scale * 1.1, body_top + scale * 0.8, scale * 1.0, body_h * 0.72, outline)
    _px_rect(screen_x + torso_w * 0.5 + scale * 0.1, body_top + scale * 0.8, scale * 1.0, body_h * 0.72, outline)
    _px_rect(screen_x - torso_w * 0.5 - scale * 0.9, body_top + scale * 0.85, scale * 0.7, body_h * 0.62, body)
    _px_rect(screen_x + torso_w * 0.5 + scale * 0.25, body_top + scale * 0.85, scale * 0.7, body_h * 0.62, body)
    _px_rect(screen_x - torso_w * 0.5 - scale * 0.95, body_top + body_h * 0.9, scale * 0.75, scale * 0.48, skin)
    _px_rect(screen_x + torso_w * 0.5 + scale * 0.25, body_top + body_h * 0.9, scale * 0.75, scale * 0.48, skin)

    _px_rect(screen_x - scale * 1.35, leg_top - 2, scale * 1.0, scale * 3.0 + swing, outline)
    _px_rect(screen_x + scale * 0.35, leg_top - 2, scale * 1.0, scale * 3.0 - swing, outline)
    _px_rect(screen_x - scale * 1.18, leg_top, scale * 0.66, scale * 2.85 + swing, pants)
    _px_rect(screen_x + scale * 0.52, leg_top, scale * 0.66, scale * 2.85 - swing, pants)
    _px_rect(screen_x - scale * 1.45, leg_top + scale * 2.85 + swing, scale * 1.15, scale * 0.35, outline)
    _px_rect(screen_x + scale * 0.25, leg_top + scale * 2.85 - swing, scale * 1.15, scale * 0.35, outline)

    if actor.get("emotion", "") in ["suspicious", "alert"]:
        _px_rect(screen_x + scale * 1.35, head_top - scale * 0.7, scale * 0.2, scale * 1.0, Color("#ffe892"))
        _px_rect(screen_x + scale * 1.25, head_top + scale * 0.6, scale * 0.4, scale * 0.28, Color("#ffe892"))


func _draw_sprite_actor(asset: Dictionary, actor: Dictionary, camera: Dictionary, progress: float) -> bool:
    var texture: Texture2D = asset.get("texture", null)
    var metadata: Dictionary = asset.get("metadata", {})
    if texture == null or not metadata.has("animations"):
        return false
    var animations: Dictionary = metadata.get("animations", {})
    var action := str(actor.get("animation", "idle"))
    if not animations.has(action):
        action = "idle" if animations.has("idle") else str(animations.keys()[0])
    var animation: Dictionary = animations.get(action, {})
    var frames: Array = animation.get("frames", [])
    if frames.is_empty():
        return false

    var fps := float(animation.get("fps", metadata.get("fps", 12)))
    var frame_index := int(floor(elapsed * max(1.0, fps))) % frames.size()
    var frame: Dictionary = frames[frame_index]
    var frame_w := float(frame.get("w", metadata.get("frame_size", [96, 128])[0]))
    var frame_h := float(frame.get("h", metadata.get("frame_size", [96, 128])[1]))
    var source := Rect2(float(frame.get("x", 0)), float(frame.get("y", 0)), frame_w, frame_h)

    var pos: Array = actor.get("position", [6, 6, 1])
    var x := float(pos[0]) if pos.size() > 0 else 6.0
    var y := float(pos[1]) if pos.size() > 1 else 6.0
    var move_to = actor.get("move_to", null)
    if typeof(move_to) == TYPE_ARRAY and move_to.size() >= 2:
        x = lerpf(x, float(move_to[0]), progress)
        y = lerpf(y, float(move_to[1]), progress)

    var zoom := float(camera.get("zoom", 1.0))
    var cam_x := float(camera.get("x", 0.0))
    var unit := view_size.y / 360.0
    var screen_x := view_size.x * 0.38 + (x - 5.5 - cam_x) * 44.0 * unit * zoom
    var foot_y := view_size.y * 0.47 + y * 14.0 * unit
    var target_h: float = max(128.0, frame_h * unit * 0.9 * zoom)
    var target_w: float = frame_w * (target_h / max(1.0, frame_h))
    var pivot: Array = metadata.get("pivot", [frame_w * 0.5, frame_h - 8])
    var pivot_x: float = float(pivot[0]) * (target_w / max(1.0, frame_w))
    var pivot_y: float = float(pivot[1]) * (target_h / max(1.0, frame_h))
    var dest: Rect2 = Rect2(screen_x - pivot_x, foot_y - pivot_y, target_w, target_h)
    draw_texture_rect_region(texture, dest, source)
    return true


func _px_rect(x: float, y: float, w: float, h: float, color: Color) -> void:
    draw_rect(Rect2(round(x), round(y), round(w), round(h)), color)


func _draw_camera_effect(camera: Dictionary, progress: float) -> void:
    var kind := str(camera.get("type", ""))
    if kind == "over_shoulder":
        var shoulder_w := view_size.x * 0.22
        draw_rect(Rect2(0, view_size.y * 0.42, shoulder_w, view_size.y * 0.58), Color("#08090c", 0.76))
        draw_circle(Vector2(shoulder_w * 0.35, view_size.y * 0.46), shoulder_w * 0.34, Color("#17151a", 0.88))
        draw_rect(Rect2(shoulder_w - 10, view_size.y * 0.46, 8, view_size.y * 0.54), Color("#4a342b"))
    elif kind == "reveal":
        var cover: float = float(view_size.x) * max(0.0, 0.42 * (1.0 - progress))
        if cover > 0:
            draw_rect(Rect2(0, 0, cover, view_size.y), Color("#040508", 0.88))
            draw_rect(Rect2(cover - 8, 0, 8, view_size.y), Color("#e49737"))


func _draw_overlay(shot: Dictionary) -> void:
    var title_font := ThemeDB.fallback_font
    var panel_w: float = min(float(view_size.x) - 32.0, 520.0)
    draw_rect(Rect2(18, 18, panel_w, 82), Color(0.035, 0.05, 0.075, 0.78))
    draw_rect(Rect2(18, 18, panel_w, 4), Color("#e6a043"))
    draw_string(title_font, Vector2(34, 48), str(plan.get("title", "Pixel Episode")), HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color("#fff1d6"))
    var camera_type := str(shot.get("camera", {}).get("type", "camera"))
    draw_string(title_font, Vector2(34, 78), "%s / %s / %02ds" % [str(shot.get("id", "shot")), camera_type, int(elapsed)], HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color("#d1d5db"))

    var dialogue := _dialogue_text(shot)
    if dialogue != "":
        var box_h := 86
        var top := view_size.y - box_h - 28
        draw_rect(Rect2(32, top, view_size.x - 64, box_h), Color(0.03, 0.04, 0.06, 0.84))
        draw_rect(Rect2(32, top, view_size.x - 64, 4), Color("#f0ab48"))
        draw_string(title_font, Vector2(52, top + 34), dialogue.substr(0, 72), HORIZONTAL_ALIGNMENT_LEFT, -1, 19, Color("#ffffff"))


func _dialogue_text(shot: Dictionary) -> String:
    var parts: Array[String] = []
    for item in shot.get("dialogue", []):
        if typeof(item) == TYPE_DICTIONARY:
            var speaker := str(item.get("speaker", ""))
            var line := str(item.get("line", ""))
            if line != "":
                parts.append("%s: %s" % [speaker, line] if speaker != "" else line)
    return "  ".join(parts)
