/* Service worker do app do aluno (escopo /app/).
 * - guarda o "casco" do app (HTML e arquivos estáticos do Next) para abrir mesmo sem internet;
 * - NUNCA guarda respostas da API (/app/api/*): dados de aula e sessão só vêm da rede;
 * - sem rede, navegação cai numa página offline amigável.
 */
const VERSAO = "v1";
const CASCO = "aluno-casco-" + VERSAO;
const ESTATICO = "aluno-estatico-" + VERSAO;
const OFFLINE = "/app/offline.html";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CASCO).then((c) => c.addAll([OFFLINE, "/app/icon.svg"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n.startsWith("aluno-") && n !== CASCO && n !== ESTATICO).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/app/api/")) return; // dados e sessão: sempre rede, nunca cache

  // navegação dentro do app: rede primeiro; sem rede, a última cópia do casco ou a página offline
  if (req.mode === "navigate" && url.pathname.startsWith("/app")) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && !res.redirected) {
            const copia = res.clone();
            caches.open(CASCO).then((c) => c.put(req, copia));
          }
          return res;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match(OFFLINE))),
    );
    return;
  }

  // arquivos estáticos do Next (nomes com hash) e ícones: cache primeiro
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/app/icone/") || url.pathname === "/app/icon.svg") {
    e.respondWith(
      caches.match(req).then(
        (r) =>
          r ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copia = res.clone();
              caches.open(ESTATICO).then((c) => c.put(req, copia));
            }
            return res;
          }),
      ),
    );
  }
});
