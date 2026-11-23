import bpy
import os

out_path = '/Users/xzm/Downloads/antShip/web/starship_v1.glb'
os.makedirs(os.path.dirname(out_path), exist_ok=True)

# 1. Remove CUT_Mix cutaway shader nodes from all materials
for mat in bpy.data.materials:
    if not mat.use_nodes or mat.node_tree is None:
        continue
    nt = mat.node_tree
    cut_mix = next((n for n in nt.nodes if n.name == 'CUT_Mix'), None)
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if cut_mix and out:
        if cut_mix.inputs[1].links:
            src_sock = cut_mix.inputs[1].links[0].from_socket
            for lk in list(out.inputs['Surface'].links):
                nt.links.remove(lk)
            nt.links.new(src_sock, out.inputs['Surface'])
        for nm in ('CUT_Mix', 'CUT_Coord'):
            nd = nt.nodes.get(nm)
            if nd:
                nt.nodes.remove(nd)

# 2. Delete helper/non-geometry objects
for o in list(bpy.data.objects):
    if o.name in ('PH_ClipVolume', 'CUTAWAY_Plane', 'Ship_Target') or o.type in ('CAMERA', 'LIGHT'):
        bpy.data.objects.remove(o, do_unlink=True)

# 4. Ensure visibility on remaining objects and convert CURVE objects to MESH
dg = bpy.context.evaluated_depsgraph_get()
curve_objs = [o for o in bpy.data.objects if o.type == 'CURVE']
for ob in curve_objs:
    ob.hide_set(False)
    ob.hide_viewport = False
    ob.hide_render = False
    dg.update()
    ev = ob.evaluated_get(dg)
    new_me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    if len(new_me.materials) == 0 and len(ob.data.materials) > 0:
        for m in ob.data.materials:
            new_me.materials.append(m)
    new_ob = bpy.data.objects.new(ob.name + '_Mesh', new_me)
    new_ob.matrix_world = ob.matrix_world.copy()
    for col in ob.users_collection:
        col.objects.link(new_ob)
    old_name = ob.name
    old_data = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if old_data.users == 0:
        bpy.data.curves.remove(old_data)
    new_ob.name = old_name

for o in bpy.data.objects:
    o.hide_set(False)
    o.hide_viewport = False
    o.hide_render = False

# 5. Create parent Empties GRP_Exterior and GRP_Interior
sc = bpy.context.scene
grp_ext = bpy.data.objects.new('GRP_Exterior', None)
grp_int = bpy.data.objects.new('GRP_Interior', None)
sc.collection.objects.link(grp_ext)
sc.collection.objects.link(grp_int)

ext_colls = ('Exterior', 'Fins_Horns', 'Engines', 'Ornaments', 'Lights_Glow')
int_colls = ('Interior', 'Int_Structure', 'Int_ZoneFloors', 'Int_Furniture', 'Int_Machinery')

ext_set = set()
for cname in ext_colls:
    c = bpy.data.collections.get(cname)
    if c:
        for o in c.objects:
            if o.type == 'MESH':
                ext_set.add(o)

int_set = set()
for cname in int_colls:
    c = bpy.data.collections.get(cname)
    if c:
        for o in c.objects:
            if o.type == 'MESH':
                int_set.add(o)

ph_shell = bpy.data.objects.get('PressureHull_Shell')
if ph_shell:
    int_set.add(ph_shell)

for o in ext_set:
    mw = o.matrix_world.copy()
    o.parent = grp_ext
    o.matrix_world = mw

for o in int_set:
    if o in ext_set:
        continue
    mw = o.matrix_world.copy()
    o.parent = grp_int
    o.matrix_world = mw

print(f"Exporting objects: total={len(bpy.data.objects)}, ext={len(ext_set)}, int={len(int_set)}")
print("Materials:", [m.name for m in bpy.data.materials])

# 6. Export GLB with embedded 4K PBR textures
gltf_kwargs = dict(
    filepath=out_path,
    export_format='GLB',
    export_image_format='JPEG',
    export_yup=True,
    export_apply=True,
    export_materials='EXPORT',
    export_lights=False,
    export_cameras=False,
)
rna_props = bpy.ops.export_scene.gltf.get_rna_type().properties
if 'export_image_quality' in rna_props:
    gltf_kwargs['export_image_quality'] = 92
bpy.ops.export_scene.gltf(**gltf_kwargs)

print("GLB exported:", out_path, "size:", os.path.getsize(out_path))
