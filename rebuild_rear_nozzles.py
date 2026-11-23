import bpy
import bmesh
import math
import os
from mathutils import Vector, Euler

TEX_DIR = '/Users/xzm/Downloads/antShip/textures'
REND_DIR = '/Users/xzm/Downloads/antShip/renders'
BLEND_PATH = '/Users/xzm/Downloads/antShip/starship_v1.blend'


def link_only(ob, c):
    for u in list(ob.users_collection):
        u.objects.unlink(ob)
    c.objects.link(ob)
    return ob


def kill_obj(o):
    d = o.data
    bpy.data.objects.remove(o, do_unlink=True)
    if d and d.users == 0:
        if isinstance(d, bpy.types.Mesh):
            bpy.data.meshes.remove(d)
        elif isinstance(d, bpy.types.Curve):
            bpy.data.curves.remove(d)


def set_in(node, names, val):
    for nm in names:
        if nm in node.inputs:
            node.inputs[nm].default_value = val
            return True
    return False


def hook_cutaway(mat, plane):
    if not plane or not mat or not mat.use_nodes:
        return
    nt = mat.node_tree
    if any(n.name == 'CUT_Mix' for n in nt.nodes):
        return
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if not out or not out.inputs['Surface'].links:
        return
    src = out.inputs['Surface'].links[0].from_socket
    N = nt.nodes; Lk = nt.links
    tc = N.new('ShaderNodeTexCoord'); tc.object = plane; tc.name = 'CUT_Coord'; tc.location = out.location + Vector((-600, -300))
    sep = N.new('ShaderNodeSeparateXYZ'); sep.location = out.location + Vector((-400, -300))
    gt = N.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.0; gt.location = out.location + Vector((-250, -300))
    tr = N.new('ShaderNodeBsdfTransparent'); tr.location = out.location + Vector((-250, -150))
    mix = N.new('ShaderNodeMixShader'); mix.name = 'CUT_Mix'; mix.location = out.location + Vector((-100, 0))
    Lk.new(tc.outputs['Object'], sep.inputs['Vector'])
    Lk.new(sep.outputs['Z'], gt.inputs[0])
    Lk.new(gt.outputs['Value'], mix.inputs['Fac'])
    Lk.new(src, mix.inputs[1])
    Lk.new(tr.outputs['BSDF'], mix.inputs[2])
    Lk.new(mix.outputs['Shader'], out.inputs['Surface'])
    out.location.x += 150
    try:
        mat.surface_render_method = 'DITHERED'
    except Exception:
        pass


def make_simple_mat(name, base_col, metal=0.0, rough=0.3, emit_col=None, emit_str=0.0, plane=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes; Lk = nt.links
    out = N.new('ShaderNodeOutputMaterial'); out.location = (300, 0)
    p = N.new('ShaderNodeBsdfPrincipled'); p.location = (0, 0)
    p.inputs['Base Color'].default_value = (*base_col, 1.0)
    p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = rough
    if emit_col is not None:
        set_in(p, ('Emission Color', 'Emission'), (*emit_col, 1.0))
        set_in(p, ('Emission Strength',), emit_str)
    Lk.new(p.outputs['BSDF'], out.inputs['Surface'])
    m.diffuse_color = (*base_col, 1.0)
    hook_cutaway(m, plane)
    return m


def make_face_mat(name, face_file, emit_file, plane):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes; Lk = nt.links
    out = N.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    p = N.new('ShaderNodeBsdfPrincipled'); p.location = (80, 0)
    p.inputs['Metallic'].default_value = 0.65
    p.inputs['Roughness'].default_value = 0.35
    set_in(p, ('Emission Strength',), 2.8)

    img_f = bpy.data.images.load(os.path.join(TEX_DIR, face_file), check_existing=True)
    img_f.colorspace_settings.name = 'sRGB'
    img_e = bpy.data.images.load(os.path.join(TEX_DIR, emit_file), check_existing=True)
    img_e.colorspace_settings.name = 'sRGB'

    tf = N.new('ShaderNodeTexImage'); tf.image = img_f; tf.location = (-320, 180)
    te = N.new('ShaderNodeTexImage'); te.image = img_e; te.location = (-320, -140)
    Lk.new(tf.outputs['Color'], p.inputs['Base Color'])
    for ec_name in ('Emission Color', 'Emission'):
        if ec_name in p.inputs:
            Lk.new(te.outputs['Color'], p.inputs[ec_name])
            break
    Lk.new(p.outputs['BSDF'], out.inputs['Surface'])
    hook_cutaway(m, plane)
    return m


plane = bpy.data.objects.get('CUTAWAY_Plane')
if plane:
    plane.location = (0.0, 0.0, 1000.0)
    plane.rotation_euler = (0.0, 0.0, 0.0)

# 1. Create dedicated nozzle materials
mat_cyan    = make_simple_mat('M_NozzleCyan',    (0.01, 0.72, 0.95), metal=0.0, rough=0.18, emit_col=(0.02, 0.86, 1.0), emit_str=5.5, plane=plane)
mat_hotcore = make_simple_mat('M_NozzleHotCore', (0.85, 0.98, 1.00), metal=0.0, rough=0.12, emit_col=(0.78, 0.98, 1.0), emit_str=14.0, plane=plane)
mat_purple  = make_simple_mat('M_NozzlePurple',  (0.14, 0.07, 0.28), metal=0.75, rough=0.34, plane=plane)
mat_face_c  = make_face_mat('M_NozzleFace_C', 'nozzle_face_center.png', 'nozzle_emit_center.png', plane)
mat_face_s  = make_face_mat('M_NozzleFace_S', 'nozzle_face_side.png',   'nozzle_emit_side.png',   plane)

mat_gold = bpy.data.materials['M_Gold']
mat_dark = bpy.data.materials['M_DarkMetal']

# 2. Remove old Engine_* nozzle components (preserve Engine_*_Nacelle & EyePod_*)
C_eng = bpy.data.collections['Engines']
for o in list(C_eng.objects):
    if o.name.startswith('Engine_') and not o.name.endswith('_Nacelle'):
        kill_obj(o)

# Helpers for smooth primitives & revolved cowlings
def make_mesh_ob(name, verts, faces, mat, uvs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate(); me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    if uvs is not None:
        uv_layer = me.uv_layers.new(name='UVMap')
        for poly in me.polygons:
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                uv_layer.data[li].uv = uvs[vi]
    me.update()
    ob = bpy.data.objects.new(name, me)
    C_eng.objects.link(ob)
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def add_revolved_profile(name, center_x, yc, zc, profile_xr, mat, segs=64):
    """Revolve list of (dx_from_xe, radius) around X axis."""
    verts = []; faces = []
    for (dx, r) in profile_xr:
        px = center_x + dx
        for i in range(segs):
            a = 2.0 * math.pi * i / segs
            verts.append((px, yc + r * math.cos(a), zc + r * math.sin(a)))
    K = len(profile_xr)
    for k in range(K - 1):
        for i in range(segs):
            a = k * segs + i
            b = k * segs + (i + 1) % segs
            faces.append((a, b, b + segs, a + segs))
    return make_mesh_ob(name, verts, faces, mat)


def add_torus(name, loc, R, r, rot, mat, maj=56, mn=12):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=maj, minor_segments=mn, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name; link_only(o, C_eng); o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    return o


def add_arc_torus(name, x, yc, zc, R, r, ang_start, ang_end, mat, steps=24, mn=10):
    verts = []; faces = []
    for s in range(steps):
        u = s / (steps - 1)
        a = ang_start + (ang_end - ang_start) * u
        taper = math.sin(math.pi * u) ** 0.45
        rr = r * (0.35 + 0.65 * taper)
        cy = yc + R * math.cos(a)
        cz = zc + R * math.sin(a)
        for j in range(mn):
            b = 2.0 * math.pi * j / mn
            vy = cy + rr * math.cos(b) * math.cos(a)
            vz = cz + rr * math.cos(b) * math.sin(a)
            vx = x + rr * math.sin(b)
            verts.append((vx, vy, vz))
    for s in range(steps - 1):
        for j in range(mn):
            a0 = s * mn + j; b0 = s * mn + (j + 1) % mn
            faces.append((a0, b0, b0 + mn, a0 + mn))
    return make_mesh_ob(name, verts, faces, mat)


def add_radial_box(name, cx, yc, zc, r_mid, radial_len, tang_w, depth_x, ang, mat, tilt_ang=0.0):
    """Create a radial strut/vane/bar rotated to angle `ang` around X-axis, with optional vane pitch `tilt_ang`."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    o = bpy.context.active_object
    o.name = name
    link_only(o, C_eng)
    o.data.materials.append(mat)
    # Local cube: X=depth_x, Y=radial_len, Z=tang_w
    o.scale = (depth_x, radial_len, tang_w)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = o; o.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if abs(tilt_ang) > 1e-4:
        for v in o.data.vertices:
            y0, z0 = v.co.x, v.co.z
            c, s = math.cos(tilt_ang), math.sin(tilt_ang)
            v.co.x = y0 * c - z0 * s
            v.co.z = y0 * s + z0 * c
    # Rotate around X by `ang` (so local +Y points along radial (0, cos(ang), sin(ang)))
    o.rotation_euler = (ang, 0.0, 0.0)
    o.location = (cx, yc + r_mid * math.cos(ang), zc + r_mid * math.sin(ang))
    return o


# 3. Build 3 multi-layered rear exhaust nozzles
specs = [
    ('C',  0.0, 0.26, 3.60, 38.2, 8, mat_face_c),
    ('L',  8.2, 0.22, 3.25, 37.5, 4, mat_face_s),
    ('R', -8.2, 0.22, 3.25, 37.5, 4, mat_face_s),
]

for tag, yc, zc, R, xe, n_glow_pylons, face_mat in specs:
    prefix = f'Engine_{tag}'

    # A. Outer Stepped Cowling Shroud (deep purple-steel) & Twin Gold Bezels
    shroud_prof = [
        (-1.65, 1.00 * R),
        (-0.90, 1.12 * R),
        (-0.05, 1.10 * R),
        ( 0.08, 1.05 * R),
        ( 0.10, 0.96 * R),
        (-0.05, 0.93 * R),
        (-0.85, 0.92 * R),
    ]
    add_revolved_profile(f'{prefix}_Shroud', xe, yc, zc, shroud_prof, mat_purple, segs=64)

    add_torus(f'{prefix}_BezelOuter', (xe + 0.08, yc, zc), 1.03 * R, 0.048 * R, (0, math.radians(90), 0), mat_gold)
    add_torus(f'{prefix}_BezelInner', (xe + 0.04, yc, zc), 0.95 * R, 0.032 * R, (0, math.radians(90), 0), mat_gold)

    # Sculpted arched gold eyebrow trims hugging upper & lower saddle
    add_arc_torus(f'{prefix}_EyebrowTop', xe - 0.14, yc, zc, 1.11 * R, 0.048 * R, math.radians(28), math.radians(152), mat_gold)
    add_arc_torus(f'{prefix}_EyebrowBot', xe - 0.14, yc, zc, 1.11 * R, 0.042 * R, math.radians(212), math.radians(328), mat_gold)

    # 8 gold bezel flange lugs
    for k in range(8):
        ang = math.radians(22.5 + k * 45.0)
        ly = yc + 1.04 * R * math.cos(ang)
        lz = zc + 1.04 * R * math.sin(ang)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.042 * R, location=(xe + 0.10, ly, lz))
        lg = bpy.context.active_object; lg.name = f'{prefix}_Lug{k}'; lg.scale = (0.7, 1.0, 1.0)
        link_only(lg, C_eng); lg.data.materials.append(mat_gold)
        for p in lg.data.polygons: p.use_smooth = True

    # B. Recessed Outer Turbine Cavity Backplate Disc & 24 Stator Vanes
    # Textured circular disc at xe - 0.85 facing +X
    d_segs = 64
    r_disc = 0.94 * R
    d_verts = [(xe - 0.85, yc, zc)]
    d_uvs = [(0.5, 0.5)]
    for i in range(d_segs):
        a = 2.0 * math.pi * i / d_segs
        vy = yc + r_disc * math.cos(a)
        vz = zc + r_disc * math.sin(a)
        d_verts.append((xe - 0.85, vy, vz))
        # Rear view (+X looking toward -X): +Y is left (u=0), +Z is up (v=1)
        u = 0.5 - (vy - yc) / (2.0 * r_disc)
        v = 0.5 + (vz - zc) / (2.0 * r_disc)
        d_uvs.append((u, v))
    d_faces = [(0, i + 1, (i + 1) % d_segs + 1) for i in range(d_segs)]
    make_mesh_ob(f'{prefix}_FaceDisc', d_verts, d_faces, face_mat, uvs=d_uvs)

    # Stepped gunmetal outer turbine liner
    add_revolved_profile(f'{prefix}_CavityWall', xe, yc, zc, [(-0.86, 0.93 * R), (-0.42, 0.93 * R)], mat_dark, segs=64)

    # 24 angled radial stator vanes around r = 0.62R .. 0.92R
    for k in range(24):
        ang = 2.0 * math.pi * k / 24.0
        add_radial_box(
            f'{prefix}_Vane{k}', xe - 0.69, yc, zc,
            0.77 * R, 0.30 * R, 0.018 * R, 0.24, ang, mat_dark, tilt_ang=math.radians(28.0)
        )

    # Recessed thin gold conduit ring inside turbine cavity
    add_torus(f'{prefix}_CavityGoldRing', (xe - 0.60, yc, zc), 0.77 * R, 0.018 * R, (0, math.radians(90), 0), mat_gold)

    # C. Signature Radial Energy Pylons (8 glowing for C; 4 cardinal glowing + 4 diagonal struts for L/R)
    for k in range(8):
        ang = 2.0 * math.pi * k / 8.0
        is_cardinal = (k % 2 == 0)
        is_glowing = (n_glow_pylons == 8) or is_cardinal

        p_len = (0.39 * R) if is_cardinal else (0.36 * R)
        p_w   = (0.082 * R) if is_cardinal else (0.062 * R)
        p_rm  = 0.75 * R

        # Dark gunmetal channel housing
        add_radial_box(f'{prefix}_PylonHousing{k}', xe - 0.42, yc, zc, p_rm, p_len, p_w, 0.28, ang, mat_dark)
        # Flanking gold rail trims on both tangential sides of housing
        for side_t in (-1, 1):
            t_off = side_t * (p_w * 0.56)
            ry = yc + p_rm * math.cos(ang) - t_off * math.sin(ang)
            rz = zc + p_rm * math.sin(ang) + t_off * math.cos(ang)
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(xe - 0.38, ry, rz), rotation=(ang, 0.0, 0.0))
            rl = bpy.context.active_object; rl.name = f'{prefix}_PylonRail{k}_{side_t}'; link_only(rl, C_eng); rl.data.materials.append(mat_gold)
            rl.scale = (0.24, p_len * 0.96, 0.014 * R)

        if is_glowing:
            bar_w = (0.038 * R) if is_cardinal else (0.026 * R)
            add_radial_box(f'{prefix}_PylonGlow{k}', xe - 0.25, yc, zc, p_rm, p_len * 0.90, bar_w, 0.10, ang, mat_cyan)
        else:
            # Diagonal structural gold rib on side engines
            add_radial_box(f'{prefix}_PylonGoldBar{k}', xe - 0.27, yc, zc, p_rm, p_len * 0.88, 0.022 * R, 0.08, ang, mat_gold)

    # D. Mid Containment Collar & 16 Segmented Cyan Arc-Ticks (r = 0.47R .. 0.58R)
    add_torus(f'{prefix}_CollarDark', (xe - 0.32, yc, zc), 0.54 * R, 0.044 * R, (0, math.radians(90), 0), mat_dark)
    add_torus(f'{prefix}_CollarGold', (xe - 0.28, yc, zc), 0.51 * R, 0.024 * R, (0, math.radians(90), 0), mat_gold)

    for k in range(16):
        ang = math.radians(11.25 + k * 22.5)
        add_radial_box(f'{prefix}_ArcTick{k}', xe - 0.34, yc, zc, 0.475 * R, 0.038 * R, 0.048 * R, 0.09, ang, mat_cyan)

    # E. Deep Plasma Accelerator Funnel & Dual Cyan Plasma Rings (r = 0.25R .. 0.46R)
    funnel_prof = [
        (-0.44, 0.46 * R),
        (-1.15, 0.25 * R),
    ]
    add_revolved_profile(f'{prefix}_Funnel', xe, yc, zc, funnel_prof, mat_dark, segs=48)

    # 16 fine glowing cyan plasma ribs along the funnel slant
    for k in range(16):
        ang = 2.0 * math.pi * k / 16.0
        add_radial_box(f'{prefix}_FunnelRib{k}', xe - 0.78, yc, zc, 0.355 * R, 0.22 * R, 0.012 * R, 0.08, ang, mat_cyan, tilt_ang=0.0)

    add_torus(f'{prefix}_PlasmaRingOuter', (xe - 0.62, yc, zc), 0.41 * R, 0.019 * R, (0, math.radians(90), 0), mat_cyan)
    add_torus(f'{prefix}_PlasmaRingInner', (xe - 0.88, yc, zc), 0.30 * R, 0.017 * R, (0, math.radians(90), 0), mat_cyan)

    # F. Radiant Dual-Tone Plasma Core (outer aqua-cyan dome + inner hot white-cyan sphere)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.27 * R, location=(xe - 0.85, yc, zc))
    dome = bpy.context.active_object; dome.name = f'{prefix}_PlasmaDome'; dome.scale = (0.45, 1.0, 1.0)
    link_only(dome, C_eng); dome.data.materials.append(mat_cyan)
    for p in dome.data.polygons: p.use_smooth = True

    bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=14, radius=0.13 * R, location=(xe - 0.76, yc, zc))
    core = bpy.context.active_object; core.name = f'{prefix}_HotCore'; core.scale = (0.65, 1.0, 1.0)
    link_only(core, C_eng); core.data.materials.append(mat_hotcore)
    for p in core.data.polygons: p.use_smooth = True

print("Rebuilt multi-layered rear nozzles. Total Engines objects:", len(C_eng.objects))

# 4. Re-render rear_engines.png, hero_exterior.png, and close-up check
sc = bpy.context.scene
sc.cycles.samples = 48
sc.cycles.use_denoising = True
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'

for cam_name, out_name in (('Camera_Rear', 'rear_engines.png'), ('Camera_Hero', 'hero_exterior.png')):
    sc.camera = bpy.data.objects[cam_name]
    sc.render.filepath = os.path.join(REND_DIR, out_name)
    bpy.ops.render.render(write_still=True)
    print("Rendered:", out_name)

# Temporary close-up rear-3/4 check camera
cam_cu_data = bpy.data.cameras.new('Cam_RearCloseup_Tmp')
cam_cu_data.lens = 50
cam_cu = bpy.data.objects.new('Cam_RearCloseup_Tmp', cam_cu_data)
bpy.context.scene.collection.objects.link(cam_cu)
cam_cu.location = (56.0, -14.0, 4.5)
direction = Vector((38.0, 0.0, 0.25)) - cam_cu.location
cam_cu.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
sc.camera = cam_cu
sc.render.filepath = os.path.join(REND_DIR, 'rear_closeup_check.png')
bpy.ops.render.render(write_still=True)
print("Rendered: rear_closeup_check.png")

bpy.data.objects.remove(cam_cu, do_unlink=True)
bpy.data.cameras.remove(cam_cu_data)

# Restore final state & save .blend
sc.camera = bpy.data.objects['Camera_Hero']
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.cycles.samples = 128
if plane:
    plane.location = (0.0, 0.0, 1000.0)
    plane.rotation_euler = (0.0, 0.0, 0.0)
bpy.ops.wm.save_mainfile(filepath=BLEND_PATH)
print("Saved blend:", BLEND_PATH)
