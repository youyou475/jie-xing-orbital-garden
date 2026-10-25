"""
《借星》多视角渲染预览
用途：无界面下输出关键视角 PNG，用于人工检查建模效果并迭代。

/Applications/Blender.app/Contents/MacOS/Blender --background --python render_preview.py
"""

import os
import sys
import math

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_garden as bg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))   # .../jie-xing-orbital-garden（仓库根）
OUT_DIR = os.path.join(ROOT, "renders", "preview")
os.makedirs(OUT_DIR, exist_ok=True)

VIEWS = [
    ("01_舱内全景俯瞰", (2.0, -15.0, 26.0), (2.0, -2.0, 1.0), 55),
    ("02_主厅内南望月洞门", (2.0, 13.0, 1.65), (2.0, -8.0, 2.2), 55),
    ("03_池畔看月到风来亭", (-3.0, -7.5, 1.7), (12.0, -10.5, 2.6), 58),
    ("04_殿春簃庭院", (-8.0, -9.5, 1.75), (-14.5, -12.2, 1.5), 62),
    ("05_曲廊漏窗", (-16.5, 2.0, 1.65), (-7.0, -4.0, 1.6), 60),
    ("06_天窗仰望星空", (2.0, 2.0, 1.7), (2.0, 0.0, 34.0), 80),
    ("07_门洞框星特写", (2.0, 8.5, 1.65), (2.0, 3.5, 2.3), 60),
    ("08_引静桥跨池", (11.5, 2.0, 1.9), (11.5, -7.0, 0.9), 60),
]


def aim(cam_obj, target, loc):
    cam_obj.location = Vector(loc)
    direction = Vector(target) - Vector(loc)
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_render(scene, w=1280, h=720):
    scene.render.resolution_x = w
    scene.render.resolution_y = h
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        try:
            scene.eevee.taa_render_samples = 24
            scene.eevee.use_raytracing = True
        except Exception:
            pass
    except Exception:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 24


def main():
    bg.build_all()
    scene = bpy.context.scene
    setup_render(scene)

    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.clip_end = 1200.0
    cam_obj = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    for name, loc, target, fov in VIEWS:
        cam_data.angle = math.radians(fov)
        aim(cam_obj, target, loc)
        scene.render.filepath = os.path.join(OUT_DIR, name + ".png")
        bpy.ops.render.render(write_still=True)
        print("[ok]", name)


if __name__ == "__main__":
    main()
