"""Gaussian projection and SH are evaluated once per splat, not per corner."""

import gpu
from gpu_extras.batch import batch_for_shader


COMPUTE = r'''
vec4 load_data(uint address) {
  uint width = uint(textureSize(splats, 0).x);
  return texelFetch(splats, ivec2(address % width, address / width), 0);
}

vec4 load_object(uint address) {
  uint width = uint(textureSize(objects, 0).x);
  return texelFetch(objects, ivec2(address % width, address / width), 0);
}

void store_result(uint address, vec4 value) {
  uint width = uint(imageSize(projected).x);
  imageStore(projected, ivec2(address % width, address / width), value);
}

vec3 evaluate_sh(uint base, int degree, vec3 v) {
  float x = v.x, y = v.y, z = v.z;
  float xx = x*x, yy = y*y, zz = z*z;
  float xy = x*y, yz = y*z, xz = x*z;
  float basis[25];
  basis[0] = 0.2820947918;
  basis[1] = -0.4886025119*y;
  basis[2] = 0.4886025119*z;
  basis[3] = -0.4886025119*x;
  basis[4] = 1.0925484306*xy;
  basis[5] = -1.0925484306*yz;
  basis[6] = 0.3153915653*(3.0*zz - 1.0);
  basis[7] = -1.0925484306*xz;
  basis[8] = 0.5462742153*(xx - yy);
  basis[9] = -0.5900435899*y*(3.0*xx - yy);
  basis[10] = 2.8906114426*xy*z;
  basis[11] = -0.4570457995*y*(5.0*zz - 1.0);
  basis[12] = 0.3731763326*z*(5.0*zz - 3.0);
  basis[13] = -0.4570457995*x*(5.0*zz - 1.0);
  basis[14] = 1.4453057213*z*(xx - yy);
  basis[15] = -0.5900435899*x*(xx - 3.0*yy);
  basis[16] = 2.5033429418*xy*(xx - yy);
  basis[17] = -1.7701307698*yz*(3.0*xx - yy);
  basis[18] = 0.9461746958*xy*(7.0*zz - 1.0);
  basis[19] = -0.6690465436*yz*(7.0*zz - 3.0);
  basis[20] = 0.1057855469*(zz*(35.0*zz - 30.0) + 3.0);
  basis[21] = -0.6690465436*xz*(7.0*zz - 3.0);
  basis[22] = 0.4730873479*(xx - yy)*(7.0*zz - 1.0);
  basis[23] = -1.7701307698*xz*(xx - 3.0*yy);
  basis[24] = 0.6258357354*(xx*xx - 6.0*xx*yy + yy*yy);
  vec3 color = vec3(0.5);
  int count = (degree + 1)*(degree + 1);
  for (int i = 0; i < count; ++i) {
    color += basis[i]*load_data(base + uint(i)).xyz;
  }
  return max(color, vec3(0.0));
}

void main() {
  uint i = gl_GlobalInvocationID.x + gl_GlobalInvocationID.y * gl_NumWorkGroups.x * 128u;
  if (i >= pointCount) return;
  uint output_base = i*3u;
  store_result(output_base, vec4(0.0, 0.0, 2.0, 0.0));
  uint width = uint(textureSize(order, 0).x);
  vec4 item = texelFetch(order, ivec2(i % width, i / width), 0);
  uint base = uint(item.x) + uint(item.y)*65536u;
  uint object_base = uint(item.z)*8u;
  vec4 center = load_data(base);
  vec3 scale = load_data(base + 1u).xyz;
  vec4 q = load_data(base + 2u);
  mat4 model_view = mat4(load_object(object_base), load_object(object_base + 1u),
                         load_object(object_base + 2u), load_object(object_base + 3u));
  vec4 camera = load_object(object_base + 4u);
  vec4 parallel = load_object(object_base + 5u);
  vec4 params = load_object(object_base + 6u);
  vec4 view_pos = model_view*vec4(center.xyz, 1.0);
  vec4 clip = projection*view_pos;
  if (clip.w <= 0.0 || clip.z < -clip.w || clip.z > clip.w || center.w <= 0.0) return;

  q *= inversesqrt(max(dot(q, q), 1e-20));
  float x = q.x, y = q.y, z = q.z, w = q.w;
  mat3 rotation = mat3(
    vec3(1.0 - 2.0*(y*y + z*z), 2.0*(x*y + z*w), 2.0*(x*z - y*w)),
    vec3(2.0*(x*y - z*w), 1.0 - 2.0*(x*x + z*z), 2.0*(y*z + x*w)),
    vec3(2.0*(x*z + y*w), 2.0*(y*z - x*w), 1.0 - 2.0*(x*x + y*y)));
  mat3 axes = mat3(model_view)*rotation;
  axes[0] *= scale.x;
  axes[1] *= scale.y;
  axes[2] *= scale.z;

  // Quotient-rule Jacobian supports perspective, orthographic and shifted views.
  // Bound the EWA derivative outside the frustum: distant background splats
  // almost on the camera plane must not expand across the entire viewport.
  mat4 pt = transpose(projection);
  vec2 derivative_center = clamp(clip.xy/clip.w, vec2(-1.3), vec2(1.3));
  vec3 jx = (pt[0].xyz - pt[3].xyz*derivative_center.x)/clip.w*viewport.x*0.5;
  vec3 jy = (pt[1].xyz - pt[3].xyz*derivative_center.y)/clip.w*viewport.y*0.5;
  vec3 ax = transpose(axes)*jx;
  vec3 ay = transpose(axes)*jy;
  float a = dot(ax, ax), b = dot(ax, ay), c = dot(ay, ay);
  vec3 area = cross(ax, ay);
  float determinant = dot(area, area);
  float filtered = determinant + 0.3*(a + c) + 0.09;
  a += 0.3;
  c += 0.3;
  if (filtered <= 0.0 || isinf(filtered) || isnan(filtered)) return;
  float opacity = center.w;
  float aa = load_data(base + 1u).w;
  if (aa == 0.0 ? params.x != 0.0 : aa == 2.0) opacity *= sqrt(determinant/filtered);
  if (opacity <= 0.0) return;

  float mean = 0.5*(a + c);
  float delta = length(vec2(0.5*(a - c), b));
  float major = mean + delta;
  float minor = max(filtered/major, 1e-8);
  vec2 direction = abs(b) > 1e-6 ? normalize(vec2(b, major - a))
                                : (a >= c ? vec2(1, 0) : vec2(0, 1));
  float extent = 3.0;
  vec2 u = direction*sqrt(major)*extent;
  vec2 v = vec2(-direction.y, direction.x)*sqrt(minor)*extent;
  vec2 ndc = clip.xy/clip.w;
  vec2 bounds = (abs(u) + abs(v))*2.0/viewport;
  if (any(greaterThan(abs(ndc), vec2(1.0) + bounds))) return;

  vec3 ray = params.y != 0.0 ? parallel.xyz : center.xyz - camera.xyz;
  ray *= inversesqrt(max(dot(ray, ray), 1e-20));
  vec3 color = evaluate_sh(base + 3u, int(camera.w), ray);
  // Resolve every SH term before decoding sRGB. POST_VIEW is scene-linear;
  // Blender applies its display conversion after the preview has been blended.
  float color_space = load_data(base + 3u).w;
  if ((color_space == 0.0 ? parallel.w : color_space) != 2.0) {
    color = mix(color/12.92, pow((color + 0.055)/1.055, vec3(2.4)),
                greaterThan(color, vec3(0.04045)));
  }
  store_result(output_base, vec4(ndc, clip.z/clip.w, min(opacity, 1.0)));
  store_result(output_base + 1u, vec4(u*2.0/viewport, v*2.0/viewport));
  store_result(output_base + 2u, vec4(color, extent));
}
'''

VERTEX = r'''
vec4 load_result(int address) {
  int width = textureSize(projected, 0).x;
  return texelFetch(projected, ivec2(address % width, address / width), 0);
}
void main() {
  int base = gl_InstanceID*3;
  vec4 center = load_result(base);
  if (center.w == 0.0) {
    gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
    radiance = vec4(0.0);
    offset = vec2(0.0);
    return;
  }
  vec4 axes = load_result(base + 1);
  vec4 color = load_result(base + 2);
  gl_Position = vec4(center.xy + corner.x*axes.xy + corner.y*axes.zw, center.z, 1.0);
  offset = corner*color.w;
  radiance = vec4(color.xyz, center.w);
}
'''

FRAGMENT = r'''
void main() {
  float radius2 = dot(offset, offset);
  if (radius2 > 9.0) discard;
  float alpha = radiance.w*exp(-0.5*radius2);
  fragColor = vec4(radiance.xyz*alpha, alpha);
}
'''


def create():
    info = gpu.types.GPUShaderCreateInfo()
    info.local_group_size(128, 1)
    info.sampler(0, 'FLOAT_2D', 'splats')
    info.sampler(1, 'FLOAT_2D', 'order')
    info.sampler(2, 'FLOAT_2D', 'objects')
    info.image(0, 'RGBA32F', 'FLOAT_2D', 'projected', qualifiers={'WRITE'})
    info.push_constant('MAT4', 'projection')
    info.push_constant('VEC2', 'viewport')
    info.push_constant('UINT', 'pointCount')
    info.compute_source(COMPUTE)
    compute = gpu.shader.create_from_info(info)

    info = gpu.types.GPUShaderCreateInfo()
    interface = gpu.types.GPUStageInterfaceInfo('splat_interface')
    interface.smooth('VEC2', 'offset')
    interface.flat('VEC4', 'radiance')
    info.vertex_in(0, 'VEC2', 'corner')
    info.vertex_out(interface)
    info.sampler(0, 'FLOAT_2D', 'projected')
    info.fragment_out(0, 'VEC4', 'fragColor')
    info.vertex_source(VERTEX)
    info.fragment_source(FRAGMENT)
    draw = gpu.shader.create_from_info(info)
    batch = batch_for_shader(draw, 'TRIS', {'corner': [(-1, -1), (1, -1), (-1, 1), (1, 1)]},
                             indices=[(0, 1, 2), (2, 1, 3)])
    return compute, draw, batch
