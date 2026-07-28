from __future__ import annotations

from typing import Iterable

from .data import SceneNodeData

_EMPTY_SEQUENCE: tuple = ()


(
    _N_OWNER,
    _N_NAME,
    _N_PARENT_INDEX,
    _N_PROTOTYPE_ROOT_INDEX,
    _N_INSTANCE_TARGET_INDEX,
    _N_VISIBLE,
    _N_LAYERS,
    _N_CAMERA_TYPE,
    _N_CAMERA_NAME,
    _N_CAMERA_EXTRA,
    _N_CAMERA_IMAGER_EXTRA,
    _N_CAMERA_VALUES,
    _N_LIGHT_TYPE,
    _N_LIGHT_NAME,
    _N_LIGHT_EXTRA,
    _N_LIGHT_COLOR,
    _N_LIGHT_VALUES,
    _N_MATRIX_F32,
    _N_WORLD_MATRIX_F32,
    _N_EXTRA,
    _N_ANIM_COUNT,
    _N_ANIM_CHANNELS,
) = range(22)


class NativeSceneNodeData:
    __slots__ = ("_raw", "_visible", "_has_world_matrix")

    def __init__(self, raw: tuple):
        self._raw = raw
        self._has_world_matrix = len(raw) >= 22
        extra = raw[_N_EXTRA if self._has_world_matrix else _N_WORLD_MATRIX_F32]
        visible = _extra_bool(extra, ("extensions", "KHR_node_visibility", "visible")) if extra else None
        self._visible = bool(raw[_N_VISIBLE]) if visible is None else visible

    @property
    def name(self):
        return self._raw[_N_NAME] or ""

    @property
    def parent_index(self):
        value = self._raw[_N_PARENT_INDEX]
        return int(value if value is not None else -1)

    @property
    def prototype_root_index(self):
        value = self._raw[_N_PROTOTYPE_ROOT_INDEX]
        return int(value if value is not None else -1)

    @property
    def instance_target_index(self):
        value = self._raw[_N_INSTANCE_TARGET_INDEX]
        return int(value if value is not None else -1)

    @property
    def matrix_f32(self):
        return self._raw[_N_MATRIX_F32] or b""

    @property
    def world_matrix_f32(self):
        if not self._has_world_matrix:
            return b""
        return self._raw[_N_WORLD_MATRIX_F32] or b""

    @property
    def anim_channels(self):
        index = _N_ANIM_CHANNELS if self._has_world_matrix else _N_ANIM_COUNT
        return self._raw[index] or _EMPTY_SEQUENCE

    @property
    def anim_count(self):
        index = _N_ANIM_COUNT if self._has_world_matrix else _N_EXTRA
        return int(self._raw[index] or 0)

    @property
    def visible(self):
        return self._visible

    @property
    def layers(self):
        return self._raw[_N_LAYERS] or _EMPTY_SEQUENCE

    @property
    def camera_type(self):
        return int(self._raw[_N_CAMERA_TYPE] or 0)

    @property
    def camera_name(self):
        return self._raw[_N_CAMERA_NAME] or ""

    @property
    def camera_values(self):
        return self._raw[_N_CAMERA_VALUES] or (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def camera_extra(self):
        return self._raw[_N_CAMERA_EXTRA]

    @property
    def camera_imager_extra(self):
        return self._raw[_N_CAMERA_IMAGER_EXTRA]

    @property
    def light_type(self):
        return int(self._raw[_N_LIGHT_TYPE] or 0)

    @property
    def light_name(self):
        return self._raw[_N_LIGHT_NAME] or ""

    @property
    def light_color(self):
        return self._raw[_N_LIGHT_COLOR] or (1.0, 1.0, 1.0)

    @property
    def light_values(self):
        return self._raw[_N_LIGHT_VALUES] or (0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def light_extra(self):
        return self._raw[_N_LIGHT_EXTRA]

    @property
    def extra(self):
        return self._raw[_N_EXTRA if self._has_world_matrix else _N_WORLD_MATRIX_F32]

    @property
    def _native_owner(self):
        return self._raw[_N_OWNER]


def nodes_from_raw(raw_nodes: Iterable[dict]) -> list[SceneNodeData]:
    nodes = []
    for item in raw_nodes:
        if isinstance(item, tuple) and len(item) == 19:
            item = item[:3] + (-1, -1) + item[3:]
        if isinstance(item, tuple) and len(item) >= 21:
            nodes.append(NativeSceneNodeData(item))
            continue

        extra = item.get("extra")
        visible = _extra_bool(extra, ("extensions", "KHR_node_visibility", "visible")) if extra else None
        if visible is None:
            visible = bool(item.get("visible", True))
        nodes.append(
            SceneNodeData(
                name=item.get("name") or "",
                parent_index=int(item.get("parent_index") if item.get("parent_index") is not None else -1),
                prototype_root_index=int(
                    item.get("prototype_root_index")
                    if item.get("prototype_root_index") is not None
                    else -1
                ),
                instance_target_index=int(
                    item.get("instance_target_index")
                    if item.get("instance_target_index") is not None
                    else -1
                ),
                matrix_f32=item.get("matrix_f32") or b"",
                world_matrix_f32=item.get("world_matrix_f32") or b"",
                anim_channels=item.get("anim_channels") or [],
                anim_count=int(item.get("anim_count") or 0),
                visible=visible,
                layers=list(item.get("layers") or []),
                camera_type=int(item.get("camera_type") or 0),
                camera_name=item.get("camera_name") or "",
                camera_values=tuple(item.get("camera_values") or (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
                camera_extra=item.get("camera_extra"),
                camera_imager_extra=item.get("camera_imager_extra"),
                light_type=int(item.get("light_type") or 0),
                light_name=item.get("light_name") or "",
                light_color=tuple(item.get("light_color") or (1.0, 1.0, 1.0)),
                light_values=tuple(item.get("light_values") or (0.0, 0.0, 0.0, 0.0, 0.0)),
                light_extra=item.get("light_extra"),
                extra=extra,
                _native_owner=item.get("_owner"),
            )
        )
    return nodes


def _extra_bool(extra: object, path: tuple[str, ...]) -> bool | None:
    node = _extra_child_path(extra, path)
    if not isinstance(node, dict):
        return None

    value = str(node.get("value") or "").strip().lower()
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    return None


def _extra_child_path(extra: object, path: tuple[str, ...]) -> object | None:
    node = extra
    for name in path:
        if not isinstance(node, dict):
            return None
        node = next(
            (
                child
                for child in node.get("children") or []
                if isinstance(child, dict) and child.get("name") == name
            ),
            None,
        )
    return node
