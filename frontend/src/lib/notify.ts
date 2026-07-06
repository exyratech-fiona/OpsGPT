// Thin wrapper over the Web Notifications API. Fires desktop/OS notifications
// while the dashboard is open in any tab (including a backgrounded one). No
// service worker / push backend needed for that — this is intentionally simple.

export function notifySupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function notifyPermission(): NotificationPermission {
  return notifySupported() ? Notification.permission : "denied";
}

export async function ensureNotifyPermission(): Promise<NotificationPermission> {
  if (!notifySupported()) return "denied";
  if (Notification.permission === "default") {
    try {
      return await Notification.requestPermission();
    } catch {
      return Notification.permission;
    }
  }
  return Notification.permission;
}

export function showAlertNotification(title: string, body: string, tag?: string): void {
  if (!notifySupported() || Notification.permission !== "granted") return;
  try {
    const n = new Notification(title, { body, tag, icon: "/favicon.ico", renotify: !!tag } as NotificationOptions);
    n.onclick = () => {
      window.focus();
      n.close();
    };
  } catch {
    /* some browsers throw if constructed outside a SW in odd contexts */
  }
}
