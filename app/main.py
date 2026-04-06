from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import THEME_COOKIE_NAME, is_authenticated, login_redirect, normalize_theme, router as auth_router, safe_next_path
from app.database import add_server, fetch_clients, fetch_servers, init_database

app = FastAPI(title="easyvpn")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates
app.include_router(auth_router)


def build_server_items(servers: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "title": server.get("name") or server.get("id") or "Unknown server",
            "subtitle": (
                f"{server.get('region', 'Unknown region')}"
                f" · {server.get('ip_address', 'N/A')}"
                f" · user: {server.get('username', 'N/A')}"
                f" · {server.get('status', 'online')}"
            ),
        }
        for server in servers
    ]


def build_client_items(clients: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "title": client.get("name") or client.get("id") or "Unknown client",
            "subtitle": f"id: {client.get('id', 'N/A')} · status: {client.get('status', 'unknown')}",
        }
        for client in clients
    ]


def render_server_form(
    request: Request,
    theme: str,
    error_message: str,
    form_data: dict[str, str],
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "server_form.html",
        {
            "theme": theme,
            "active_path": "/servers",
            "is_authenticated": True,
            "error_message": error_message,
            "form_data": form_data,
        },
        status_code=status_code,
    )


@app.on_event("startup")
async def startup_event() -> None:
    init_database()


@app.get("/")
async def root(request: Request) -> RedirectResponse:
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/servers", status_code=302)


@app.get("/servers")
async def servers_page(request: Request):
    if not is_authenticated(request):
        return login_redirect("/servers")

    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    items = build_server_items(fetch_servers())
    return templates.TemplateResponse(
        request,
        "list_page.html",
        {
            "theme": theme,
            "page_name": "Servers",
            "page_hint": "Linux servers managed by easyvpn",
            "items": items,
            "error_message": "",
            "empty_title": "No servers found",
            "empty_text": "The API responded but returned an empty list.",
            "cta_href": "/clients",
            "cta_label": "View clients",
            "secondary_cta_href": "/servers/new",
            "secondary_cta_label": "Add Server",
            "active_path": "/servers",
            "is_authenticated": True,
        },
    )


@app.get("/servers/new")
async def add_server_page(request: Request):
    if not is_authenticated(request):
        return login_redirect("/servers/new")

    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    return render_server_form(
        request=request,
        theme=theme,
        error_message="",
        form_data={
            "name": "",
            "region": "",
            "ip_address": "",
            "username": "",
            "status": "online",
            "ssh_private_key": "",
        },
    )


@app.post("/servers/new")
async def add_server_submit(
    request: Request,
    name: str = Form(...),
    region: str = Form(...),
    ip_address: str = Form(...),
    username: str = Form(...),
    status: str = Form(...),
    ssh_private_key: str = Form(...),
):
    if not is_authenticated(request):
        return login_redirect("/servers/new")

    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    payload = {
        "name": name.strip(),
        "region": region.strip(),
        "ip_address": ip_address.strip(),
        "username": username.strip(),
        "status": status.strip(),
        "ssh_private_key": ssh_private_key.strip(),
    }

    if not all(payload.values()):
        return render_server_form(
            request=request,
            theme=theme,
            error_message="All fields are required.",
            form_data=payload,
            status_code=400,
        )

    add_server(
        name=payload["name"],
        region=payload["region"],
        ip_address=payload["ip_address"],
        username=payload["username"],
        status=payload["status"],
        ssh_private_key=payload["ssh_private_key"],
    )
    return RedirectResponse(url="/servers", status_code=303)


@app.get("/clients")
async def clients_page(request: Request):
    if not is_authenticated(request):
        return login_redirect("/clients")

    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    items = build_client_items(fetch_clients())
    return templates.TemplateResponse(
        request,
        "list_page.html",
        {
            "theme": theme,
            "page_name": "OVPN Clients",
            "page_hint": "OpenVPN client profiles (.ovpn)",
            "items": items,
            "error_message": "",
            "empty_title": "No OVPN clients found",
            "empty_text": "The API responded but returned an empty list.",
            "cta_href": "/servers",
            "cta_label": "View servers",
            "active_path": "/clients",
            "is_authenticated": True,
        },
    )


@app.post("/theme/toggle")
async def toggle_theme(request: Request, next_path: str = Form("/servers")):
    redirect_path = safe_next_path(next_path)
    if not is_authenticated(request):
        return login_redirect(redirect_path)

    current = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    next_theme = "light" if current == "dark" else "dark"

    response = RedirectResponse(url=redirect_path, status_code=303)
    response.set_cookie(
        key=THEME_COOKIE_NAME,
        value=next_theme,
        max_age=365 * 24 * 60 * 60,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/api/servers")
async def servers_api(request: Request):
    if not is_authenticated(request):
        return login_redirect("/api/servers")
    return {"servers": fetch_servers()}


@app.get("/api/clients")
async def clients_api(request: Request):
    if not is_authenticated(request):
        return login_redirect("/api/clients")
    return {"clients": fetch_clients()}


@app.exception_handler(404)
async def not_found_page(request: Request, _exc):
    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    return templates.TemplateResponse(
        request,
        "not_found.html",
        {
            "theme": theme,
            "active_path": "",
            "is_authenticated": is_authenticated(request),
        },
        status_code=404,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)