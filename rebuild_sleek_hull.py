import bpy
import bmesh
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

BLEND_PATH = '/Users/xzm/Downloads/antShip/starship_v1.blend'


def get_coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


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


def make_mesh(name, verts, faces, c, mat=None, smooth=True, recalc_normals=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    if recalc_normals:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.update()
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    if mat:
        me.materials.append(mat)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return ob


def apply_mods(ob, subsurf_levels=None):
    ob.hide_set(False)
    ob.hide_viewport = False
    ob.hide_render = False
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    for mod in list(ob.modifiers):
        if mod.type == 'SUBSURF' and subsurf_levels is not None:
            mod.levels = subsurf_levels
            mod.render_levels = subsurf_levels
        bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.select_set(False)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def _cr_chain(P, steps):
    P = [Vector(p) for p in P]
    ext = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(len(P) - 1):
        for k in range(steps):
            t = k / steps
            p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return out


def blade_world(name, A, B, c, mat, thick=0.10, K=10, steps=6, mirror_y=False, tmin=0.06):
    SA = _cr_chain(A, steps)
    SB = _cr_chain(B, steps)
    M = len(SA)
    verts = []
    faces = []
    for j in range(M):
        a, b = SA[j], SB[j]
        ch = b - a
        L = ch.length
        sp = SA[min(j + 1, M - 1)] - SA[max(j - 1, 0)]
        n = ch.cross(sp)
        n = n.normalized() if n.length > 1e-6 else Vector((0, 1, 0))
        th = max(L * thick, tmin) * (1.0 - 0.85 * (j / (M - 1)) ** 2)
        ring = []
        for k in range(K):
            u = k / (K - 1)
            ring.append(a + ch * u + n * (th * (math.sin(math.pi * u) ** 0.8)))
        for k in range(K - 2, 0, -1):
            u = k / (K - 1)
            ring.append(a + ch * u - n * (th * (math.sin(math.pi * u) ** 0.8)))
        verts.extend(tuple(v) for v in ring)
    R = 2 * K - 2
    for j in range(M - 1):
        for i in range(R):
            p = j * R + i
            q = j * R + (i + 1) % R
            faces.append((p, q, q + R, p + R))
    faces.append(tuple(range(R - 1, -1, -1)))
    ob = make_mesh(name, verts, faces, c, mat)
    if mirror_y:
        m = ob.modifiers.new('MirrorY', 'MIRROR')
        m.use_axis[0] = False
        m.use_axis[1] = True
    sd = ob.modifiers.new('Subd', 'SUBSURF')
    sd.levels = 1
    sd.render_levels = 1
    return apply_mods(ob, subsurf_levels=1)


def tube_world(name, pts, radii, c, mat, N=24, steps=4, cap=False):
    P = [Vector(p) for p in pts]
    R = list(radii)
    ext = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    samples = []; rs = []
    for i in range(len(P) - 1):
        for k in range(steps):
            t = k / steps
            p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
            samples.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
            rs.append(R[i] * (1.0 - t) + R[i + 1] * t)
    samples.append(P[-1]); rs.append(R[-1])
    U = Vector((0, 0, 1))
    verts = []; faces = []
    M = len(samples)
    for j, p in enumerate(samples):
        tg = (samples[min(j + 1, M - 1)] - samples[max(j - 1, 0)]).normalized()
        side = tg.cross(U)
        if side.length < 1e-4:
            side = tg.cross(Vector((1, 0, 0)))
        side.normalize()
        nrm = side.cross(tg).normalized()
        r = max(rs[j], 0.0)
        for i in range(N):
            a = 2 * math.pi * i / N
            verts.append(tuple(p + side * (math.cos(a) * r) + nrm * (math.sin(a) * r)))
    for j in range(M - 1):
        for i in range(N):
            a = j * N + i
            b = j * N + (i + 1) % N
            faces.append((a, b, b + N, a + N))
    if cap:
        e = len(verts); verts.append(tuple(samples[0]))
        for i in range(N):
            faces.append((e, (i + 1) % N, i))
    ob = make_mesh(name, verts, faces, c, mat, recalc_normals=True)
    sd = ob.modifiers.new('Subd', 'SUBSURF')
    sd.levels = 1
    sd.render_levels = 1
    return apply_mods(ob, subsurf_levels=1)


# Materials
mat_ext = bpy.data.materials.get('M_Exterior_HD') or bpy.data.materials.new('M_Exterior_HD')
mat_gold = bpy.data.materials['M_Gold']
mat_glow = bpy.data.materials['M_GlowCyan']
mat_dark = bpy.data.materials['M_DarkMetal']

root = get_coll('Starship_V1')
C_ext = get_coll('Exterior', root)
C_fin = get_coll('Fins_Horns', C_ext)
C_eng = get_coll('Engines', C_ext)

# 1. Rebuild sleek Hull_Outer from exact HD silhouette measurements
old_hull = bpy.data.objects.get('Hull_Outer')
if old_hull:
    kill_obj(old_hull)

stations = [
    (-47.0,  0.55, -0.50,  0.55, 2.0, 0.15),
    (-44.0,  1.45, -1.10,  1.25, 2.0, 0.25),
    (-40.0,  2.55, -1.75,  2.05, 2.0, 0.35),
    (-35.5,  3.65, -2.35,  2.75, 2.1, 0.45),
    (-30.5,  4.85, -2.90,  3.45, 2.1, 0.50),
    (-25.5,  6.00, -3.40,  4.00, 2.1, 0.55),
    (-20.5,  7.10, -3.95,  4.65, 2.1, 0.60),
    (-15.5,  7.35, -4.25,  4.95, 2.1, 0.55),
    (-10.5,  8.20, -4.35,  5.25, 2.1, 0.60),
    ( -5.5,  9.50, -4.85,  5.65, 2.1, 0.65),
    ( -0.5, 10.60, -5.20,  5.55, 2.1, 0.65),
    (  4.5, 11.80, -5.75,  5.85, 2.2, 0.70),
    (  9.5, 12.80, -6.20,  8.20, 2.2, 0.90),
    ( 14.5, 13.60, -7.10, 10.80, 2.2, 1.10),
    ( 19.5, 13.90, -7.35, 10.60, 2.2, 1.00),
    ( 24.5, 13.50, -7.20,  9.80, 2.2, 0.80),
    ( 29.5, 12.60, -6.50,  8.40, 2.2, 0.50),
    ( 33.5, 11.40, -5.30,  6.20, 2.2, 0.30),
    ( 37.5,  9.80, -3.80,  4.20, 2.2, 0.10),
]

N = 64
verts = []
faces = []
for (wx, hw_y, z_bot, z_top, n_exp, ridge) in stations:
    z_mid = 0.5 * (z_top + z_bot)
    h_half = 0.5 * (z_top - z_bot)
    for i in range(N):
        a = 2.0 * math.pi * i / N
        c, s = math.cos(a), math.sin(a)
        y = hw_y * math.copysign(abs(c) ** (2.0 / n_exp), c)
        z = z_mid + h_half * math.copysign(abs(s) ** (2.0 / n_exp), s)
        if s > 0:
            z += ridge * (s ** 10)
        verts.append((wx, y, z))

S = len(stations)
for s_idx in range(S - 1):
    for i in range(N):
        a = s_idx * N + i
        b = s_idx * N + (i + 1) % N
        faces.append((a, b, b + N, a + N))

# Sharp closed nose tip & flat stern cap
nose_idx = len(verts)
verts.append((-48.2, 0.0, 0.0))
for i in range(N):
    faces.append((nose_idx, (i + 1) % N, i))

stern_idx = len(verts)
last = (S - 1) * N
verts.append((37.5, 0.0, 0.2))
for i in range(N):
    faces.append((stern_idx, last + i, last + (i + 1) % N))

hull = make_mesh('Hull_Outer', verts, faces, C_ext, mat_ext, smooth=True, recalc_normals=True)
sd = hull.modifiers.new('Subd', 'SUBSURF')
sd.levels = 1
sd.render_levels = 1
apply_mods(hull, subsurf_levels=1)
print("Rebuilt Hull_Outer dimensions:", tuple(round(d, 2) for d in hull.dimensions))

# 2. Rebuild Fins_Horns aligned to exact HD alpha landmarks
for o in list(C_fin.objects):
    kill_obj(o)

blade_world('Fin_Dorsal',
    [(15.0, 0, 9.8), (22.0, 0, 13.6), (29.0, 0, 17.8), (34.5, 0, 20.8), (39.0, 0, 22.7)],
    [(29.5, 0, 8.0), (31.5, 0, 11.4), (34.0, 0, 15.6), (36.8, 0, 19.6), (39.2, 0, 22.7)],
    C_fin, mat_ext, thick=0.07)

blade_world('Fin_Ventral',
    [(10.0, 0, -6.2), (13.5, 0, -10.5), (16.5, 0, -15.2), (18.4, 0, -19.2), (19.5, 0, -22.4)],
    [(24.0, 0, -7.0), (24.2, 0, -11.2), (23.2, 0, -15.6), (21.6, 0, -19.4), (19.7, 0, -22.4)],
    C_fin, mat_ext, thick=0.08)

blade_world('Fin_VentralFront',
    [(-9.0, 0, -4.2), (-6.2, 0, -6.4), (-3.6, 0, -9.0), (-1.0, 0, -11.3)],
    [(2.0, 0, -5.2), (1.4, 0, -7.2), (0.3, 0, -9.5), (-0.8, 0, -11.3)],
    C_fin, mat_ext, thick=0.08)

blade_world('Fin_BellyRear',
    [(14.0, 6.0, -4.8), (17.2, 7.4, -7.8), (19.8, 8.6, -11.2), (21.5, 9.4, -14.2)],
    [(25.0, 6.2, -5.8), (25.2, 7.6, -8.8), (24.0, 8.7, -11.8), (21.7, 9.4, -14.2)],
    C_fin, mat_ext, thick=0.09, mirror_y=True)

blade_world('Prong_Side',
    [(6.0, 11.8, 1.5), (18.0, 17.5, 4.5), (30.0, 21.0, 8.2), (42.0, 23.4, 11.8), (54.0, 24.2, 15.0), (65.0, 23.2, 16.5), (74.0, 20.0, 16.9)],
    [(22.0, 12.2, 1.5), (32.0, 14.5, 5.2), (41.0, 13.0, 9.2), (51.0, 18.2, 12.2), (61.0, 20.1, 14.6), (69.0, 20.2, 16.0), (74.2, 20.0, 16.9)],
    C_fin, mat_ext, thick=0.08, mirror_y=True)

blade_world('Spike_TopRear',
    [(22.0, 0, 9.8), (34.0, 0, 10.6), (48.0, 0, 12.6), (62.0, 0, 14.9), (76.2, 0, 16.9)],
    [(36.0, 0, 4.2), (43.0, 0, 6.2), (53.0, 0, 9.4), (65.0, 0, 13.0), (76.4, 0, 16.9)],
    C_fin, mat_ext, thick=0.14)

blade_world('Arch_RearLower',
    [(22.0, 10.2, -6.2), (34.0, 13.5, -5.2), (41.0, 16.6, -1.0), (48.0, 19.4, 5.8), (55.0, 21.2, 12.6)],
    [(26.5, 10.2, -7.2), (37.5, 13.3, -6.2), (44.0, 16.4, -2.0), (50.2, 19.2, 4.8), (56.5, 21.2, 12.2)],
    C_fin, mat_ext, thick=0.14, mirror_y=True)

print("Rebuilt Fins_Horns:", len(C_fin.objects))

# 3. Rebuild Engines & EyePod_L/R at exact HD coordinates
for o in list(C_eng.objects):
    kill_obj(o)

def add_torus(name, center, R, r, rot, mat, maj=40, mn=10):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=maj, minor_segments=mn, location=center, rotation=rot)
    o = bpy.context.active_object; o.name = name; link_only(o, C_eng); o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    return o

engines = [
    ('C',  0.0, 0.26, 3.1, 38.2),
    ('L',  8.7, 0.22, 2.5, 37.5),
    ('R', -8.7, 0.22, 2.5, 37.5),
]
for tag, y, z, r, xe in engines:
    xs = [22.0, 26.0, 30.0, 34.0, xe - 1.2, xe]
    rs = [r * 0.72, r * 0.96, r * 1.05, r * 1.10, r * 1.13, r * 1.15]
    pts = [(x, y * (0.82 if x < 26.0 else 1.0), z) for x in xs]
    tube_world(f'Engine_{tag}_Nacelle', pts, rs, C_eng, mat_ext, N=24, steps=4, cap=False)

    add_torus(f'Engine_{tag}_RimGold', (xe, y, z), r * 1.15, 0.30, (0, math.radians(90), 0), mat_gold)
    add_torus(f'Engine_{tag}_RimInner', (xe - 0.35, y, z), r * 0.85, 0.16, (0, math.radians(90), 0), mat_gold)

    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=r * 1.10, radius2=r * 0.68, depth=2.0, location=(xe - 1.0, y, z), rotation=(0, math.radians(90), 0))
    noz = bpy.context.active_object; noz.name = f'Engine_{tag}_Nozzle'; link_only(noz, C_eng); noz.data.materials.append(mat_dark)
    for p in noz.data.polygons: p.use_smooth = True

    bpy.ops.mesh.primitive_circle_add(vertices=40, radius=r * 0.78, fill_type='NGON', location=(xe - 0.18, y, z), rotation=(0, math.radians(90), 0))
    dsc = bpy.context.active_object; dsc.name = f'Engine_{tag}_Glow'; link_only(dsc, C_eng); dsc.data.materials.append(mat_glow)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=r * 0.35, location=(xe - 0.05, y, z))
    cor = bpy.context.active_object; cor.name = f'Engine_{tag}_Core'; cor.scale = (0.5, 1, 1); link_only(cor, C_eng); cor.data.materials.append(mat_glow)
    for p in cor.data.polygons: p.use_smooth = True

    add_torus(f'Engine_{tag}_InnerGlowRing', (xe - 0.02, y, z), r * 0.58, 0.11, (0, math.radians(90), 0), mat_glow)
    add_torus(f'Engine_{tag}_MidGoldRing',   (xe - 0.04, y, z), r * 0.64, 0.09, (0, math.radians(90), 0), mat_gold)

    r_in = r * 0.35; r_out = r * 1.10
    mid_r = 0.5 * (r_in + r_out); len_s = r_out - r_in
    for k in range(8):
        ang = 2 * math.pi * k / 8
        sy = y + math.cos(ang) * mid_r
        sz = z + math.sin(ang) * mid_r
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.09 if tag == 'C' else 0.07, depth=len_s, location=(xe - 0.08, sy, sz), rotation=(math.radians(90) - ang, 0, 0))
        sp = bpy.context.active_object; sp.name = f'Engine_{tag}_Spoke{k}'; link_only(sp, C_eng); sp.data.materials.append(mat_gold)
        for p in sp.data.polygons: p.use_smooth = True

    for k in range(3):
        bx = 27.5 + k * 3.5
        add_torus(f'Engine_{tag}_Band{k}', (bx, y, z), r * (1.03 + 0.03 * k), 0.15, (0, math.radians(90), 0), mat_gold, maj=32, mn=8)

# Side Eye-Pods at X=22.5, Y=±12.8, Z=1.3
for side in (1, -1):
    tag = 'L' if side > 0 else 'R'
    cy = side * 12.8
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0, location=(22.5, cy, 1.3))
    ep = bpy.context.active_object; ep.name = f'EyePod_{tag}'; ep.scale = (4.5, 1.8, 2.5); link_only(ep, C_eng); ep.data.materials.append(mat_ext)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = ep; ep.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for p in ep.data.polygons: p.use_smooth = True

    add_torus(f'EyePod_Rim_{tag}', (23.0, side * 14.0, 1.3), 1.65, 0.24, (math.radians(90), 0, 0), mat_gold, maj=32, mn=8)
    add_torus(f'EyePod_RingInner_{tag}', (23.0, side * 14.1, 1.3), 0.92, 0.12, (math.radians(90), 0, 0), mat_gold, maj=32, mn=8)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1.25, location=(23.0, side * 13.8, 1.3))
    eg = bpy.context.active_object; eg.name = f'EyePod_Glow_{tag}'; eg.scale = (1.0, 0.55, 1.0); link_only(eg, C_eng); eg.data.materials.append(mat_glow)
    for p in eg.data.polygons: p.use_smooth = True

    for k in range(8):
        ang = 2 * math.pi * k / 8
        rx = 23.0 + math.cos(ang) * 1.24
        rz = 1.3 + math.sin(ang) * 1.24
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.075, depth=0.80, location=(rx, side * 14.12, rz), rotation=(0, ang + math.pi / 2, 0))
        sp = bpy.context.active_object; sp.name = f'EyePod_Louver_{tag}_{k}'; link_only(sp, C_eng); sp.data.materials.append(mat_gold)
        for p in sp.data.polygons: p.use_smooth = True

print("Rebuilt Engines & EyePods:", len(C_eng.objects))

# 4. Refit 2-Deck Interior cleanly inside sleek Hull_Outer
SX, SY, SZ = 0.87, 0.92, 0.82
C_int = get_coll('Interior')

def map_pt(p):
    return Vector((-48.0 + (p.x + 48.0) * SX, p.y * SY, p.z * SZ))

seen_meshes = set()
int_meshes = []
for o in C_int.all_objects:
    if o.name == 'PH_ClipVolume':
        continue
    if o.type == 'LIGHT':
        o.location = map_pt(o.location)
        if o.data.type == 'AREA':
            o.data.size *= SX
            o.data.size_y *= SY
    elif o.type == 'MESH':
        if o.data in seen_meshes:
            o.data = o.data.copy()
        seen_meshes.add(o.data)
        mw = o.matrix_world
        mwi = mw.inverted()
        for v in o.data.vertices:
            v.co = mwi @ map_pt(mw @ v.co)
        o.data.update()
        int_meshes.append(o)

# Build temporary Hull_SafeClip (shrunk inward 0.30m) and clip any protruding interior meshes
dg = bpy.context.evaluated_depsgraph_get()
h_eval = hull.evaluated_get(dg)
safe_me = bpy.data.meshes.new_from_object(h_eval)
bm = bmesh.new()
bm.from_mesh(safe_me)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.normal_update()
for v in bm.verts:
    v.co -= v.normal * 0.30
bm.to_mesh(safe_me)
bm.free()
safe_me.update()

safe_ob = bpy.data.objects.new('Hull_SafeClip', safe_me)
get_coll('Interior_ClipVolume', C_int).objects.link(safe_ob)

dg = bpy.context.evaluated_depsgraph_get()
bvh_safe = BVHTree.FromObject(safe_ob, dg)

def find_protruding(bvh_ref, objs):
    out = []
    for o in objs:
        mw = o.matrix_world
        for v in o.data.vertices:
            p = mw @ v.co
            loc, n, idx, dist = bvh_ref.find_nearest(p)
            if loc is not None and (p - loc).dot(n) > 0.02:
                out.append(o)
                break
    return out

to_clip = find_protruding(bvh_safe, int_meshes)
print("Interior meshes protruding before clip:", len(to_clip))

for o in to_clip:
    vb = len(o.data.vertices)
    md = o.modifiers.new('B', 'BOOLEAN')
    md.operation = 'INTERSECT'
    md.object = safe_ob
    try:
        md.solver = 'EXACT'
    except Exception:
        pass
    dg = bpy.context.evaluated_depsgraph_get()
    nm = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    o.modifiers.remove(md)
    old = o.data
    o.data = nm
    if old.users == 0:
        bpy.data.meshes.remove(old)
    print(f"  clipped {o.name}: {vb}->{len(o.data.vertices)} verts, dim={tuple(round(d,2) for d in o.dimensions)}")
    if len(o.data.vertices) == 0:
        print("  WARNING empty after clip, removing:", o.name)
        kill_obj(o)

int_meshes_alive = [o for o in C_int.all_objects if o.type == 'MESH' and o.name not in ('PH_ClipVolume', 'Hull_SafeClip')]
bvh_outer = BVHTree.FromObject(hull.evaluated_get(dg), dg)
rem_outer = find_protruding(bvh_outer, int_meshes_alive)
print("Remaining interior meshes outside Hull_Outer:", len(rem_outer), [o.name for o in rem_outer])

bpy.data.objects.remove(safe_ob, do_unlink=True)
bpy.data.meshes.remove(safe_me)

# 5. Update toggle_cutaway.py deck slice heights
TOGGLE_CODE = r'''import bpy, math

MODES = {
    'intact':      ((0.0, 0.0, 1000.0), (0.0, 0.0, 0.0)),
    'side':        ((0.0, 0.0, 0.0),    (math.pi / 2, 0.0, 0.0)),
    'side_cabins': ((0.0, 0.96, 0.0),   (math.pi / 2, 0.0, 0.0)),
    'top_upper':   ((0.0, 0.0, 2.55),   (0.0, 0.0, 0.0)),
    'top_lower':   ((0.0, 0.0, -0.15),  (0.0, 0.0, 0.0)),
}

def set_mode(mode='intact', camera_name=None):
    """Switch cutaway mode: 'intact', 'side', 'side_cabins', 'top_upper', 'top_lower'."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode '{mode}'. Choose from {list(MODES.keys())}")
    loc, rot = MODES[mode]
    plane = bpy.data.objects['CUTAWAY_Plane']
    plane.location = loc
    plane.rotation_euler = rot
    if camera_name and camera_name in bpy.data.objects:
        bpy.context.scene.camera = bpy.data.objects[camera_name]
    bpy.context.view_layer.update()
    print(f"Cutaway mode set to '{mode}' (loc={loc}, rot={rot})")
'''
t = bpy.data.texts.get('toggle_cutaway.py') or bpy.data.texts.new('toggle_cutaway.py')
t.clear(); t.write(TOGGLE_CODE)

tgt = bpy.data.objects.get('Ship_Target')
if tgt:
    tgt.location = (10.0, 0.0, 0.0)

plane = bpy.data.objects.get('CUTAWAY_Plane')
if plane:
    plane.location = (0.0, 0.0, 1000.0)
    plane.rotation_euler = (0.0, 0.0, 0.0)

bpy.ops.wm.save_mainfile(filepath=BLEND_PATH)
print("Saved sleek starship_v1.blend!")
