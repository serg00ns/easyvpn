from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import THEME_COOKIE_NAME, is_authenticated, login_redirect, normalize_theme, router as auth_router, safe_next_path
from app.connector import SSHClientConfig, SSHConnectionError, SSHConnector
from app.database import add_server, fetch_clients, fetch_servers, get_server_connection_details, init_database

app = FastAPI(title="easyvpn")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates
app.include_router(auth_router)


def build_server_items(servers: list[dict[str, str]], check_results: dict[str, dict[str, str]] | None = None) -> list[dict[str, str]]:
    check_results = check_results or {}
    return [
        {
            "id": server.get("id", ""),
            "dashboard_href": f"/servers/{server.get('id', '')}" if server.get("id") else "",
            "title": server.get("name") or server.get("id") or "Unknown server",
            "subtitle": (
                f"{server.get('region', 'Unknown region')}"
                f" · {server.get('ip_address', 'N/A')}"
                f" · user: {server.get('username', 'N/A')}"
                f" · {server.get('status', 'online')}"
            ),
            "check_message": check_results.get(server.get("id", ""), {}).get("message", ""),
            "check_kind": check_results.get(server.get("id", ""), {}).get("kind", ""),
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


def render_server_dashboard(
    request: Request,
    theme: str,
    server: dict[str, str],
    status_kind: str = "",
    status_message: str = "",
    command: str = "",
    command_exit_code: int | None = None,
    command_stdout: str = "",
    command_stderr: str = "",
    command_error: str = "",
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "server_dashboard.html",
        {
            "theme": theme,
            "active_path": "/servers",
            "is_authenticated": True,
            "server": server,
            "status_kind": status_kind,
            "status_message": status_message,
            "command": command,
            "command_exit_code": command_exit_code,
            "command_stdout": command_stdout,
            "command_stderr": command_stderr,
            "command_error": command_error,
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
    checked_server_id = request.query_params.get("check_server_id", "")
    checked_state = request.query_params.get("check_state", "")
    checked_message = request.query_params.get("check_message", "")

    check_results: dict[str, dict[str, str]] = {}
    if checked_server_id and checked_state and checked_message:
        check_results[checked_server_id] = {
            "kind": checked_state,
            "message": checked_message,
        }

    items = build_server_items(fetch_servers(), check_results)
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


@app.get("/servers/{server_id}")
async def server_dashboard_page(request: Request, server_id: str):
    if not is_authenticated(request):
        return login_redirect(f"/servers/{server_id}")

    server = get_server_connection_details(server_id)
    if server is None:
        return RedirectResponse(url="/servers", status_code=303)

    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    return render_server_dashboard(
        request=request,
        theme=theme,
        server=server,
        status_kind=request.query_params.get("check_state", ""),
        status_message=request.query_params.get("check_message", ""),
    )


@app.post("/servers/{server_id}/execute")
async def execute_server_command(request: Request, server_id: str, command: str = Form(...)):
    if not is_authenticated(request):
        return login_redirect(f"/servers/{server_id}")

    server = get_server_connection_details(server_id)
    if server is None:
        return RedirectResponse(url="/servers", status_code=303)

    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    trimmed_command = command.strip()
    if not trimmed_command:
        return render_server_dashboard(
            request=request,
            theme=theme,
            server=server,
            command_error="Command is required.",
            status_code=400,
        )

    try:
        connector = SSHConnector(
            SSHClientConfig(
                hostname=server["ip_address"],
                username=server["username"],
                private_key=server["ssh_private_key"],
                timeout_seconds=8,
            )
        )
        exit_code, stdout, stderr = connector.execute(trimmed_command)
        return render_server_dashboard(
            request=request,
            theme=theme,
            server=server,
            command=trimmed_command,
            command_exit_code=exit_code,
            command_stdout=stdout,
            command_stderr=stderr,
        )
    except SSHConnectionError as exc:
        return render_server_dashboard(
            request=request,
            theme=theme,
            server=server,
            command=trimmed_command,
            command_error=str(exc),
            status_code=502,
        )


@app.post("/servers/{server_id}/check-status")
async def check_server_status(request: Request, server_id: str, next_path: str = Form("/servers")):
    if not is_authenticated(request):
        return login_redirect("/servers")

    redirect_path = safe_next_path(next_path, "/servers")

    server = get_server_connection_details(server_id)
    if server is None:
        params = urlencode(
            {
                "check_server_id": server_id,
                "check_state": "error",
                "check_message": "Server not found",
            }
        )
        separator = "&" if "?" in redirect_path else "?"
        return RedirectResponse(url=f"{redirect_path}{separator}{params}", status_code=303)

    try:
        connector = SSHConnector(
            SSHClientConfig(
                hostname=server["ip_address"],
                username=server["username"],
                private_key=server["ssh_private_key"],
                timeout_seconds=8,
            )
        )
        with connector.connected_client():
            pass
        check_state = "ok"
        check_message = "SSH connection successful"
    except SSHConnectionError as exc:
        check_state = "error"
        check_message = str(exc)
    except Exception:
        check_state = "error"
        check_message = "Unexpected SSH error"

    params = urlencode(
        {
            "check_server_id": server_id,
            "check_state": check_state,
            "check_message": check_message,
        }
    )
    separator = "&" if "?" in redirect_path else "?"
    return RedirectResponse(url=f"{redirect_path}{separator}{params}", status_code=303)


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