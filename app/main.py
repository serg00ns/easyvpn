from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

THEME_COOKIE_NAME = "easyvpn_theme"

SERVERS = [
    {
        "id": "sg-1",
        "name": "Singapore Gateway",
        "region": "Singapore",
        "ip_address": "10.23.0.11",
        "username": "root",
        "status": "online",
    },
    {
        "id": "de-1",
        "name": "Berlin Edge",
        "region": "Germany",
        "ip_address": "10.23.0.21",
        "username": "ubuntu",
        "status": "online",
    },
    {
        "id": "us-1",
        "name": "Virginia Core",
        "region": "United States",
        "ip_address": "10.23.0.31",
        "username": "ec2-user",
        "status": "maintenance",
    },
]

CLIENTS = [
    {"id": "00", "name": "jhon", "status": "active"},
    {"id": "01", "name": "doe", "status": "revoked"},
    {"id": "02", "name": "jane", "status": "active"},
]

app = FastAPI(title="easyvpn")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def normalize_theme(value: str | None) -> Literal["dark", "light"]:
    return "light" if value == "light" else "dark"


def build_server_items() -> list[dict[str, str]]:
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
        for server in SERVERS
    ]


def build_client_items() -> list[dict[str, str]]:
    return [
        {
            "title": client.get("name") or client.get("id") or "Unknown client",
            "subtitle": f"id: {client.get('id', 'N/A')} · status: {client.get('status', 'unknown')}",
        }
        for client in CLIENTS
    ]


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/servers", status_code=302)


@app.get("/servers")
async def servers_page(request: Request):
    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    items = build_server_items()
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
            "active_path": "/servers",
        },
    )


@app.get("/clients")
async def clients_page(request: Request):
    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    items = build_client_items()
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
        },
    )


@app.post("/theme/toggle")
async def toggle_theme(request: Request, next_path: str = Form("/servers")):
    current = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    next_theme = "light" if current == "dark" else "dark"

    response = RedirectResponse(url=next_path if next_path.startswith("/") else "/servers", status_code=303)
    response.set_cookie(
        key=THEME_COOKIE_NAME,
        value=next_theme,
        max_age=365 * 24 * 60 * 60,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/api/servers")
async def servers_api():
    return {"servers": SERVERS}


@app.get("/api/clients")
async def clients_api():
    return {"clients": CLIENTS}


@app.exception_handler(404)
async def not_found_page(request: Request, _exc):
    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    return templates.TemplateResponse(
        request,
        "not_found.html",
        {
            "theme": theme,
            "active_path": "",
        },
        status_code=404,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)