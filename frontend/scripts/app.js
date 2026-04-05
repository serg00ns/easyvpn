const serversState = {
  status: "idle",
  items: [],
  errorMessage: "",
};

const clientsState = {
  status: "idle",
  items: [],
  errorMessage: "",
};

const runtimeConfig = window.EASYVPN_CONFIG || {};
const API_BASE_URL = String(runtimeConfig.API_BASE_URL || "").replace(/\/$/, "");
const SERVERS_ENDPOINT = runtimeConfig.SERVERS_ENDPOINT || "/api/servers";
const CLIENTS_ENDPOINT = runtimeConfig.CLIENTS_ENDPOINT || "/api/clients";
const REQUEST_TIMEOUT_MS = Number(runtimeConfig.REQUEST_TIMEOUT_MS) || 10000;

function getApiUrl(endpoint) {
  if (endpoint.startsWith("http://") || endpoint.startsWith("https://")) {
    return endpoint;
  }
  return `${API_BASE_URL}${endpoint}`;
}

function getJwtToken() {
  return localStorage.getItem("easyvpn_jwt") || "";
}

function normalizeServers(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload?.servers)) {
    return payload.servers;
  }
  return [];
}

function normalizeClients(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload?.clients)) {
    return payload.clients;
  }
  return [];
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderServerRows() {
  if (serversState.status === "loading") {
    return `
      <li class="server-list-item">
        <strong>Loading servers...</strong>
        <span>Fetching /api/servers</span>
      </li>
    `;
  }

  if (serversState.status === "error") {
    const message = serversState.errorMessage || "Could not load servers from /api/servers.";
    return `
      <li class="server-list-item server-list-item-error">
        <span class="warn-triangle" aria-hidden="true">!</span>
        <div>
          <strong>Server list error</strong>
          <span>${escapeHtml(message)}</span>
        </div>
      </li>
    `;
  }

  if (serversState.status === "ready" && serversState.items.length > 0) {
    return serversState.items
      .map((server, index) => {
        const name = escapeHtml(server?.name || server?.id || `Server ${index + 1}`);
        const region = escapeHtml(server?.region || server?.location || "Unknown region");
        const status = escapeHtml(server?.status || "online");
        return `
          <li class="server-list-item">
            <strong>${name}</strong>
            <span>${region} · ${status}</span>
          </li>
        `;
      })
      .join("");
  }

  return `
    <li class="server-list-item">
      <strong>No servers found</strong>
      <span>The API responded but returned an empty list.</span>
    </li>
  `;
}

async function fetchServers() {
  if (serversState.status === "loading") {
    return;
  }

  serversState.status = "loading";
  serversState.errorMessage = "";
  render();

  try {
    const token = getJwtToken();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const headers = {
      Accept: "application/json",
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(getApiUrl(SERVERS_ENDPOINT), {
      method: "GET",
      headers,
      signal: controller.signal,
    });

    window.clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const data = await response.json();
    serversState.items = normalizeServers(data);
    serversState.status = "ready";
  } catch (error) {
    serversState.items = [];
    serversState.status = "error";
    serversState.errorMessage = error instanceof Error ? error.message : "Could not load server list";
  }

  render();
}

function renderClientRows() {
  if (clientsState.status === "loading") {
    return `
      <li class="server-list-item">
        <strong>Loading clients...</strong>
        <span>Fetching /api/clients</span>
      </li>
    `;
  }

  if (clientsState.status === "error") {
    const message = clientsState.errorMessage || "Could not load clients from /api/clients.";
    return `
      <li class="server-list-item server-list-item-error">
        <span class="warn-triangle" aria-hidden="true">!</span>
        <div>
          <strong>Client list error</strong>
          <span>${escapeHtml(message)}</span>
        </div>
      </li>
    `;
  }

  if (clientsState.status === "ready" && clientsState.items.length > 0) {
    return clientsState.items
      .map((client, index) => {
        const name = escapeHtml(client?.name || client?.id || `Client ${index + 1}`);
        const platform = escapeHtml(client?.platform || client?.os || "Unknown platform");
        const version = escapeHtml(client?.version || "latest");
        return `
          <li class="server-list-item">
            <strong>${name}</strong>
            <span>${platform} · ${version}</span>
          </li>
        `;
      })
      .join("");
  }

  return `
    <li class="server-list-item">
      <strong>No clients found</strong>
      <span>The API responded but returned an empty list.</span>
    </li>
  `;
}

async function fetchClients() {
  if (clientsState.status === "loading") {
    return;
  }

  clientsState.status = "loading";
  clientsState.errorMessage = "";
  render();

  try {
    const token = getJwtToken();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const headers = {
      Accept: "application/json",
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(getApiUrl(CLIENTS_ENDPOINT), {
      method: "GET",
      headers,
      signal: controller.signal,
    });

    window.clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const data = await response.json();
    clientsState.items = normalizeClients(data);
    clientsState.status = "ready";
  } catch (error) {
    clientsState.items = [];
    clientsState.status = "error";
    clientsState.errorMessage = error instanceof Error ? error.message : "Could not load client list";
  }

  render();
}

const routes = {
  "/servers": () => `
    <section class="card">
      <span class="pill">Servers</span>
      <ul class="server-list" aria-live="polite">
        ${renderServerRows()}
      </ul>
      <a class="cta" href="#/clients">View clients</a>
    </section>
  `,

  "/clients": () => `
    <section class="card">
      <span class="pill">Clients</span>
      <ul class="server-list" aria-live="polite">
        ${renderClientRows()}
      </ul>
      <a class="cta" href="#/servers">View servers</a>
    </section>
  `,
};

const notFound = () => `
  <section class="card">
    <span class="pill">404</span>
    <h2>Page not found</h2>
    <p class="lead">That route does not exist yet. Use the navigation to continue.</p>
    <a class="cta" href="#/servers">Go to servers</a>
  </section>
`;

const THEME_COOKIE_NAME = "easyvpn_theme";

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return decodeURIComponent(parts.pop().split(";").shift());
  }
  return null;
}

function setCookie(name, value, days) {
  const maxAge = days * 24 * 60 * 60;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; samesite=lax`;
}

function getTheme() {
  const cookieTheme = getCookie(THEME_COOKIE_NAME);
  return cookieTheme === "light" ? "light" : "dark";
}

function applyTheme(theme) {
  const validTheme = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", validTheme);
  const toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.textContent = validTheme === "dark" ? "Light Mode" : "Dark Mode";
  }
}

function initThemeToggle() {
  const toggle = document.getElementById("theme-toggle");
  if (!toggle) {
    return;
  }

  applyTheme(getTheme());

  toggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    setCookie(THEME_COOKIE_NAME, next, 365);
  });
}

function getCurrentPath() {
  const hash = window.location.hash || "#/servers";
  const path = hash.slice(1);
  return path === "/" || !path ? "/servers" : path;
}

function updateActiveLinks(path) {
  const links = document.querySelectorAll("[data-link]");
  links.forEach((link) => {
    const linkPath = new URL(link.href).hash.slice(1) || "/servers";
    link.classList.toggle("active", linkPath === path);
  });
}

function render() {
  const app = document.getElementById("app");
  const path = getCurrentPath();
  const page = routes[path] || notFound;

  app.innerHTML = page();
  updateActiveLinks(path);

  if (path === "/servers" && serversState.status === "idle") {
    fetchServers();
  }

  if (path === "/clients" && clientsState.status === "idle") {
    fetchClients();
  }
}

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
  render();
});
