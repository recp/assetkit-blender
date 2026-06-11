#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <limits.h>
#include <errno.h>
#if defined(_WIN32)
#include <windows.h>
#include <direct.h>
#else
#include <dlfcn.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

#include "cglm/struct.h"

#include "mem.h"

#include "ak/assetkit.h"
#include "ak/options.h"
#include "ak/path.h"
#include "ak/version.h"

#ifndef PATH_MAX
#  define PATH_MAX 4096
#endif


#include "common/types.inc"
#include "imp/import.inc"
#include "exp/export.inc"

static PyMethodDef akb_methods[] = {
  {"load_meshes", akb_load_meshes, METH_VARARGS, "Load mesh buffers through AssetKit."},
  {"open_scene", akb_open_scene, METH_VARARGS, "Open an AssetKit scene for batched mesh reads."},
  {"read_mesh_batch", akb_read_mesh_batch, METH_VARARGS, "Read a batch of mesh buffers from an open AssetKit scene."},
  {"export_scene", akb_export_scene, METH_VARARGS, "Export Blender scene objects through AssetKit."},
  {"export_aligned_anim_channel", akb_export_aligned_anim_channel, METH_VARARGS, "Build an aligned Blender FCurve animation channel for export."},
  {"export_pack_metallic_roughness", akb_export_pack_metallic_roughness, METH_VARARGS, "Pack glTF metallic-roughness pixels for export."},
  {"export_pack_base_color_alpha", akb_export_pack_base_color_alpha, METH_VARARGS, "Pack base-color RGB and alpha pixels for export."},
  {"export_pack_channel", akb_export_pack_channel, METH_VARARGS, "Pack one image channel into a glTF target channel for export."},
  {"export_pack_rgb_channel", akb_export_pack_rgb_channel, METH_VARARGS, "Pack one image channel into RGB for export."},
  {"export_pack_specular_glossiness", akb_export_pack_specular_glossiness, METH_VARARGS, "Pack glTF specular-glossiness pixels for export."},
  {"decode_ktx2", akb_decode_ktx2, METH_VARARGS, "Decode a KTX2 texture to float RGBA pixels."},
  {"anim_coords", akb_anim_coords, METH_VARARGS, "Build an interleaved FCurve coordinate buffer for an animation channel."},
  {"anim_component_constant", akb_anim_component_constant, METH_VARARGS, "Return true when an animation channel component is constant."},
  {"offset_i32", akb_offset_i32, METH_VARARGS, "Build an int32 buffer with a constant offset added to each element."},
  {"write_offset_i32", akb_write_offset_i32, METH_VARARGS, "Write an int32 buffer with a constant offset into a writable destination buffer."},
  {"fill_i32", akb_fill_i32, METH_VARARGS, "Fill a writable destination buffer with one int32 value."},
  {"fill_triangle_loop_offsets_ptr", akb_fill_triangle_loop_offsets_ptr, METH_VARARGS, "Fill Blender Mesh face offsets for a triangle-only mesh from a raw int32 pointer."},
  {"fill_u8_ptr", akb_fill_u8_ptr, METH_VARARGS, "Fill a raw uint8 pointer with one byte value."},
  {"skin_group_assignments", akb_skin_group_assignments, METH_VARARGS, "Build rigid skin vertex-group assignment buffers."},
  {NULL, NULL, 0, NULL}
};

static struct PyModuleDef akb_module = {
  PyModuleDef_HEAD_INIT,
  "_assetkit_blender",
  "Native AssetKit bridge for Blender.",
  -1,
  akb_methods
};

PyMODINIT_FUNC
PyInit__assetkit_blender(void) {
  return PyModule_Create(&akb_module);
}
