bl_info = {
    "name": "Quick Pivot",
    "author": "AiryHorizon5696",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "Vue 3D > Barre latérale (N) > Pivot",
    "description": "Place le pivot d'un objet en un clic (boîte englobante, centre de masse, etc.)",
    "category": "Object",
}

import bpy
import bmesh
from bpy.props import FloatVectorProperty, EnumProperty
from mathutils import Vector


# ---------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------

def bbox_world(obj):
    """Retourne (min, max) de la boîte englobante en coordonnées monde."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def point_on_bbox(obj, fx, fy, fz):
    """fx, fy, fz valent 0 (min), 0.5 (milieu) ou 1 (max)."""
    mn, mx = bbox_world(obj)
    return Vector((
        mn.x + (mx.x - mn.x) * fx,
        mn.y + (mx.y - mn.y) * fy,
        mn.z + (mx.z - mn.z) * fz,
    ))


def center_of_mass_world(obj, volume=False):
    """Centre de masse (surface) ou centre de volume, en coordonnées monde."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)

    if volume:
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        total = 0.0
        acc = Vector((0, 0, 0))
        for f in bm.faces:
            a, b, c = [v.co for v in f.verts]
            vol = a.dot(b.cross(c)) / 6.0
            total += vol
            acc += (a + b + c) * vol / 4.0
        bm.free()
        if abs(total) > 1e-9:
            return acc / total
        # Mesh non fermé : on retombe sur la moyenne des sommets
        volume = False
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.transform(obj.matrix_world)

    if not bm.verts:
        bm.free()
        return obj.matrix_world.translation.copy()
    center = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
    bm.free()
    return center


def set_origin_world(obj, world_pos):
    """Déplace l'origine de l'objet à world_pos sans bouger la géométrie."""
    local = obj.matrix_world.inverted() @ world_pos
    me = obj.data
    offset = Matrix_translation(-local)
    me.transform(offset)
    obj.matrix_world.translation = world_pos
    # Applique la même correction aux objets qui partagent ce mesh
    for other in bpy.data.objects:
        if other is not obj and other.data is me:
            other.matrix_world.translation += (
                other.matrix_world.to_3x3() @ local
            )


def Matrix_translation(vec):
    from mathutils import Matrix
    return Matrix.Translation(vec)


def selected_meshes(context):
    return [o for o in context.selected_objects if o.type == 'MESH']


# ---------------------------------------------------------------
# Opérateurs
# ---------------------------------------------------------------

class QP_OT_bbox_point(bpy.types.Operator):
    """Place le pivot sur un point de la boîte englobante"""
    bl_idname = "quickpivot.bbox_point"
    bl_label = "Pivot sur la boîte"
    bl_options = {'REGISTER', 'UNDO'}

    fx: bpy.props.FloatProperty(default=0.5)
    fy: bpy.props.FloatProperty(default=0.5)
    fz: bpy.props.FloatProperty(default=0.5)

    def execute(self, context):
        objs = selected_meshes(context)
        if not objs:
            self.report({'WARNING'}, "Sélectionne au moins un mesh")
            return {'CANCELLED'}
        was_edit = context.mode == 'EDIT_MESH'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in objs:
            set_origin_world(obj, point_on_bbox(obj, self.fx, self.fy, self.fz))
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}


class QP_OT_mass(bpy.types.Operator):
    """Place le pivot au centre de masse ou de volume"""
    bl_idname = "quickpivot.mass"
    bl_label = "Pivot au centre de masse"
    bl_options = {'REGISTER', 'UNDO'}

    volume: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        objs = selected_meshes(context)
        if not objs:
            self.report({'WARNING'}, "Sélectionne au moins un mesh")
            return {'CANCELLED'}
        was_edit = context.mode == 'EDIT_MESH'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in objs:
            set_origin_world(obj, center_of_mass_world(obj, self.volume))
        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}


class QP_OT_world_origin(bpy.types.Operator):
    """Place le pivot à l'origine du monde"""
    bl_idname = "quickpivot.world_origin"
    bl_label = "Pivot à l'origine du monde"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objs = selected_meshes(context)
        if not objs:
            self.report({'WARNING'}, "Sélectionne au moins un mesh")
            return {'CANCELLED'}
        for obj in objs:
            set_origin_world(obj, Vector((0, 0, 0)))
        return {'FINISHED'}


class QP_OT_to_cursor(bpy.types.Operator):
    """Place le pivot sur le curseur 3D"""
    bl_idname = "quickpivot.to_cursor"
    bl_label = "Pivot sur le curseur 3D"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objs = selected_meshes(context)
        if not objs:
            self.report({'WARNING'}, "Sélectionne au moins un mesh")
            return {'CANCELLED'}
        for obj in objs:
            set_origin_world(obj, context.scene.cursor.location.copy())
        return {'FINISHED'}


class QP_OT_to_selection(bpy.types.Operator):
    """Place le pivot au centre des éléments sélectionnés en mode édition"""
    bl_idname = "quickpivot.to_selection"
    bl_label = "Pivot sur la sélection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        verts = [v.co for v in bm.verts if v.select]
        if not verts:
            self.report({'WARNING'}, "Rien n'est sélectionné")
            return {'CANCELLED'}
        center_local = sum(verts, Vector()) / len(verts)
        world = obj.matrix_world @ center_local
        bpy.ops.object.mode_set(mode='OBJECT')
        set_origin_world(obj, world)
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}


class QP_OT_reset_cursor(bpy.types.Operator):
    """Remet le curseur 3D au centre du monde"""
    bl_idname = "quickpivot.reset_cursor"
    bl_label = "Curseur 3D au centre"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.cursor.location = (0, 0, 0)
        context.scene.cursor.rotation_euler = (0, 0, 0)
        return {'FINISHED'}


# ---------------------------------------------------------------
# Panneau
# ---------------------------------------------------------------

class QP_PT_panel(bpy.types.Panel):
    bl_label = "Quick Pivot"
    bl_idname = "QP_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pivot"

    def draw(self, context):
        layout = self.layout

        # Grille 3 x 3 (face avant : gauche/centre/droite x haut/milieu/bas)
        box = layout.box()
        box.label(text="Boîte englobante (vue de face)")
        for fz, name_z in ((1.0, "Haut"), (0.5, "Milieu"), (0.0, "Bas")):
            row = box.row(align=True)
            for fx, name_x in ((0.0, "G"), (0.5, "C"), (1.0, "D")):
                op = row.operator(
                    "quickpivot.bbox_point",
                    text=f"{name_z[0]}{name_x}",
                )
                op.fx = fx
                op.fy = 0.5
                op.fz = fz

        col = layout.column(align=True)
        col.label(text="Rapide")
        op = col.operator("quickpivot.bbox_point", text="Centre de la boîte", icon='PIVOT_BOUNDBOX')
        op.fx = op.fy = op.fz = 0.5
        op = col.operator("quickpivot.bbox_point", text="Bas au centre", icon='TRIA_DOWN_BAR')
        op.fx = 0.5
        op.fy = 0.5
        op.fz = 0.0
        op = col.operator("quickpivot.mass", text="Centre de masse", icon='SNAP_FACE_CENTER')
        op.volume = False
        op = col.operator("quickpivot.mass", text="Centre du volume", icon='MESH_CUBE')
        op.volume = True

        col = layout.column(align=True)
        col.label(text="Autres")
        col.operator("quickpivot.to_selection", text="Sur la sélection (édition)", icon='RESTRICT_SELECT_OFF')
        col.operator("quickpivot.to_cursor", text="Sur le curseur 3D", icon='CURSOR')
        col.operator("quickpivot.world_origin", text="Origine du monde", icon='WORLD')
        col.operator("quickpivot.reset_cursor", text="Curseur 3D au centre", icon='X')


# ---------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------

classes = (
    QP_OT_bbox_point,
    QP_OT_mass,
    QP_OT_world_origin,
    QP_OT_to_cursor,
    QP_OT_to_selection,
    QP_OT_reset_cursor,
    QP_PT_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()