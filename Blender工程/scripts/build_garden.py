"""
《借星》· 网师园的轨道移植 —— Blender 程序化建模脚本
Blender 4.5.9 LTS

运行方式（命令行，无需打开界面）：
/Applications/Blender.app/Contents/MacOS/Blender --background --python build_garden.py

产出：
  ../../assets/garden.glb                     网页漫游用模型
  ../../assets/anchors.json                   五个叙事锚点（含坐标换算到 Y-up）
  ../借星_网师园轨道舱.blend                  Blender 源工程

设计说明：
  全部几何由本脚本程序化生成，不使用任何第三方模型/贴图/HDRI，
  因此作品无第三方素材授权问题，第三方资源说明可如实写「无」。
"""

import bpy
import bmesh
import json
import math
import os
import random
from mathutils import Vector, Matrix, noise

random.seed(20261022)

# ---------------------------------------------------------------- 路径
HERE = os.path.dirname(os.path.abspath(__file__))          # .../jie-xing-orbital-garden/Blender工程/scripts
BLEND_DIR = os.path.dirname(HERE)                          # .../jie-xing-orbital-garden/Blender工程
ROOT = os.path.dirname(BLEND_DIR)                          # .../jie-xing-orbital-garden（仓库根）
OUT_GLB = os.path.join(ROOT, "assets", "garden.glb")
OUT_JSON = os.path.join(ROOT, "assets", "anchors.json")
OUT_BLEND = os.path.join(BLEND_DIR, "借星_网师园轨道舱.blend")

# ---------------------------------------------------------------- 尺度（米）
CFG = {
    "hull_radius": 26.0,     # 舱体内半径
    "hull_axis_z": 12.0,     # 圆筒轴心高度（地面 z=0 为弦）
    "hull_half_len": 34.0,   # 舱体沿 X 半长
    "ground_half_x": 30.0,
    "ground_half_y": 20.0,
    "pool_center": (6.0, -3.5),
    "pool_size": (16.0, 12.0),
    "water_z": 0.12,
}

# ---------------------------------------------------------------- 材质桶
BUCKETS = {}
MATS = {}


def make_mat(name, color, rough=0.7, metal=0.0, alpha=1.0,
             emit_color=(0.0, 0.0, 0.0), emit_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = m.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        m.node_tree.links.new(bsdf.outputs[0],
                              m.node_tree.nodes.get("Material Output").inputs[0])
    try:
        bsdf.inputs["Base Color"].default_value = tuple(color) + (1.0,)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
    except Exception as e:
        print("[mat warn]", name, e)
    if alpha < 1.0:
        try:
            bsdf.inputs["Alpha"].default_value = alpha
        except Exception:
            pass
        try:
            m.blend_method = "BLEND"
        except Exception:
            pass
    if emit_strength > 0.0:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = tuple(emit_color) + (1.0,)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit_strength
    MATS[name] = m
    return m


def init_materials():
    make_mat("white_wall", (0.86, 0.85, 0.81), rough=0.85)          # 粉墙
    make_mat("wood", (0.28, 0.13, 0.10), rough=0.55)                 # 木构（栗色）
    make_mat("tile", (0.28, 0.30, 0.34), rough=0.7)                  # 黛瓦
    make_mat("stone", (0.55, 0.56, 0.54), rough=0.9)                 # 青石/铺地
    make_mat("rock", (0.42, 0.43, 0.45), rough=0.95)                 # 太湖石
    make_mat("water", (0.05, 0.16, 0.22), rough=0.08, metal=0.7,
             alpha=0.92, emit_color=(0.02, 0.06, 0.10), emit_strength=0.35)
    make_mat("hull", (0.30, 0.32, 0.35), rough=0.45, metal=0.75)     # 舱体金属
    make_mat("hull_dark", (0.16, 0.17, 0.19), rough=0.6, metal=0.6)  # 舱体结构件
    make_mat("screen", (0.35, 0.62, 0.95), rough=0.2, metal=0.1,
             emit_color=(0.35, 0.62, 0.95), emit_strength=2.4)       # 舷窗屏/全息
    make_mat("glow", (1.0, 0.86, 0.62), rough=0.4,
             emit_color=(1.0, 0.86, 0.62), emit_strength=3.0)        # 灯带
    make_mat("star", (1.0, 1.0, 1.0), rough=1.0,
             emit_color=(1.0, 1.0, 1.0), emit_strength=4.0)          # 星
    make_mat("space", (0.01, 0.01, 0.03), rough=1.0,
             emit_color=(0.01, 0.02, 0.05), emit_strength=0.6)       # 星幕底
    make_mat("earth", (0.10, 0.34, 0.62), rough=0.9,
             emit_color=(0.06, 0.20, 0.40), emit_strength=0.7)       # 地球
    make_mat("plant", (0.16, 0.34, 0.18), rough=0.9)                 # 绿植


def bucket(key):
    """按材质分桶累积几何，最终每个桶输出一个对象，控制 GLB 体积与对象数。"""
    if key not in BUCKETS:
        BUCKETS[key] = bmesh.new()
    return BUCKETS[key]


def flush_buckets():
    for key, bm in BUCKETS.items():
        if bm is None or len(bm.verts) == 0:
            continue
        mesh = bpy.data.meshes.new("M_" + key)
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new("O_" + key, mesh)
        bpy.context.scene.collection.objects.link(obj)
        if key in MATS:
            obj.data.materials.append(MATS[key])
    BUCKETS.clear()


# ---------------------------------------------------------------- 基础几何
def add_box(bm, dims, loc, rot_z=0.0):
    m = (Matrix.Translation(Vector(loc))
         @ Matrix.Rotation(rot_z, 4, "Z")
         @ Matrix.Diagonal(Vector((dims[0], dims[1], dims[2], 1.0))))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def add_cyl(bm, radius, height, loc, axis="Z", seg=20, rot_z=0.0):
    m = Matrix.Translation(Vector(loc)) @ Matrix.Rotation(rot_z, 4, "Z")
    if axis == "Y":
        m = m @ Matrix.Rotation(math.pi / 2.0, 4, "X")
    elif axis == "X":
        m = m @ Matrix.Rotation(math.pi / 2.0, 4, "Y")
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=radius, radius2=radius, depth=height, matrix=m)


def add_ico(bm, radius, loc, subdiv=2, scale=(1.0, 1.0, 1.0)):
    m = (Matrix.Translation(Vector(loc))
         @ Matrix.Diagonal(Vector((scale[0] * radius, scale[1] * radius,
                                   scale[2] * radius, 1.0))))
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0, matrix=m)


def add_box_m(bm, dims, matrix):
    bmesh.ops.create_cube(bm, size=1.0, matrix=matrix @ Matrix.Diagonal(
        Vector((dims[0], dims[1], dims[2], 1.0))))


def moon_gate_frame(bm, cx, y, z, r=1.42, tube=0.11, thickness=0.16, seg=22):
    """月洞门木色窗套：XZ 平面内的圆环管道（法向为 Y）。"""
    for k in range(seg):
        a = 2.0 * math.pi * k / seg
        t = Vector((-math.sin(a), 0.0, math.cos(a)))     # 切向（XZ 平面）
        rvec = Vector((math.cos(a), 0.0, math.sin(a)))   # 径向（XZ 平面，与切向正交）
        rot = Matrix(((t.x, 0.0, rvec.x), (t.y, 1.0, rvec.y),
                      (t.z, 0.0, rvec.z))).to_4x4()
        center = Vector((cx, y, z)) + rvec * r
        chord = 2.0 * r * math.sin(math.pi / seg) * 1.06
        add_box_m(bm, (chord, thickness, 2.0 * tube),
                  Matrix.Translation(center) @ rot)


def perforated_plate(bm, w, h, thickness, loc, rot_z, holes, step=0.32):
    """带圆孔的板（用于月洞门墙）。holes = [(cx, cy, r), ...]，坐标为板局部坐标。"""
    nx = max(6, int(w / step))
    ny = max(6, int(h / step))
    base = Matrix.Translation(Vector(loc)) @ Matrix.Rotation(rot_z, 4, "Z")

    def local_to_world(x, y, z):
        return (base @ Vector((x, y, z))).to_tuple()

    def project(x, y):
        for (cx, cy, r) in holes:
            dx, dy = x - cx, y - cy
            d = math.hypot(dx, dy)
            if d < r:
                if d < 1e-6:
                    return x, y, True
                k = r / d
                return cx + dx * k, cy + dy * k, True
        return x, y, False

    # 正反两面
    for sign in (1.0, -1.0):
        grid = []
        for j in range(ny + 1):
            row = []
            for i in range(nx + 1):
                x = -w / 2.0 + w * i / nx
                y = -h / 2.0 + h * j / ny
                px, py, _ = project(x, y)
                v = bm.verts.new(local_to_world(px, py, sign * thickness / 2.0))
                row.append(v)
            grid.append(row)
        bm.verts.ensure_lookup_table()
        for j in range(ny):
            for i in range(nx):
                a, b = grid[j][i], grid[j][i + 1]
                c, d = grid[j + 1][i + 1], grid[j + 1][i]
                # 判断格子中心是否落在孔内部（孔内则不生成面）
                cx = -w / 2.0 + w * (i + 0.5) / nx
                cy = -h / 2.0 + h * (j + 0.5) / ny
                inside = False
                for (hx, hy, r) in holes:
                    if math.hypot(cx - hx, cy - hy) < r * 0.97:
                        inside = True
                        break
                if inside:
                    continue
                if sign > 0:
                    bm.faces.new((a, b, c, d))
                else:
                    bm.faces.new((d, c, b, a))
    # 孔壁
    seg = 28
    for (cx, cy, r) in holes:
        ring_a, ring_b = [], []
        for k in range(seg):
            ang = 2.0 * math.pi * k / seg
            x = cx + r * math.cos(ang)
            y = cy + r * math.sin(ang)
            ring_a.append(bm.verts.new(local_to_world(x, y, thickness / 2.0)))
            ring_b.append(bm.verts.new(local_to_world(x, y, -thickness / 2.0)))
        for k in range(seg):
            k2 = (k + 1) % seg
            bm.faces.new((ring_a[k], ring_a[k2], ring_b[k2], ring_b[k]))


# ---------------------------------------------------------------- 中式构件
def roof_surface(bm, width, depth, ridge_h, eave_h, lift, thickness=0.16,
                 loc=(0.0, 0.0, 0.0), rot_z=0.0, nx=10, ny=8):
    """中式反曲（举折）双坡屋面：脊高 ridge_h，檐口 eave_h，檐端上翘 lift。"""
    base = Matrix.Translation(Vector(loc)) @ Matrix.Rotation(rot_z, 4, "Z")

    def height(t):
        return ridge_h - (ridge_h - eave_h) * (t ** 1.25) + lift * (t ** 4.0)

    half_w = width / 2.0
    grid = []
    for j in range(ny + 1):
        row = []
        for i in range(2 * nx + 1):
            t = abs(i - nx) / float(nx)          # 0 = 脊, 1 = 檐
            x = (i - nx) / float(nx) * half_w
            y = -depth / 2.0 + depth * j / ny
            z = height(t)
            row.append(bm.verts.new((base @ Vector((x, y, z))).to_tuple()))
        grid.append(row)
    bm.verts.ensure_lookup_table()
    faces = []
    for j in range(ny):
        for i in range(2 * nx):
            faces.append(bm.faces.new((grid[j][i], grid[j][i + 1],
                                       grid[j + 1][i + 1], grid[j + 1][i])))
    try:
        bmesh.ops.solidify(bm, geom=faces, thickness=thickness)
    except Exception as e:
        print("[solidify warn]", e)
    # 正脊
    add_box(bm, (0.34, depth + 0.25, 0.26),
            (base @ Vector((0.0, 0.0, ridge_h + 0.10))).to_tuple(), rot_z)
    # 檐口压边
    for sx in (-1.0, 1.0):
        add_box(bm, (0.30, depth + 0.25, 0.18),
                (base @ Vector((sx * (half_w - 0.06), 0.0, eave_h + lift * 0.6))).to_tuple(),
                rot_z)
    # 瓦垄：沿进深方向、从脊到檐均匀排列
    for i in range(2 * nx + 1):
        t = abs(i - nx) / float(nx)
        x = (i - nx) / float(nx) * half_w
        add_box(bm, (0.055, depth + 0.18, 0.07),
                (base @ Vector((x, 0.0, height(t) + 0.045))).to_tuple())


def lattice_window(bm, w, h, loc, rot_z, wood_key="wood", n=3, bar=0.07):
    """漏窗：外框 + 内部栅格（天然镂空，无需布尔）。"""
    t = 0.14
    add_box(bm, (w, t, h), (loc[0], loc[1], loc[2] + h / 2.0 - t / 2.0), rot_z)
    add_box(bm, (w, t, h), (loc[0], loc[1], loc[2] - h / 2.0 + t / 2.0), rot_z)
    add_box(bm, (t, t, h - 2 * t), (loc[0] - w / 2.0 + t / 2.0, loc[1], loc[2]), rot_z)
    add_box(bm, (t, t, h - 2 * t), (loc[0] + w / 2.0 - t / 2.0, loc[1], loc[2]), rot_z)
    for k in range(1, n):
        x = -w / 2.0 + w * k / n
        add_box(bm, (bar, bar, h - 2 * t), (loc[0] + x, loc[1], loc[2]), rot_z)
        y = -h / 2.0 + h * k / n
        add_box(bm, (w - 2 * t, bar, bar), (loc[0], loc[1], loc[2] + y), rot_z)


def column_row(bm, x0, y0, x1, y1, count, z=0.0, h=3.0, r=0.16):
    for k in range(count):
        t = 0.0 if count == 1 else k / float(count - 1)
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        add_cyl(bm, r, h, (x, y, z + h / 2.0), axis="Z", seg=12)
        add_cyl(bm, r * 1.35, 0.18, (x, y, z + 0.09), axis="Z", seg=12)  # 柱础


def taihu_rock(bm, loc, scale=1.0, subdiv=3, seed=0):
    """太湖石：icosphere + 多频湍流位移，取『瘦皱漏透』意象。"""
    rnd = random.Random(seed)
    before = len(bm.verts)
    m = (Matrix.Translation(Vector(loc))
         @ Matrix.Diagonal(Vector((1.15 * scale, 0.95 * scale, 1.35 * scale, 1.0))))
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0, matrix=m)
    for v in list(bm.verts[before:]):
        co = v.co.copy()
        n1 = noise.turbulence(co * 1.6 + Vector((seed * 3.1, seed * 1.7, 0.0)), 3, False)
        n2 = noise.turbulence(co * 4.2, 4, False)
        amp = 0.42 + 0.30 * n2
        v.co = co + co.normalized() * (n1 - 0.35) * amp
        v.co.z *= 1.0 + 0.35 * n1
    bm.verts.ensure_lookup_table()
    bm.normal_update()


def arched_bridge(bm, center, length, width, rise, rot_z=0.0):
    """引静桥意象：微拱石桥。"""
    n = 9
    for k in range(n):
        t = (k + 0.5) / n - 0.5
        x = t * length
        z = rise * (1.0 - (2.0 * t) ** 2)
        add_box(bm, (length / n * 0.95, width, 0.16),
                (center[0] + x * math.cos(rot_z),
                 center[1] + x * math.sin(rot_z),
                 center[2] + z), rot_z)
    for sx in (-1.0, 1.0):
        add_box(bm, (0.12, width, 0.55),
                (center[0] + sx * length / 2.0 * math.cos(rot_z),
                 center[1] + sx * length / 2.0 * math.sin(rot_z),
                 center[2] + 0.22), rot_z)


# ---------------------------------------------------------------- 场景装配
def build_walkway():
    """月洞门前石板路：主厅南面正对门洞铺一排石板伸向池岸，
    给用户『出门有路』的视觉引导（Blender 坐标，门在 x=2，岸在 y≈6.3）。"""
    bm_s = bucket("stone")
    for k in range(6):
        add_box(bm_s, (2.6, 0.5, 0.05), (2.0, 6.5 - k * 0.75, 0.025))


def build_ground():
    bm_s = bucket("stone")
    bm_w = bucket("white_wall")
    # 地面
    add_box(bm_s, (CFG["ground_half_x"] * 2.0, CFG["ground_half_y"] * 2.0, 0.2),
            (0.0, 0.0, -0.1))
    # 池岸条石
    px, py = CFG["pool_center"]
    pw, pd = CFG["pool_size"]
    for side in range(4):
        if side == 0:
            add_box(bm_s, (pw + 1.2, 0.6, 0.26), (px, py + pd / 2.0 + 0.3, 0.13))
        elif side == 1:
            add_box(bm_s, (pw + 1.2, 0.6, 0.26), (px, py - pd / 2.0 - 0.3, 0.13))
        elif side == 2:
            add_box(bm_s, (0.6, pd + 1.2, 0.26), (px + pw / 2.0 + 0.3, py, 0.13))
        else:
            add_box(bm_s, (0.6, pd + 1.2, 0.26), (px - pw / 2.0 - 0.3, py, 0.13))
    # 院墙（外围粉墙）
    gx, gy = CFG["ground_half_x"], CFG["ground_half_y"]
    for (cx, cy, w, d) in ((0.0, gy, gx * 2.0, 0.4), (0.0, -gy, gx * 2.0, 0.4),
                           (gx, 0.0, 0.4, gy * 2.0), (-gx, 0.0, 0.4, gy * 2.0)):
        add_box(bm_w, (w, d, 3.6), (cx, cy, 1.8))
        add_box(bm_w, (w + 0.25, d + 0.25, 0.16), (cx, cy, 3.66))  # 墙帽


def build_water():
    px, py = CFG["pool_center"]
    pw, pd = CFG["pool_size"]
    bm = bucket("water")
    # 微起伏水面（网格 + 湍流位移），模拟微重力池面的缓慢涌动
    m = (Matrix.Translation((px, py, CFG["water_z"]))
         @ Matrix.Diagonal((pw / 2.0, pd / 2.0, 1.0, 1.0)))
    bmesh.ops.create_grid(bm, x_segments=44, y_segments=34, size=1.0, matrix=m)
    for v in bm.verts:
        v.co.z += 0.055 * noise.turbulence(v.co * 0.7, 2, False)
        v.co.z += 0.020 * noise.turbulence(v.co * 2.2, 2, False)
    bm.normal_update()
    # 池底
    bucket("stone")
    add_box(BUCKETS["stone"], (pw, pd, 0.08), (px, py, -0.02))


def build_main_hall():
    """S3 主厅（万卷堂 / 看松读画轩意象）：面阔 12、进深 8，南向月洞门对舷窗。"""
    cx, cy = 2.0, 10.0
    w, d, h = 12.0, 8.0, 3.4
    bm_w, bm_d, bm_t = bucket("white_wall"), bucket("wood"), bucket("tile")
    # 台基
    add_box(bm_s := bucket("stone"), (w + 2.0, d + 1.6, 0.45), (cx, cy, 0.22))
    # 柱（北面 5 根；南面只留角柱，让开中央月洞门）
    column_row(bm_d, cx - w / 2.0, cy + d / 2.0, cx + w / 2.0, cy + d / 2.0, 5, 0.45, h)
    for sx in (-1.0, 1.0):
        px_ = cx + sx * (w / 2.0 - 0.35)
        add_cyl(bm_d, 0.16, h, (px_, cy - d / 2.0 + 0.3, 0.45 + h / 2.0), axis="Z", seg=12)
        add_cyl(bm_d, 0.22, 0.18, (px_, cy - d / 2.0 + 0.3, 0.54), axis="Z", seg=12)
    # 檐下枋（一圈横梁，强化中式木构）
    add_box(bm_d, (w + 0.3, 0.24, 0.30), (cx, cy - d / 2.0 + 0.1, h + 0.28))
    add_box(bm_d, (w + 0.3, 0.24, 0.30), (cx, cy + d / 2.0 - 0.1, h + 0.28))
    add_box(bm_d, (0.24, d + 0.3, 0.30), (cx - w / 2.0 + 0.1, cy, h + 0.28))
    add_box(bm_d, (0.24, d + 0.3, 0.30), (cx + w / 2.0 - 0.1, cy, h + 0.28))
    # 三面墙（南面留月洞门墙）
    add_box(bm_w, (w, 0.35, h), (cx, cy + d / 2.0, h / 2.0 + 0.45))
    add_box(bm_w, (0.35, d, h), (cx - w / 2.0, cy, h / 2.0 + 0.45))
    add_box(bm_w, (0.35, d, h), (cx + w / 2.0, cy, h / 2.0 + 0.45))
    # 南面月洞门墙（圆孔居中）＋ 木色窗套圆环
    perforated_plate(bm_w, w, h, 0.35, (cx, cy - d / 2.0, h / 2.0 + 0.45), 0.0,
                     holes=[(0.0, 0.0, 1.42)])
    moon_gate_frame(bm_d, cx, cy - d / 2.0, h / 2.0 + 0.45)
    # 屋面
    roof_surface(bm_t, w + 2.6, d + 2.6, h + 2.5, h + 0.55, 0.42,
                 loc=(cx, cy, 0.45 + h), thickness=0.18)
    # 匾额灯（自发光）
    add_box(bucket("glow"), (2.6, 0.10, 0.5), (cx, cy + d / 2.0 - 0.22, h + 0.55))


def build_corridor():
    """S2 曲廊：门厅到主厅的折廊，一侧漏窗序列（即舱体观察窗）。"""
    bm_w, bm_d, bm_t = bucket("white_wall"), bucket("wood"), bucket("tile")
    segs = [((-16.0, 4.0), (-14.0, -4.0)),
            ((-14.0, -4.0), (-6.0, -6.0)),
            ((-6.0, -6.0), (-4.6, 1.0))]
    for (p0, p1) in segs:
        (x0, y0), (x1, y1) = p0, p1
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        ang = math.atan2(dy, dx)
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        # 柱列（两侧）
        ncol = max(2, int(length / 2.4))
        for k in range(ncol):
            t = k / float(max(1, ncol - 1))
            bx = x0 + dx * t
            by = y0 + dy * t
            nx_, ny_ = -math.sin(ang), math.cos(ang)
            for sx in (-1.0, 1.0):
                add_cyl(bm_d, 0.14, 2.9,
                        (bx + nx_ * sx * 1.1, by + ny_ * sx * 1.1, 1.45), axis="Z", seg=10)
        # 一侧墙 + 漏窗（窗沿法向外凸 0.15，避免与墙体穿模）
        nx_, ny_ = -math.sin(ang), math.cos(ang)
        for k in range(4):
            t = (k + 0.5) / 4.0
            wx = x0 + dx * t + nx_ * 1.15
            wy = y0 + dy * t + ny_ * 1.15
            add_box(bm_w, (length / 4.0 * 0.55, 0.22, 2.9), (wx, wy, 1.45), ang)
            lattice_window(bm_d, 1.1, 1.5, (wx + nx_ * 0.16, wy + ny_ * 0.16, 1.60), ang)
        # 廊顶
        roof_surface(bm_t, 2.9, length, 3.55, 2.95, 0.22,
                     loc=(mx, my, 0.0), rot_z=ang - math.pi / 2.0, thickness=0.12)
        # 灯带
        add_box(bucket("glow"), (length * 0.9, 0.06, 0.06), (mx, my, 2.80), ang)


def build_pavilion(cx, cy, radius=2.2, name="月到风来亭"):
    """攒尖顶亭（六角）。"""
    bm_d, bm_t = bucket("wood"), bucket("tile")
    sides = 6
    for k in range(sides):
        ang = 2.0 * math.pi * k / sides
        add_cyl(bm_d, 0.13, 2.8,
                (cx + radius * math.cos(ang), cy + radius * math.sin(ang), 1.40),
                axis="Z", seg=10)
    # 攒尖顶：用锥体近似 + 起翘
    bmesh.ops.create_cone(bm_t, cap_ends=False, cap_tris=False, segments=sides,
                          radius1=radius + 0.9, radius2=0.12, depth=2.0,
                          matrix=Matrix.Translation((cx, cy, 3.75)))
    add_cyl(bm_t, 0.10, 0.35, (cx, cy, 4.82), axis="Z", seg=8)
    add_cyl(bucket("stone"), radius + 0.4, 0.30, (cx, cy, 0.15), axis="Z", seg=sides)


def build_waterside_pavilion():
    """濯缨水阁：临水小阁。"""
    cx, cy = -3.2, -8.0
    bm_d, bm_t, bm_w = bucket("wood"), bucket("tile"), bucket("white_wall")
    w, d, h = 5.0, 4.0, 2.9
    add_box(bucket("stone"), (w + 1.2, d + 1.2, 0.35), (cx, cy, 0.18))
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            add_cyl(bm_d, 0.14, h, (cx + sx * w / 2.0, cy + sy * d / 2.0, h / 2.0 + 0.35),
                    axis="Z", seg=10)
    add_box(bm_w, (w, 0.3, h), (cx, cy - d / 2.0, h / 2.0 + 0.35))
    add_box(bm_w, (0.3, d, h), (cx - w / 2.0, cy, h / 2.0 + 0.35))
    roof_surface(bm_t, w + 1.6, d + 1.6, h + 2.0, h + 0.45, 0.32,
                 loc=(cx, cy, 0.35 + h), thickness=0.14)


def build_dianchunyi():
    """S5 殿春簃庭院：生态维生舱，冷泉 + 湖石 + 半亭 + 植物。"""
    cx, cy = -13.0, -12.0
    bm_w, bm_d, bm_t = bucket("white_wall"), bucket("wood"), bucket("tile")
    w, d, h = 9.0, 8.0, 3.0
    add_box(bucket("stone"), (w + 1.6, d + 1.6, 0.40), (cx, cy, 0.20))
    column_row(bm_d, cx - w / 2.0, cy + d / 2.0, cx + w / 2.0, cy + d / 2.0, 4, 0.40, h)
    add_box(bm_w, (w, 0.32, h), (cx, cy + d / 2.0, h / 2.0 + 0.40))
    add_box(bm_w, (0.32, d, h), (cx - w / 2.0, cy, h / 2.0 + 0.40))
    # 东面开敞（朝庭院），西面漏窗
    lattice_window(bm_d, 1.6, 1.8, (cx + w / 2.0, cy - 2.0, 1.55), math.pi / 2.0, n=4)
    roof_surface(bm_t, w + 2.0, d + 2.0, h + 2.1, h + 0.45, 0.34,
                 loc=(cx, cy, 0.40 + h), thickness=0.15)
    # 冷泉
    add_cyl(bucket("water"), 0.85, 0.12, (cx - 2.0, cy - 1.6, 0.46), axis="Z", seg=16)
    add_cyl(bucket("stone"), 0.95, 0.35, (cx - 2.0, cy - 1.6, 0.30), axis="Z", seg=16)
    # 湖石
    taihu_rock(bucket("rock"), (cx + 2.4, cy - 2.2, 1.15), scale=1.5, seed=1)
    taihu_rock(bucket("rock"), (cx - 3.0, cy + 1.4, 0.85), scale=1.0, seed=2)
    # 半亭
    build_pavilion(cx + 3.4, cy + 2.6, radius=1.5)
    # 植物（低模）
    bm_p = bucket("plant")
    for k in range(14):
        px = cx - w / 2.0 + random.uniform(0.4, w - 0.4)
        py = cy - d / 2.0 + random.uniform(0.4, d - 0.4)
        if math.hypot(px - (cx - 2.0), py - (cy - 1.6)) < 1.4:
            continue
        add_ico(bm_p, random.uniform(0.35, 0.75), (px, py, random.uniform(0.5, 1.4)),
                subdiv=1, scale=(1.0, 1.0, 0.8))


def build_entry():
    """S1 门厅 + 气闸舱（抑）。"""
    cx, cy = -19.0, 6.0
    bm_w, bm_d, bm_t, bm_h = (bucket("white_wall"), bucket("wood"),
                              bucket("tile"), bucket("hull_dark"))
    w, d, h = 6.0, 5.0, 3.0
    add_box(bucket("stone"), (w + 1.4, d + 1.4, 0.35), (cx, cy, 0.18))
    for sx in (-1.0, 1.0):
        add_box(bm_w, (0.32, d, h), (cx + sx * w / 2.0, cy, h / 2.0 + 0.35))
    add_box(bm_w, (w, 0.32, h), (cx, cy + d / 2.0, h / 2.0 + 0.35))
    # 北墙开朱门（门厅与内院之间的墙门）＋ 木门框
    for sx in (-1.0, 1.0):
        add_box(bm_w, (1.85, 0.32, h), (cx + sx * 2.07, cy + d / 2.0, h / 2.0 + 0.35))
    for sx in (-1.0, 1.0):
        add_box(bm_d, (0.16, 0.42, h + 0.35),
                (cx + sx * 1.2, cy + d / 2.0, (h + 0.35) / 2.0 + 0.35))
    add_box(bm_d, (2.56, 0.42, 0.18), (cx, cy + d / 2.0, h + 0.62))
    # 门洞（两侧墙垛）
    for sx in (-1.0, 1.0):
        add_box(bm_w, (1.6, 0.32, h), (cx + sx * 2.2, cy - d / 2.0, h / 2.0 + 0.35))
    roof_surface(bm_t, w + 1.8, d + 1.8, h + 2.0, h + 0.45, 0.30,
                 loc=(cx, cy, 0.35 + h), thickness=0.14)
    # 气闸舱构件
    add_box(bm_h, (w + 1.0, 0.35, 3.6), (cx, cy - d / 2.0 - 0.6, 1.8))
    add_box(bucket("glow"), (w + 0.6, 0.05, 0.05), (cx, cy - d / 2.0 - 0.6, 3.35))
    # 砖雕门楼意象（简化为叠涩）
    for k in range(3):
        add_box(bm_d, (4.4 - k * 0.5, 0.30, 0.22),
                (cx, cy - d / 2.0 - 0.35, 2.55 + k * 0.28))


def build_hull():
    """轨道舱：圆筒内壁 + 结构环梁 + 舷窗屏 + 星幕 + 地球。"""
    R = CFG["hull_radius"]
    zc = CFG["hull_axis_z"]
    L = CFG["hull_half_len"]
    bm_h, bm_d = bucket("hull"), bucket("hull_dark")
    # 内壁（近似圆筒，沿 X 轴）
    seg = 48
    for k in range(seg):
        a0 = 2.0 * math.pi * k / seg
        a1 = 2.0 * math.pi * (k + 1) / seg
        y0, z0 = R * math.cos(a0), zc + R * math.sin(a0)
        y1, z1 = R * math.cos(a1), zc + R * math.sin(a1)
        if z0 < -0.3 or z1 < -0.3:       # 地面以下不生成
            continue
        if min(z0, z1) > 29.0:           # 顶部开环形天窗带，露出星幕
            continue
        for sx in (-1.0, 1.0):
            pass
        bm_h.verts.new((-L, y0, z0))
        bm_h.verts.new((L, y0, z0))
        bm_h.verts.new((L, y1, z1))
        bm_h.verts.new((-L, y1, z1))
    verts = bm_h.verts[:]
    n = len(verts)
    bm_h.verts.ensure_lookup_table()
    for i in range(0, n - 3, 4):
        bm_h.faces.new((verts[i + 3], verts[i + 2], verts[i + 1], verts[i]))
    # 结构环梁
    for x in range(-int(L) + 6, int(L), 8):
        for k in range(36):
            a0 = 2.0 * math.pi * k / 36
            y0, z0 = R * math.cos(a0), zc + R * math.sin(a0)
            if z0 < 0.6:
                continue
            add_box(bm_d, (0.55, 0.55, 0.55), (x, y0, z0))
    # 端封（气闸门所在端）
    add_box(bm_h, (0.6, R * 1.7, R * 1.7), (-L - 0.3, 0.0, zc * 0.75))
    add_box(bm_h, (0.6, R * 1.7, R * 1.7), (L + 0.3, 0.0, zc * 0.75))

    # 舷窗屏（自发光圆盘，朝向舱内）
    bm_s = bucket("screen")
    windows = [
        (3.5, -23.0, 7.5, 3.8, 0.0),
        (10.0, 21.5, 7.5, 3.6, math.pi),
        (-12.0, 21.5, 7.0, 3.2, math.pi),
        (-13.0, -21.5, 6.5, 3.0, 0.0),
        (2.0, 21.0, 12.0, 3.0, math.pi),
    ]
    for (wx, wy, wz, r, rot) in windows:
        add_cyl(bm_s, r, 0.16, (wx, wy, wz), axis="Y", seg=28)
        moon_gate_frame(bm_d, wx, wy, wz, r=r + 0.34, tube=0.14, thickness=0.34)

    # 星幕（大球，法线朝内）
    bm_sp = bucket("space")
    bmesh.ops.create_icosphere(bm_sp, subdivisions=3, radius=260.0,
                               matrix=Matrix.Translation((0.0, 0.0, 40.0)))
    for f in bm_sp.faces:
        f.normal_flip()
    bm_sp.normal_update()
    # 星点
    bm_st = bucket("star")
    rnd = random.Random(7)
    for k in range(260):
        u = rnd.uniform(-1.0, 1.0)
        phi = rnd.uniform(0.0, 2.0 * math.pi)
        s = math.sqrt(max(0.0, 1.0 - u * u))
        r = 250.0
        add_ico(bm_st, rnd.uniform(0.6, 1.6),
                (r * s * math.cos(phi), r * s * math.sin(phi), 40.0 + r * u), subdiv=0)
    # 地球
    add_ico(bucket("earth"), 34.0, (2.0, -150.0, 95.0), subdiv=4)


def build_rocks_and_plants():
    """池边湖石与点缀植物。"""
    px, py = CFG["pool_center"]
    spots = [(px - 7.5, py + 5.0, 1.0), (px + 6.5, py - 4.6, 0.9),
             (px + 8.0, py + 4.0, 1.2), (px - 6.0, py - 5.2, 0.75)]
    for k, (x, y, s) in enumerate(spots):
        taihu_rock(bucket("rock"), (x, y, 0.9 * s), scale=s * 1.3, seed=10 + k)
    bm_p = bucket("plant")
    for k in range(18):
        ang = 2.0 * math.pi * k / 18.0
        rr = 1.15
        add_ico(bm_p, random.uniform(0.3, 0.6),
                (px + (CFG["pool_size"][0] / 2.0 + rr) * math.cos(ang),
                 py + (CFG["pool_size"][1] / 2.0 + rr) * math.sin(ang),
                 random.uniform(0.4, 1.1)), subdiv=1, scale=(1.0, 1.0, 0.85))


def set_world():
    """深空微光环境，避免金属舱壁全黑。"""
    scene = bpy.context.scene
    world = bpy.data.worlds.new("DeepSpace")
    scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs[0].default_value = (0.010, 0.014, 0.024, 1.0)
        bg_node.inputs[1].default_value = 1.0


def add_light(kind, loc, energy, color=(1.0, 1.0, 1.0), size=None, name=None):
    bpy.ops.object.light_add(type=kind, location=loc)
    light = bpy.context.active_object
    if name:
        light.name = name
    light.data.energy = energy
    light.data.color = color
    if kind == "AREA" and size:
        light.data.size = size
    return light


def build_camera_and_lights():
    # 灯光仅用于 Blender 内预览；网页端由 Three.js 自行布光
    add_light("SUN", (8.0, -30.0, 30.0), 3.2, (0.92, 0.95, 1.0), name="Starlight")
    add_light("AREA", (2.0, 8.0, 9.0), 900.0, (0.85, 0.92, 1.0), size=16.0, name="Skylight")
    # 室内暖光
    add_light("POINT", (2.0, 10.0, 3.1), 160.0, (1.0, 0.82, 0.6), name="HallWarm")
    add_light("POINT", (-13.0, -12.0, 2.9), 110.0, (1.0, 0.82, 0.6), name="DcyWarm")
    add_light("POINT", (-19.0, 6.0, 2.8), 70.0, (1.0, 0.85, 0.65), name="EntryWarm")
    add_light("POINT", (-10.0, -5.0, 2.6), 45.0, (1.0, 0.85, 0.65), name="CorrWarmA")
    add_light("POINT", (-5.0, 5.0, 2.6), 45.0, (1.0, 0.85, 0.65), name="CorrWarmB")
    add_light("POINT", (-13.0, -2.0, 2.6), 40.0, (1.0, 0.85, 0.65), name="CorrWarmC")
    add_light("POINT", (-15.0, 0.0, 2.5), 40.0, (1.0, 0.85, 0.65), name="CorrWarmD")
    add_light("POINT", (-11.0, -10.0, 2.4), 90.0, (1.0, 0.84, 0.62), name="DcyYard")
    # 池面月光（冷）
    add_light("POINT", (6.0, 0.0, 7.0), 320.0, (0.62, 0.78, 1.0), name="PoolMoon")
    add_light("POINT", (12.0, -6.5, 3.4), 60.0, (0.75, 0.85, 1.0), name="PavilionCool")
    set_world()

    cam = bpy.data.cameras.new("TourCam")
    cam.clip_end = 800.0
    obj = bpy.data.objects.new("TourCam", cam)
    obj.location = (-19.0, 6.0, 1.65)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.camera = obj


# ---------------------------------------------------------------- 锚点
ANCHORS = [
    {"id": "S1", "title": "门厅 · 抑",
     "sub": "网师园门厅 / 砖雕门楼",
     "text": "入口刻意低矮封闭，视线被压缩——中国园林以『抑』开篇。轨道语境下，这里是气闸舱与编号标识：WSY-01，网师园，已编号拆解。",
     "pos": (-19.0, 6.0, 1.6), "radius": 5.5},
    {"id": "S2", "title": "曲廊 · 过渡",
     "sub": "网师园复廊 / 漏窗序列",
     "text": "狭长折廊，一侧漏窗透出断续的光。漏窗在此即舱体观察窗阵列：星光被窗棂切成纹样——『框景』在轨道条件下仍然成立。",
     "pos": (-10.0, 0.0, 1.6)},
    {"id": "S3", "title": "主厅 · 扬",
     "sub": "万卷堂 / 看松读画轩",
     "text": "空间豁然开敞，正面月洞门框住一幅景。而门后已无园外——月洞门就是舷窗，借进来的是地球与星海。这便是『借星』。",
     "pos": (2.0, 8.0, 1.6), "radius": 7.6},
    {"id": "S4", "title": "彩霞池 · 高潮",
     "sub": "彩霞池 / 月到风来亭 / 濯缨水阁 / 引静桥",
     "text": "环池一周，移步换景。微重力下水面缓慢上浮，池面倒映的不是天光云影，而是星象——『以小见大』在有限舱容里被重新验证。",
     "pos": (6.0, -3.5, 1.6), "radius": 10.5},
    {"id": "S5", "title": "殿春簃 · 余韵",
     "sub": "殿春簃 / 冷泉 / 湖石 / 半亭",
     "text": "全舱唯一的生态维生舱，真实绿植与活水。殿春簃早在 1980 年就被复制进纽约大都会（明轩）——八百年后，人类第二次搬走它，这一次搬向轨道。",
     "pos": (-13.0, -12.0, 1.6), "radius": 6.5},
]


def write_anchors():
    """Blender (Z-up) -> glTF (Y-up)：gx=x, gy=z, gz=-y"""
    data = []
    for a in ANCHORS:
        x, y, z = a["pos"]
        data.append({"id": a["id"], "title": a["title"], "sub": a["sub"],
                     "text": a["text"], "pos": [x, z, -y],
                     "radius": a.get("radius", 5.0)})
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"anchors": data,
                   "spawn": [2.0, 1.65, -8.0],
                   "bounds": {"min_y": 0.0, "max_y": 6.0,
                              "half_x": CFG["ground_half_x"] - 1.0,
                              "half_z": CFG["ground_half_y"] - 1.0}},
                  f, ensure_ascii=False, indent=2)
    print("[ok] anchors ->", OUT_JSON)


# ---------------------------------------------------------------- 主流程
def build_all():
    """只构建场景，不做导出。供渲染预览脚本复用。"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    init_materials()
    build_ground()
    build_water()
    build_walkway()
    build_entry()
    build_corridor()
    build_main_hall()
    build_pavilion(12.0, -10.5, radius=2.2)
    build_waterside_pavilion()
    arched_bridge(bucket("stone"), (11.5, -3.5, 0.7), 13.4, 1.5, 0.5, rot_z=math.pi / 2.0)
    build_dianchunyi()
    build_rocks_and_plants()
    build_hull()
    flush_buckets()
    build_camera_and_lights()


def main():
    build_all()

    # 统计
    total_faces = sum(len(o.data.polygons) for o in bpy.context.scene.objects
                      if o.type == "MESH")
    print("[info] mesh objects:",
          len([o for o in bpy.context.scene.objects if o.type == "MESH"]),
          "faces:", total_faces)

    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
        print("[ok] blend ->", OUT_BLEND)
    except Exception as e:
        print("[warn] 保存 .blend 失败（不影响 GLB 交付）：", e)

    os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)
    try:
        bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format="GLB",
                                  export_apply=True, export_lights=False)
    except TypeError:
        bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format="GLB")
    print("[ok] glb ->", OUT_GLB, os.path.getsize(OUT_GLB) // 1024, "KB")

    write_anchors()


if __name__ == "__main__":
    main()
