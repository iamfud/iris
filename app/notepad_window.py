"""Iris Notepad Window — Native Tkinter Implementation.

Directly bridges all notepad requests to the featherweight native Tkinter
QuickNoteWindow in quick_note.py, completely eliminating the legacy
pywebview / WebView2 subprocess overhead.
"""

import logging

try:
    import quick_note
    import ws_bridge
except ImportError:
    from app import quick_note
    from app import ws_bridge

log = logging.getLogger("iris.notepad_window")


def open_notepad(app_tag="general", filename=None, initial_title=None, initial_body=None, engine=None, toggle=False, root=None, app=None):
    """Open, bring to front, or toggle the dedicated native Iris Notepad window."""
    try:
        target_fn = quick_note.toggle_quick_note if toggle else quick_note.open_quick_note
        if app is None:
            app = getattr(ws_bridge, "_app", None)
        if root is None:
            root = getattr(app, "_root", None) if app else None

        if root:
            root.after(0, lambda: target_fn(
                root=root,
                app=app,
                app_tag=app_tag,
                filename=filename,
                initial_title=initial_title,
                initial_body=initial_body,
            ))
        else:
            target_fn(
                root=None,
                app=app,
                app_tag=app_tag,
                filename=filename,
                initial_title=initial_title,
                initial_body=initial_body,
            )
    except Exception as ex:
        log.warning("[notepad_window] Failed to dispatch native notepad: %s", ex)


def toggle_notepad(app_tag="general", filename=None, initial_title=None, initial_body=None, root=None, app=None):
    """Toggle Iris Note: if open in foreground, send to back; else bring to front."""
    open_notepad(app_tag=app_tag, filename=filename, initial_title=initial_title, initial_body=initial_body, toggle=True, root=root, app=app)


def is_notepad_open():
    """Return True if the native notepad window is currently open."""
    return quick_note.is_quick_note_open()


def close_notepad():
    """Close the active notepad window if open."""
    quick_note.close_quick_note()


if __name__ == "__main__":
    open_notepad()
