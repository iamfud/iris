"""Windows notification mirror — polls WinRT toasts and forwards to D1."""

import asyncio
import logging
import threading
import time

import pystray

import ws_bridge
from display_priority import PRIO_CORE_NOTIFY

log = logging.getLogger("iris.notif")

WINRT_AVAILABLE = False
try:
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener, UserNotificationListenerAccessStatus)
    from winrt.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
    WINRT_AVAILABLE = True
except ImportError:
    pass


class NotificationMirrorProvider:
    POLL_SECONDS = 3

    def __init__(self, cfg, serial_sender=None):
        self.cfg = cfg
        self.serial = serial_sender
        self._running = False
        self._last_id = 0
        self._lock = threading.Lock()
        self._last_notif = ""
        self._last_notif_time = 0.0

    def start(self):
        if not WINRT_AVAILABLE:
            log.warning("[notif] winrt not installed — disabled")
            return
        if not self.cfg.get("mirror_enabled", True):
            log.info("[notif] disabled via config")
            return
        self._running = True
        threading.Thread(target=self._run, daemon=True, name="notif-mirror").start()

    def stop(self):
        self._running = False

    def poll_data(self):
        with self._lock:
            return {"last_notif": self._last_notif}

    def menu_items(self):
        with self._lock:
            t = self._last_notif
        items = [pystray.MenuItem("Notification mirror: on", None, enabled=False)]
        if t:
            items.append(pystray.MenuItem(f"  {t[:30]}", None, enabled=False))
        return items

    def _run(self):
        while self._running:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._async_run())
            except Exception as e:
                log.error(f"[notif] crashed: {e}")
            finally:
                try:
                    loop.close()
                except Exception:
                    pass
            if self._running:
                log.info("[notif] restarting in 5s...")
                time.sleep(5)

    async def _async_run(self):
        listener = UserNotificationListener.current
        status = await listener.request_access_async()
        log.info(f"[notif] access status: {status}")
        if status != UserNotificationListenerAccessStatus.ALLOWED:
            log.warning(f"[notif] access denied ({status})")
            return
        existing = await listener.get_notifications_async(NotificationKinds.TOAST)
        with self._lock:
            for n in existing:
                if n.id > self._last_id:
                    self._last_id = n.id
        log.info(f"[notif] active — seeded last_id={self._last_id}")
        while self._running:
            await asyncio.sleep(self.POLL_SECONDS)
            try:
                await self._poll(listener)
            except Exception as e:
                log.debug(f"[notif] poll error: {e}")

    async def _poll(self, listener):
        notifs = await listener.get_notifications_async(NotificationKinds.TOAST)
        for n in notifs:
            with self._lock:
                if n.id <= self._last_id:
                    continue
                self._last_id = n.id
            app = self._get_app_name(n)
            title, body = self._get_text(n)
            log.debug(f"[notif] toast id={n.id}  app={app!r}  title={title!r}  body={body!r}")
            if not title and not body:
                continue

            # rate limit
            now = time.time()
            if now - self._last_notif_time < 3.0:
                continue
            self._last_notif_time = now

            # show title (sender/app) : body (message)
            if title and body:
                msg = f"{title}: {body}"[:120]
            else:
                msg = (title or body)[:120]

            with self._lock:
                self._last_notif = msg

            log.info(f"[notif] forwarding: {msg}")
            ws_bridge.broadcast({
                "type": "notification",
                "app": app,
                "title": title,
                "body": body,
                "timestamp": time.time(),
            })
            if self.serial:
                self.serial.send_notification(
                    "", msg, priority=PRIO_CORE_NOTIFY, key="core.mirror")

    def _get_app_name(self, n):
        try:
            name = n.app_info.display_info.display_name
            if name: return name
        except Exception:
            pass
        try:
            aumi = n.app_info.app_user_model_id or ""
            log.debug(f"[notif] aumi={aumi!r}")
            if aumi:
                return aumi.split("!")[0].split(".")[-1] if "." in aumi else aumi.split("!")[0]
        except Exception:
            pass
        return "Unknown"

    def _get_text(self, n):
        title = ""
        body = ""
        try:
            b = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
            if b:
                texts = [e.text for e in b.get_text_elements() if e.text and e.text.strip()]
                if len(texts) >= 2:
                    title, body = texts[0], " ".join(texts[1:])
                elif len(texts) == 1:
                    body = texts[0]
        except Exception:
            pass
        return title.strip(), body.strip()
