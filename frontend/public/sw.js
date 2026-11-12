/* ClassSniper Service Worker — handles Web Push & notification taps cleanly on iOS/Android/Desktop */

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  const showFallback = () =>
    self.registration.showNotification("ClassSniper Alert", {
      body: "A watched Cornell section changed availability!",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: "/" },
    });

  if (!event.data) {
    event.waitUntil(showFallback());
    return;
  }

  let data = {};
  try {
    data = event.data.json();
  } catch {
    data = { title: "ClassSniper Alert", body: event.data.text() || "Seat opened!" };
  }

  const title = data.title || "ClassSniper Alert";
  const options = {
    body: data.body || "Check Student Center now!",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    tag: data.tag || "classsniper-alert",
    renotify: true,
    requireInteraction: true,
    data: {
      url: data.url || "/",
      classNbr: data.classNbr || null,
    },
  };

  // Safari iOS 16.4+ strictly requires every push event to call showNotification()
  event.waitUntil(
    self.registration.showNotification(title, options).catch(showFallback)
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(targetUrl).catch(() => {});
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
      return undefined;
    })
  );
});
