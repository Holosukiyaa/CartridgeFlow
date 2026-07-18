"""Import a VRM and render neutral CastPack reference views in Blender."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _args() -> argparse.Namespace:
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--vrm", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--size", type=int, default=768)
    return parser.parse_args(raw)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vrm_metadata(path: Path) -> dict:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        return {}
    offset = 12
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, offset)
        offset += 8
        payload = data[offset:offset + chunk_length]
        offset += chunk_length
        if chunk_type == b"JSON":
            document = json.loads(payload.rstrip(b" \t\r\n\x00").decode("utf-8"))
            return ((document.get("extensions") or {}).get("VRMC_vrm") or {}).get("meta") or {}
    return {}


def _enable_vrm_addon() -> str:
    candidates = ["vrm", "VRM_Addon_for_Blender-release"]
    for module in candidates:
        try:
            bpy.ops.preferences.addon_enable(module=module)
            if module in bpy.context.preferences.addons:
                return module
        except Exception:
            continue
    raise RuntimeError("VRM Add-on for Blender is not installed or could not be enabled")


def _import_vrm(path: Path) -> None:
    bpy.ops.import_scene.vrm(
        filepath=str(path.resolve()),
        use_addon_preferences=False,
        extract_textures_into_folder=True,
        make_new_texture_folder=True,
        set_shading_type_to_material_on_import=True,
        set_view_transform_to_standard_on_import=True,
        set_armature_display_to_wire=False,
        set_armature_display_to_show_in_front=False,
        set_armature_bone_shape_to_default=True,
        enable_mtoon_outline_preview=False,
    )


def _remove_auxiliary_meshes() -> list[str]:
    removed = []
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH":
            continue
        name = obj.name.lower()
        if name in {"cube", "plane", "background", "ground"} or len(obj.data.vertices) <= 8:
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    return removed


def _mesh_bounds() -> tuple[Vector, Vector]:
    corners = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        corners.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not corners:
        raise RuntimeError("VRM import produced no mesh objects")
    minimum = Vector((min(point.x for point in corners), min(point.y for point in corners), min(point.z for point in corners)))
    maximum = Vector((max(point.x for point in corners), max(point.y for point in corners), max(point.z for point in corners)))
    return minimum, maximum


def _look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def _make_camera(name: str, location: Vector, target: Vector) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.lens = 58
    data.sensor_width = 36
    data.clip_start = 0.01
    data.clip_end = 1000
    camera = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    _look_at(camera, target)
    return camera


def _add_area_light(name: str, location: Vector, energy: float, size: float, target: Vector) -> None:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    light = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(light)
    light.location = location
    _look_at(light, target)


def _configure_scene(scene: bpy.types.Scene, minimum: Vector, maximum: Vector, output_dir: Path, size: int) -> dict:
    center = (minimum + maximum) / 2
    height = max(maximum.z - minimum.z, 0.1)
    depth = max(maximum.y - minimum.y, 0.1)
    distance = max(height * 2.0, depth * 4.0, 2.5)
    target = Vector((center.x, center.y, minimum.z + height * 0.53))

    for obj in list(scene.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    front = _make_camera("CastPackFront", Vector((center.x, center.y - distance, target.z)), target)
    three_quarter = _make_camera("CastPackThreeQuarter", Vector((center.x + distance * 0.55, center.y - distance * 0.85, target.z)), target)
    side = _make_camera("CastPackSide", Vector((center.x + distance, center.y, target.z)), target)
    _add_area_light("CastPackKey", Vector((center.x - distance * 0.45, center.y - distance * 0.6, maximum.z + height * 0.7)), 900, height * 0.8, target)
    _add_area_light("CastPackFill", Vector((center.x + distance * 0.65, center.y - distance * 0.25, target.z + height * 0.2)), 500, height * 0.7, target)
    _add_area_light("CastPackRim", Vector((center.x, center.y + distance * 0.55, maximum.z)), 800, height * 0.6, target)

    scene.camera = three_quarter
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = size
    scene.render.resolution_y = int(size * 4 / 3)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.72, 0.74, 0.78, 1.0)
        background.inputs["Strength"].default_value = 0.35
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    return {"front": front, "three_quarter": three_quarter, "side": side, "target": list(target), "height": height}


def main() -> None:
    args = _args()
    vrm_path = args.vrm.resolve()
    output_dir = args.output_dir.resolve()
    if not vrm_path.is_file():
        raise FileNotFoundError(vrm_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    addon = _enable_vrm_addon()
    _import_vrm(vrm_path)
    removed_auxiliary_meshes = _remove_auxiliary_meshes()
    minimum, maximum = _mesh_bounds()
    scene = bpy.context.scene
    cameras = _configure_scene(scene, minimum, maximum, output_dir, max(256, min(args.size, 2048)))

    views = {"front": cameras["front"], "three_quarter": cameras["three_quarter"], "side": cameras["side"]}
    outputs = {}
    for name, camera in views.items():
        scene.camera = camera
        target = output_dir / f"hero_{name}.png"
        scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        if not target.is_file() or target.stat().st_size < 1024:
            raise RuntimeError(f"reference render failed: {target}")
        outputs[name] = {"path": target.name, "sha256": _sha256(target)}

    blend_path = output_dir / "boy1_reference.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    metadata = {
        "schema": "cartridgeflow.vroid_reference_render.v1",
        "source_vrm": {"path": str(vrm_path), "sha256": _sha256(vrm_path)},
        "vrm_metadata": _vrm_metadata(vrm_path),
        "blender_version": bpy.app.version_string,
        "vrm_addon_module": addon,
        "removed_auxiliary_meshes": removed_auxiliary_meshes,
        "outputs": outputs,
        "blend": {"path": blend_path.name, "sha256": _sha256(blend_path)},
        "license_review": "pending_user_confirmation",
    }
    (output_dir / "boy1_reference.metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CF_VROID_REFERENCE=" + json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
