from projection_show.render import context


def test_visible_windowed_output_is_maximized_and_focused(monkeypatch):
    calls = []
    monkeypatch.setattr(
        context.glfw, "show_window", lambda window: calls.append(("show", window))
    )
    monkeypatch.setattr(
        context.glfw, "maximize_window", lambda window: calls.append(("maximize", window))
    )
    monkeypatch.setattr(
        context.glfw, "focus_window", lambda window: calls.append(("focus", window))
    )

    context.request_visible_window_attention("window", visible=True, fullscreen=False)

    assert calls == [("show", "window"), ("maximize", "window"), ("focus", "window")]


def test_visible_fullscreen_output_is_focused_without_windowed_maximize(monkeypatch):
    calls = []
    monkeypatch.setattr(
        context.glfw, "show_window", lambda window: calls.append(("show", window))
    )
    monkeypatch.setattr(
        context.glfw, "maximize_window", lambda window: calls.append(("maximize", window))
    )
    monkeypatch.setattr(
        context.glfw, "focus_window", lambda window: calls.append(("focus", window))
    )

    context.request_visible_window_attention("window", visible=True, fullscreen=True)

    assert calls == [("show", "window"), ("focus", "window")]


def test_hidden_output_does_not_request_desktop_attention(monkeypatch):
    calls = []
    monkeypatch.setattr(
        context.glfw, "show_window", lambda window: calls.append(("show", window))
    )
    monkeypatch.setattr(
        context.glfw, "maximize_window", lambda window: calls.append(("maximize", window))
    )
    monkeypatch.setattr(
        context.glfw, "focus_window", lambda window: calls.append(("focus", window))
    )

    context.request_visible_window_attention("window", visible=False, fullscreen=False)

    assert calls == []
