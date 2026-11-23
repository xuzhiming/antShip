import bpy
import math
import os
import time
import numpy as np

TEX_DIR = '/Users/xzm/Downloads/antShip/textures'
REND_DIR = '/Users/xzm/Downloads/antShip/renders'
BLEND_PATH = '/Users/xzm/Downloads/antShip/starship_v1.blend'

EXT_PAINTED = [
    'Hull_Outer', 'Arch_RearLower', 'Fin_Dorsal', 'Fin_Ventral',
    'Fin_VentralFront', 'Fin_BellyRear',
    'Prong_Side', 'Spike_TopRear',
    'Engine_C_Nacelle', 'Engine_L_Nacelle', 'Engine_R_Nacelle',
    'EyePod_L', 'EyePod_R',
]


def kill_obj(name):
    o = bpy.data.objects.get(name)
    if not o:
        return
    d = o.data
    bpy.data.objects.remove(o, do_unlink=True)
    if d and d.users == 0:
        if isinstance(d, bpy.types.Mesh):
            bpy.data.meshes.remove(d)
        elif isinstance(d, bpy.types.Curve):
            bpy.data.curves.remove(d)


# 1. Ensure intact cutaway & remove procedural ornaments that clash with HD art
plane = bpy.data.objects.get('CUTAWAY_Plane')
if plane:
    plane.location = (0.0, 0.0, 1000.0)
    plane.rotation_euler = (0.0, 0.0, 0.0)

for nm in (
    'Spike_Spine_0', 'Spike_Spine_1', 'Spike_Spine_2', 'Spike_Spine_3',
    'GoldTrim_FinDorsal', 'GoldTrim_ProngSide', 'GoldTrim_FinVentral', 'GoldTrim_ArchRear',
    'Conduit_FinDorsal', 'Conduit_ProngSide', 'Conduit_FinVentral',
):
    kill_obj(nm)

# 2. Ensure modifiers applied & smooth shading on EXT_PAINTED
bpy.ops.object.select_all(action='DESELECT')
painted_objs = []
for nm in EXT_PAINTED:
    o = bpy.data.objects.get(nm)
    if not o or o.type != 'MESH':
        print("Warning missing EXT_PAINTED:", nm)
        continue
    o.hide_set(False)
    o.hide_viewport = False
    o.hide_render = False
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    for mod in list(o.modifiers):
        if mod.type == 'SUBSURF':
            mod.levels = 1
            mod.render_levels = 1
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        except Exception as e:
            print(f"Modifier apply warning on {nm}.{mod.name}: {e}")
    o.select_set(False)
    for p in o.data.polygons:
        p.use_smooth = True
    if not o.data.uv_layers:
        o.data.uv_layers.new(name='UVMap')
    painted_objs.append(o)

# Remove ALL old exterior materials & images so zero previous textures remain
for o in painted_objs:
    o.data.materials.clear()

for mname in ('M_Hull_Plated', 'M_Hull_Iridescent', 'M_Exterior_Ref', 'M_RefBake_Tmp', 'M_Exterior_HD', 'M_HDBake_Tmp'):
    m = bpy.data.materials.get(mname)
    if m:
        bpy.data.materials.remove(m, do_unlink=True)

for img in list(bpy.data.images):
    if img.name.startswith(('ref_', 'exterior_', 'hd_')):
        bpy.data.images.remove(img, do_unlink=True)

bpy.ops.outliner.orphans_purge(do_recursive=True)
print("Cleaned old exterior materials/images.")

# 3. Re-pack shared UV atlas cleanly across all 15 EXT_PAINTED objects
bpy.ops.object.select_all(action='DESELECT')
for o in painted_objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects['Hull_Outer']
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003, scale_to_bounds=True)
bpy.ops.object.mode_set(mode='OBJECT')
print("Smart UV projected", len(painted_objs), "objects.")

# 4. Build 6-view directional projection shader M_HDBake_Tmp
def load_hd_img(fname):
    img = bpy.data.images.load(os.path.join(TEX_DIR, fname), check_existing=False)
    img.colorspace_settings.name = 'sRGB'
    return img

img_left   = load_hd_img('hd_left.png')
img_right  = load_hd_img('hd_right.png')
img_top    = load_hd_img('hd_top.png')
img_bottom = load_hd_img('hd_bottom.png')
img_front  = load_hd_img('hd_front.png')
img_rear   = load_hd_img('hd_rear.png')

bake_mat = bpy.data.materials.new('M_HDBake_Tmp')
bake_mat.use_nodes = True
nt = bake_mat.node_tree
nt.nodes.clear()
N = nt.nodes; Lk = nt.links

out = N.new('ShaderNodeOutputMaterial'); out.location = (1300, 0)
emit = N.new('ShaderNodeEmission'); emit.location = (1100, 0); emit.inputs['Strength'].default_value = 1.0
Lk.new(emit.outputs['Emission'], out.inputs['Surface'])

geom = N.new('ShaderNodeNewGeometry'); geom.location = (-1500, 200)
sep_p = N.new('ShaderNodeSeparateXYZ'); sep_p.location = (-1250, 420)
Lk.new(geom.outputs['Position'], sep_p.inputs['Vector'])

def map_coord(src_sock, vmin, vmax, y_loc):
    mr = N.new('ShaderNodeMapRange')
    mr.clamp = True
    mr.inputs['From Min'].default_value = vmin
    mr.inputs['From Max'].default_value = vmax
    mr.inputs['To Min'].default_value = 0.0
    mr.inputs['To Max'].default_value = 1.0
    mr.location = (-1000, y_loc)
    Lk.new(src_sock, mr.inputs['Value'])
    return mr.outputs['Result']

ux = map_coord(sep_p.outputs['X'], -48.2, 76.2, 680)
uy = map_coord(sep_p.outputs['Y'], -24.2, 24.2, 460)
uz = map_coord(sep_p.outputs['Z'], -22.5, 23.0, 240)

def inv_coord(src_sock, x_loc, y_loc):
    sub = N.new('ShaderNodeMath'); sub.operation = 'SUBTRACT'; sub.inputs[0].default_value = 1.0
    sub.location = (x_loc, y_loc)
    Lk.new(src_sock, sub.inputs[1])
    return sub.outputs['Value']

inv_uy = inv_coord(uy, -760, 120)

def sample_view(img, u_sock, v_sock, x_loc, y_loc):
    comb = N.new('ShaderNodeCombineXYZ'); comb.location = (x_loc - 220, y_loc)
    Lk.new(u_sock, comb.inputs['X'])
    Lk.new(v_sock, comb.inputs['Y'])
    tex = N.new('ShaderNodeTexImage'); tex.image = img
    tex.extension = 'EXTEND'; tex.interpolation = 'Cubic'
    tex.location = (x_loc, y_loc)
    Lk.new(comb.outputs['Vector'], tex.inputs['Vector'])
    return tex.outputs['Color']

c_left   = sample_view(img_left,   ux, uz, -340, 860)
c_right  = sample_view(img_right,  ux, uz, -340, 580)
c_top    = sample_view(img_top,    ux, uy, -340, 300)
c_bottom = sample_view(img_bottom, ux, inv_uy, -340, 20)
c_front  = sample_view(img_front,  uy, uz, -340, -260)
c_rear   = sample_view(img_rear,   inv_uy, uz, -340, -540)

# 6-way normal weights (^6)
sep_n = N.new('ShaderNodeSeparateXYZ'); sep_n.location = (-1250, -520)
Lk.new(geom.outputs['Normal'], sep_n.inputs['Vector'])

def pow6_dir(sock, negate, y_loc):
    s = sock
    if negate:
        ng = N.new('ShaderNodeMath'); ng.operation = 'MULTIPLY'; ng.inputs[1].default_value = -1.0; ng.location = (-1040, y_loc)
        Lk.new(sock, ng.inputs[0]); s = ng.outputs['Value']
    mx = N.new('ShaderNodeMath'); mx.operation = 'MAXIMUM'; mx.inputs[1].default_value = 0.0; mx.location = (-880, y_loc)
    Lk.new(s, mx.inputs[0])
    pw = N.new('ShaderNodeMath'); pw.operation = 'POWER'; pw.inputs[1].default_value = 6.0; pw.location = (-700, y_loc)
    Lk.new(mx.outputs['Value'], pw.inputs[0])
    return pw.outputs['Value']

w_left   = pow6_dir(sep_n.outputs['Y'], True,  -360)  # -Y
w_right  = pow6_dir(sep_n.outputs['Y'], False, -520)  # +Y
w_top    = pow6_dir(sep_n.outputs['Z'], False, -680)  # +Z
w_bottom = pow6_dir(sep_n.outputs['Z'], True,  -840)  # -Z
w_front  = pow6_dir(sep_n.outputs['X'], True,  -1000) # -X
w_rear   = pow6_dir(sep_n.outputs['X'], False, -1160) # +X

def add_f(a, b, loc):
    n = N.new('ShaderNodeMath'); n.operation = 'ADD'; n.location = loc
    Lk.new(a, n.inputs[0]); Lk.new(b, n.inputs[1])
    return n.outputs['Value']

w_lr = add_f(w_left, w_right, (-460, -440))
w_tb = add_f(w_top, w_bottom, (-460, -760))
w_fr = add_f(w_front, w_rear, (-460, -1080))
w_s1 = add_f(w_lr, w_tb, (-260, -600))
w_s2 = add_f(w_s1, w_fr, (-80, -800))
w_eps = N.new('ShaderNodeMath'); w_eps.operation = 'ADD'; w_eps.inputs[1].default_value = 1e-5; w_eps.location = (100, -800)
Lk.new(w_s2, w_eps.inputs[0])
w_sum = w_eps.outputs['Value']

def scale_col(col_sock, w_sock, loc):
    vm = N.new('ShaderNodeVectorMath'); vm.operation = 'SCALE'; vm.location = loc
    Lk.new(col_sock, vm.inputs[0]); Lk.new(w_sock, vm.inputs['Scale'])
    return vm.outputs['Vector']

def add_col(a, b, loc):
    vm = N.new('ShaderNodeVectorMath'); vm.operation = 'ADD'; vm.location = loc
    Lk.new(a, vm.inputs[0]); Lk.new(b, vm.inputs[1])
    return vm.outputs['Vector']

sc_l = scale_col(c_left,   w_left,   (60, 820))
sc_r = scale_col(c_right,  w_right,  (60, 560))
sc_t = scale_col(c_top,    w_top,    (60, 300))
sc_b = scale_col(c_bottom, w_bottom, (60, 40))
sc_f = scale_col(c_front,  w_front,  (60, -220))
sc_x = scale_col(c_rear,   w_rear,   (60, -480))

sum_lr = add_col(sc_l, sc_r, (280, 680))
sum_tb = add_col(sc_t, sc_b, (280, 160))
sum_fx = add_col(sc_f, sc_x, (280, -340))
sum_4  = add_col(sum_lr, sum_tb, (500, 420))
sum_6  = add_col(sum_4, sum_fx, (700, 100))

inv_w = N.new('ShaderNodeMath'); inv_w.operation = 'DIVIDE'; inv_w.inputs[0].default_value = 1.0; inv_w.location = (500, -800)
Lk.new(w_sum, inv_w.inputs[1])

norm_col = scale_col(sum_6, inv_w.outputs['Value'], (900, 0))
Lk.new(norm_col, emit.inputs['Color'])

# 5. Bake 4096x4096 EMIT to hd_exterior_albedo.png
SIZE = 4096
albedo_path = os.path.join(TEX_DIR, 'hd_exterior_albedo.png')
albedo_img = bpy.data.images.new('hd_exterior_albedo.png', width=SIZE, height=SIZE, alpha=False)
albedo_img.colorspace_settings.name = 'sRGB'
albedo_img.filepath_raw = albedo_path
albedo_img.file_format = 'PNG'

bake_target = N.new('ShaderNodeTexImage'); bake_target.image = albedo_img; bake_target.location = (1100, -340)
N.active = bake_target

for o in painted_objs:
    o.data.materials.append(bake_mat)

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = 4
sc.cycles.use_denoising = False
sc.render.bake.use_selected_to_active = False
sc.render.bake.margin = 24
sc.render.bake.margin_type = 'EXTEND'

bpy.ops.object.select_all(action='DESELECT')
for o in painted_objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects['Hull_Outer']

t0 = time.time()
bpy.ops.object.bake(type='EMIT', use_clear=True)
albedo_img.save()
print(f"Baked 4K hd_exterior_albedo.png in {time.time() - t0:.1f}s")

# 6. Derive crisp 4K Emissive, Metallic, Roughness, and OpenGL Tangent Normal Maps
px_lin = np.empty(SIZE * SIZE * 4, dtype=np.float32)
albedo_img.pixels.foreach_get(px_lin)
lin = px_lin.reshape((SIZE, SIZE, 4))[:, :, :3]

def lin_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * (x ** (1.0 / 2.4)) - 0.055)

def srgb_to_lin(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

def save_np_img(name, fname, rgb_01, colorspace):
    path = os.path.join(TEX_DIR, fname)
    im_out = bpy.data.images.new(name, width=SIZE, height=SIZE, alpha=False)
    im_out.colorspace_settings.name = colorspace
    im_out.filepath_raw = path
    im_out.file_format = 'PNG'
    rgba = np.ones((SIZE, SIZE, 4), dtype=np.float32)
    rgba[:, :, :3] = srgb_to_lin(rgb_01) if colorspace == 'sRGB' else np.clip(rgb_01, 0.0, 1.0)
    im_out.pixels.foreach_set(rgba.ravel())
    im_out.save()
    return im_out

srgb = lin_to_srgb(lin) * 255.0
R = srgb[:, :, 0]; G = srgb[:, :, 1]; B = srgb[:, :, 2]
lum = (0.299 * R + 0.587 * G + 0.114 * B) / 255.0

cyan_score = np.clip((B - 155.0) / 55.0, 0.0, 1.0) * np.clip((G - 145.0) / 55.0, 0.0, 1.0) * np.clip(((B - R) - 45.0) / 45.0, 0.0, 1.0)
red_score  = np.clip((R - 170.0) / 50.0, 0.0, 1.0) * np.clip(((R - G) - 65.0) / 45.0, 0.0, 1.0) * np.clip(((R - B) - 45.0) / 40.0, 0.0, 1.0)
emit_srgb = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
emit_srgb[:, :, 0] = np.clip(cyan_score * 0.18 + red_score * 1.00, 0.0, 1.0)
emit_srgb[:, :, 1] = np.clip(cyan_score * 0.90 + red_score * 0.08, 0.0, 1.0)
emit_srgb[:, :, 2] = np.clip(cyan_score * 1.00 + red_score * 0.12, 0.0, 1.0)

gold_mask = np.clip(((R - B) - 20.0) / 32.0, 0.0, 1.0) * np.clip((R - 90.0) / 60.0, 0.0, 1.0)
emit_mask = np.maximum(cyan_score, red_score)
crev_mask = np.clip((0.20 - lum) / 0.16, 0.0, 1.0) * (1.0 - emit_mask)

# Balanced PBR metallic & roughness (keep rich HD art colors faithful without grey wash-out)
metallic = 0.35 * (1.0 - gold_mask) + 0.88 * gold_mask
metallic = metallic * (1.0 - crev_mask) + 0.10 * crev_mask
metallic = metallic * (1.0 - emit_mask)
metallic = np.clip(metallic, 0.0, 1.0)

roughness = 0.42 * (1.0 - gold_mask) + 0.28 * gold_mask
roughness = roughness * (1.0 - crev_mask) + 0.72 * crev_mask
roughness = roughness * (1.0 - emit_mask) + 0.15 * emit_mask
roughness = np.clip(roughness, 0.10, 0.88)

# Sculpted tangent-space Normal Map
H = 0.45 * lum + 0.45 * gold_mask - 0.35 * crev_mask
Hp = np.pad(H, 1, mode='edge')
Hs = (
    Hp[:-2, :-2] + Hp[:-2, 1:-1] + Hp[:-2, 2:]
    + Hp[1:-1, :-2] + 2.0 * Hp[1:-1, 1:-1] + Hp[1:-1, 2:]
    + Hp[2:, :-2] + Hp[2:, 1:-1] + Hp[2:, 2:]
) / 10.0
Hsp = np.pad(Hs, 1, mode='edge')
dh_du = ((Hsp[:-2, 2:] + 2.0 * Hsp[1:-1, 2:] + Hsp[2:, 2:]) - (Hsp[:-2, :-2] + 2.0 * Hsp[1:-1, :-2] + Hsp[2:, :-2])) / 8.0
dh_dv = ((Hsp[2:, :-2] + 2.0 * Hsp[2:, 1:-1] + Hsp[2:, 2:]) - (Hsp[:-2, :-2] + 2.0 * Hsp[:-2, 1:-1] + Hsp[:-2, 2:])) / 8.0

strength = 3.5
nx = -dh_du * strength
ny = -dh_dv * strength
nz = np.ones_like(nx)
inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
normal_rgb = np.stack([0.5 + 0.5 * nx * inv_len, 0.5 + 0.5 * ny * inv_len, 0.5 + 0.5 * nz * inv_len], axis=-1)

img_emissive  = save_np_img('hd_exterior_emissive.png',  'hd_exterior_emissive.png',  emit_srgb, 'sRGB')
img_metallic  = save_np_img('hd_exterior_metallic.png',  'hd_exterior_metallic.png',  np.repeat(metallic[:, :, None], 3, axis=2), 'Non-Color')
img_roughness = save_np_img('hd_exterior_roughness.png', 'hd_exterior_roughness.png', np.repeat(roughness[:, :, None], 3, axis=2), 'Non-Color')
img_normal    = save_np_img('hd_exterior_normal.png',    'hd_exterior_normal.png',    normal_rgb, 'Non-Color')
print("Derived 4K HD emissive, metallic, roughness, normal maps.")

# 7. Build M_Exterior_HD + CUT_Mix cutaway hook
ext_mat = bpy.data.materials.new('M_Exterior_HD')
ext_mat.use_nodes = True
nt = ext_mat.node_tree
nt.nodes.clear()
N = nt.nodes; Lk = nt.links

out = N.new('ShaderNodeOutputMaterial'); out.location = (700, 0)
bsdf = N.new('ShaderNodeBsdfPrincipled'); bsdf.location = (180, 0)
for cname in ('Coat Weight', 'Clearcoat'):
    if cname in bsdf.inputs:
        bsdf.inputs[cname].default_value = 0.20
        break
if 'Emission Strength' in bsdf.inputs:
    bsdf.inputs['Emission Strength'].default_value = 3.0

def add_tex(img, y_loc):
    t = N.new('ShaderNodeTexImage'); t.image = img; t.location = (-420, y_loc)
    return t

t_alb = add_tex(albedo_img, 420)
t_met = add_tex(img_metallic, 160)
t_rgh = add_tex(img_roughness, -100)
t_nrm = add_tex(img_normal, -360)
t_emt = add_tex(img_emissive, -620)

Lk.new(t_alb.outputs['Color'], bsdf.inputs['Base Color'])
Lk.new(t_met.outputs['Color'], bsdf.inputs['Metallic'])
Lk.new(t_rgh.outputs['Color'], bsdf.inputs['Roughness'])

nmap = N.new('ShaderNodeNormalMap'); nmap.inputs['Strength'].default_value = 1.0; nmap.location = (-100, -360)
Lk.new(t_nrm.outputs['Color'], nmap.inputs['Color'])
Lk.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])

for ec_name in ('Emission Color', 'Emission'):
    if ec_name in bsdf.inputs:
        Lk.new(t_emt.outputs['Color'], bsdf.inputs[ec_name])
        break

if plane:
    tc = N.new('ShaderNodeTexCoord'); tc.object = plane; tc.name = 'CUT_Coord'; tc.location = (-100, -760)
    sep = N.new('ShaderNodeSeparateXYZ'); sep.location = (80, -760)
    gt = N.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.0; gt.location = (240, -760)
    tr = N.new('ShaderNodeBsdfTransparent'); tr.location = (240, -560)
    mix = N.new('ShaderNodeMixShader'); mix.name = 'CUT_Mix'; mix.location = (460, 0)
    Lk.new(tc.outputs['Object'], sep.inputs['Vector'])
    Lk.new(sep.outputs['Z'], gt.inputs[0])
    Lk.new(gt.outputs['Value'], mix.inputs['Fac'])
    Lk.new(bsdf.outputs['BSDF'], mix.inputs[1])
    Lk.new(tr.outputs['BSDF'], mix.inputs[2])
    Lk.new(mix.outputs['Shader'], out.inputs['Surface'])
    try:
        ext_mat.surface_render_method = 'DITHERED'
    except Exception:
        pass
else:
    Lk.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

for o in painted_objs:
    o.data.materials.clear()
    o.data.materials.append(ext_mat)

# Remove temporary bake material and 6 view source images from .blend
bpy.data.materials.remove(bake_mat, do_unlink=True)
for tmp_img in (img_left, img_right, img_top, img_bottom, img_front, img_rear):
    bpy.data.images.remove(tmp_img, do_unlink=True)
bpy.ops.outliner.orphans_purge(do_recursive=True)

# 8. Re-render hero, rear, side_cutaway & top_cutaway, restore settings & save .blend
sc.cycles.samples = 48
sc.cycles.use_denoising = True
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA'

cut_jobs = [
    ((0.0, 0.0, 1000.0), (0.0, 0.0, 0.0),       'Camera_Hero',    'hero_exterior.png'),
    ((0.0, 0.0, 1000.0), (0.0, 0.0, 0.0),       'Camera_Rear',    'rear_engines.png'),
    ((0.0, 0.96, 0.0),   (math.pi / 2, 0.0, 0.0), 'Camera_SideCut', 'side_cutaway.png'),
    ((0.0, 0.0, 2.55),   (0.0, 0.0, 0.0),       'Camera_TopCut',  'top_cutaway.png'),
]
for cloc, crot, cam_name, out_name in cut_jobs:
    if plane:
        plane.location = cloc
        plane.rotation_euler = crot
    sc.camera = bpy.data.objects[cam_name]
    sc.render.filepath = os.path.join(REND_DIR, out_name)
    bpy.ops.render.render(write_still=True)
    print("Rendered:", out_name)

if plane:
    plane.location = (0.0, 0.0, 1000.0)
    plane.rotation_euler = (0.0, 0.0, 0.0)
sc.camera = bpy.data.objects['Camera_Hero']
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.cycles.samples = 128
bpy.ops.wm.save_mainfile(filepath=BLEND_PATH)
print("Saved blend with 4K M_Exterior_HD:", BLEND_PATH, "images:", [i.name for i in bpy.data.images])
