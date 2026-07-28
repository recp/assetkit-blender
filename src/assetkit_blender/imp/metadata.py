from __future__ import annotations

import json


def _set_prop_if_nondefault(target, key: str, value, default) -> None:
    if value == default:
        return
    target[key] = value


def _set_assetkit_json_prop(target, key: str, value: object | None) -> None:
    if not value:
        return
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return
    if payload and payload != "null":
        target[key] = payload


def _assetkit_extra_path(value: object | None, *path: str) -> object | None:
    node = value
    for name in path:
        node = _assetkit_extra_child(node, name)
        if node is None:
            return None
    return node


def _assetkit_extra_child(value: object | None, name: str) -> object | None:
    if not isinstance(value, dict):
        return None
    for child in _assetkit_extra_children(value):
        if child.get("name") == name:
            return child
    return None


def _assetkit_extra_children(value: object | None) -> list[dict]:
    if not isinstance(value, dict):
        return []
    return [child for child in (value.get("children") or ()) if isinstance(child, dict)]


def _assetkit_extra_float(value: object | None, default: float = 0.0) -> float:
    if not isinstance(value, dict):
        return default
    try:
        return float(value.get("value"))
    except (TypeError, ValueError):
        return default


def _assetkit_extra_float_array(value: object | None, limit: int) -> tuple[float, ...]:
    if not isinstance(value, dict):
        return ()
    items = []
    for child in value.get("children") or ():
        items.append(_assetkit_extra_float(child))
        if len(items) >= limit:
            break
    return tuple(items)


def _assetkit_extra_plain_value(value: object | None) -> object | None:
    if not isinstance(value, dict):
        return None

    attrs = value.get("attributes") if isinstance(value.get("attributes"), dict) else {}
    node_type = attrs.get("type")
    children = [child for child in (value.get("children") or ()) if isinstance(child, dict)]

    if node_type == "array":
        return [_assetkit_extra_plain_value(child) for child in children]

    if node_type == "object" or children:
        out = {}
        for child in children:
            key = str(child.get("name") or "item")
            child_value = _assetkit_extra_plain_value(child)
            if key in out:
                current = out[key]
                if not isinstance(current, list):
                    out[key] = [current]
                out[key].append(child_value)
            else:
                out[key] = child_value
        return out

    return _assetkit_extra_plain_scalar(value.get("value"))


def _assetkit_extra_plain_scalar(value: object | None) -> object | None:
    if value is None:
        return None

    text = str(value)
    if text == "":
        return ""
    if text == "true":
        return True
    if text == "false":
        return False
    if text == "null":
        return None

    try:
        if "." not in text and "e" not in text and "E" not in text:
            return int(text)
        return float(text)
    except ValueError:
        return text
