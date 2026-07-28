_AK_MATERIAL_TYPE_PHONG                    = 1
_AK_MATERIAL_TYPE_BLINN                    = 2
_AK_MATERIAL_TYPE_LAMBERT                  = 3
_AK_MATERIAL_TYPE_CONSTANT                 = 4
_AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS = 6

_GLTF_SETTINGS_GROUP_NAME = "glTF Material Output"
_GLTF_SETTINGS_SOCKETS    = (
    ("Occlusion", 1.0),
    ("Thickness", 0.0),
    ("Dispersion", 0.0),
    ("Iridescence Factor", 0.0),
    ("Iridescence Thickness Minimum", 100.0),
)

_TEXTURE_WRAP_DEFAULT          = 1
_TEXTURE_FILTER_DEFAULT        = 0
_TEXTURE_EXTENSION_DEFAULT     = "REPEAT"
_TEXTURE_INTERPOLATION_DEFAULT = "Linear"

_ANIM_MATERIAL_BASE_COLOR                    = 32
_ANIM_MATERIAL_METALLIC                      = 33
_ANIM_MATERIAL_ROUGHNESS                     = 34
_ANIM_MATERIAL_ALPHA_CUTOFF                  = 35
_ANIM_MATERIAL_EMISSIVE_COLOR                = 36
_ANIM_MATERIAL_EMISSIVE_STRENGTH             = 37
_ANIM_MATERIAL_NORMAL_SCALE                  = 38
_ANIM_MATERIAL_OCCLUSION_STRENGTH            = 39
_ANIM_MATERIAL_SPECULAR                      = 40
_ANIM_MATERIAL_SPECULAR_COLOR                = 41
_ANIM_MATERIAL_IOR                           = 42
_ANIM_MATERIAL_CLEARCOAT                     = 43
_ANIM_MATERIAL_CLEARCOAT_ROUGHNESS           = 44
_ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE        = 45
_ANIM_MATERIAL_TRANSMISSION                  = 46
_ANIM_MATERIAL_SHEEN_COLOR                   = 47
_ANIM_MATERIAL_SHEEN_ROUGHNESS               = 48
_ANIM_MATERIAL_IRIDESCENCE                   = 49
_ANIM_MATERIAL_IRIDESCENCE_IOR               = 50
_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM = 51
_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM = 52
_ANIM_MATERIAL_VOLUME_THICKNESS              = 53
_ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE   = 54
_ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR      = 55
_ANIM_MATERIAL_ANISOTROPY                    = 56
_ANIM_MATERIAL_ANISOTROPY_ROTATION           = 57
_ANIM_MATERIAL_DISPERSION                    = 58
_ANIM_MATERIAL_DIFFUSE_TRANSMISSION          = 59
_ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR    = 60

_ANIM_TEXTURE_TRANSFORM_BASE     = 1000
_ANIM_TEXTURE_TRANSFORM_STRIDE   = 4
_ANIM_TEXTURE_TRANSFORM_OFFSET   = 0
_ANIM_TEXTURE_TRANSFORM_SCALE    = 1
_ANIM_TEXTURE_TRANSFORM_ROTATION = 2
_ANIM_TEXTURE_TRANSFORM_ROLES    = (
    "base_color",
    "metallic_roughness",
    "occlusion",
    "normal",
    "emissive",
    "transparent",
    "specular",
    "specular_color",
    "clearcoat",
    "clearcoat_roughness",
    "clearcoat_normal",
    "transmission",
    "sheen_color",
    "sheen_roughness",
    "iridescence",
    "iridescence_thickness",
    "volume_thickness",
    "anisotropy",
    "diffuse_transmission",
    "diffuse_transmission_color",
)

_MATERIAL_TEXTURE_FIELDS = tuple(f"{role}_texture" for role in _ANIM_TEXTURE_TRANSFORM_ROLES)
