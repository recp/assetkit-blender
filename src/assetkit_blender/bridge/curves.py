from __future__ import annotations

from typing import Iterable

from .data import CurveData

(
    _C_OWNER,
    _C_NAME,
    _C_OBJECT_NAME,
    _C_KIND,
    _C_POINT_COUNT,
    _C_DEGREE,
    _C_CLOSED,
    _C_HAS_NODE,
    _C_NODE_INDEX,
    _C_MATRIX_F32,
    _C_COORD_MATRIX_F32,
    _C_POINTS_F32,
    _C_GEOMETRY_EXTRA,
    _C_CURVE_EXTRA,
) = range(14)


class NativeCurveData:
    __slots__ = ("_raw", "_count")

    def __init__(self, raw: tuple):
        self._raw = raw
        self._count = len(raw)

    def _get(self, index: int, default=None):
        return self._raw[index] if index < self._count and self._raw[index] is not None else default

    @property
    def _native_owner(self):
        return self._get(_C_OWNER)

    @property
    def name(self):
        return self._get(_C_NAME, "") or ""

    @property
    def object_name(self):
        return self._get(_C_OBJECT_NAME, "") or ""

    @property
    def kind(self):
        return int(self._get(_C_KIND, 1) or 1)

    @property
    def point_count(self):
        return int(self._get(_C_POINT_COUNT, 0) or 0)

    @property
    def degree(self):
        return int(self._get(_C_DEGREE, 1) or 1)

    @property
    def closed(self):
        return bool(self._get(_C_CLOSED, False))

    @property
    def has_node(self):
        return bool(self._get(_C_HAS_NODE, False))

    @property
    def node_index(self):
        return int(self._get(_C_NODE_INDEX, -1))

    @property
    def matrix_f32(self):
        return self._get(_C_MATRIX_F32, b"") or b""

    @property
    def coord_matrix_f32(self):
        return self._get(_C_COORD_MATRIX_F32, b"") or b""

    @property
    def points_f32(self):
        return self._get(_C_POINTS_F32, b"") or b""

    @property
    def geometry_extra(self):
        return self._get(_C_GEOMETRY_EXTRA)

    @property
    def curve_extra(self):
        return self._get(_C_CURVE_EXTRA)


def curves_from_raw(raw_curves: Iterable[dict | tuple]) -> list[CurveData]:
    curves = []
    for item in raw_curves:
        if isinstance(item, tuple) and len(item) >= _C_CURVE_EXTRA + 1:
            curves.append(NativeCurveData(item))
            continue

        if not isinstance(item, dict):
            continue

        node_index = item.get("node_index")
        curves.append(
            CurveData(
                name=item.get("name") or "",
                object_name=item.get("object_name") or "",
                kind=int(item.get("kind") or 1),
                point_count=int(item.get("point_count") or 0),
                degree=int(item.get("degree") or 1),
                closed=bool(item.get("closed")),
                has_node=bool(item.get("has_node")),
                node_index=int(node_index if node_index is not None else -1),
                matrix_f32=item.get("matrix_f32") or b"",
                coord_matrix_f32=item.get("coord_matrix_f32") or b"",
                points_f32=item.get("points_f32") or b"",
                geometry_extra=item.get("geometry_extra"),
                curve_extra=item.get("curve_extra"),
                _native_owner=item.get("_owner"),
            )
        )
    return curves
