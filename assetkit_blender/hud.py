from __future__ import annotations

import time

import bpy

try:
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
except Exception:
    blf = None
    gpu = None
    batch_for_shader = None

_FONT_ID = 0
_HUD_HANDLE = None
_HUD_ACTIVE = False
_HUD_TEXT = "AssetKit is importing"
_HUD_STARTED_AT = 0.0
_HUD_DELAY = 0.35
_HUD_TIMER_ACTIVE = False
_HUD_FONT_SIZE = 30
_HUD_PAD_X = 28
_HUD_PAD_Y = 18


def start_loading_hud(text: str = "AssetKit is importing", delay: float = 0.35) -> None:
    global _HUD_ACTIVE, _HUD_TEXT, _HUD_STARTED_AT, _HUD_DELAY, _HUD_HANDLE, _HUD_TIMER_ACTIVE

    if bpy.app.background:
        return

    _HUD_TEXT = text
    _HUD_DELAY = max(0.0, float(delay))
    _HUD_STARTED_AT = time.perf_counter()
    _HUD_ACTIVE = True

    if _HUD_HANDLE is None:
        _HUD_HANDLE = bpy.types.SpaceView3D.draw_handler_add(_draw_loading_hud, (), "WINDOW", "POST_PIXEL")

    _HUD_TIMER_ACTIVE = True
    bpy.app.timers.register(_loading_hud_timer, first_interval=min(max(_HUD_DELAY, 0.016), 0.1))

    _tag_view3d_redraw()


def update_loading_hud(text: str) -> None:
    global _HUD_TEXT

    if not _HUD_ACTIVE:
        return
    _HUD_TEXT = text
    _tag_view3d_redraw()


def finish_loading_hud() -> None:
    global _HUD_ACTIVE, _HUD_HANDLE, _HUD_TIMER_ACTIVE

    _HUD_ACTIVE = False
    _HUD_TIMER_ACTIVE = False
    if _HUD_HANDLE is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_HUD_HANDLE, "WINDOW")
        except Exception:
            pass
        _HUD_HANDLE = None
    _tag_view3d_redraw()


def _loading_hud_timer() -> float | None:
    global _HUD_TIMER_ACTIVE

    if not _HUD_ACTIVE:
        _HUD_TIMER_ACTIVE = False
        return None

    _tag_view3d_redraw()
    return 0.1


def _draw_loading_hud() -> None:
    if not _HUD_ACTIVE:
        return

    elapsed = time.perf_counter() - _HUD_STARTED_AT
    if elapsed < _HUD_DELAY:
        return

    region = getattr(bpy.context, "region", None)
    if not region:
        return
    if blf is None:
        return

    dots = "." * (int(elapsed * 2.5) % 4)
    text = f"{_HUD_TEXT}{dots}"
    try:
        if blf is None:
            return
        blf.size(_FONT_ID, _HUD_FONT_SIZE)
        width, height = blf.dimensions(_FONT_ID, text)
        box_width = width + _HUD_PAD_X * 2
        box_height = height + _HUD_PAD_Y * 2
        box_x = (region.width - box_width) * 0.5
        box_y = (region.height - box_height) * 0.5
        x = box_x + _HUD_PAD_X
        y = box_y + _HUD_PAD_Y

        _draw_background_box(box_x, box_y, box_width, box_height)

        try:
            blf.enable(_FONT_ID, blf.SHADOW)
            blf.shadow(_FONT_ID, 5, 0.0, 0.0, 0.0, 0.65)
            blf.shadow_offset(_FONT_ID, 1, -1)
        except Exception:
            pass

        blf.color(_FONT_ID, 0.92, 0.95, 1.0, 0.95)
        blf.position(_FONT_ID, x, y, 0)
        blf.draw(_FONT_ID, text)

        try:
            blf.disable(_FONT_ID, blf.SHADOW)
        except Exception:
            pass
    except Exception:
        pass


def _draw_background_box(x: float, y: float, width: float, height: float) -> None:
    if gpu is None or batch_for_shader is None:
        return

    try:
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        vertices = (
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        )
        batch = batch_for_shader(shader, "TRI_FAN", {"pos": vertices})
        gpu.state.blend_set("ALPHA")
        shader.bind()
        shader.uniform_float("color", (0.03, 0.035, 0.045, 0.78))
        batch.draw(shader)
        gpu.state.blend_set("NONE")
    except Exception:
        pass


def _tag_view3d_redraw() -> None:
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass
