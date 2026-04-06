from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import user_exists, verify_user

THEME_COOKIE_NAME = "easyvpn_theme"
AUTH_COOKIE_NAME = "easyvpn_auth"

router = APIRouter()


def normalize_theme(value: str | None) -> Literal["dark", "light"]:
    return "light" if value == "light" else "dark"


def is_authenticated(request: Request) -> bool:
    username = request.cookies.get(AUTH_COOKIE_NAME)
    if not username:
        return False
    return user_exists(username)


def safe_next_path(value: str | None, fallback: str = "/servers") -> str:
    if not value:
        return fallback
    return value if value.startswith("/") else fallback


def login_redirect(next_path: str) -> RedirectResponse:
    encoded_next = quote(next_path, safe="/")
    return RedirectResponse(url=f"/login?next={encoded_next}", status_code=303)


def get_templates(request: Request) -> Jinja2Templates:
    templates = getattr(request.app.state, "templates", None)
    if templates is None:
        raise RuntimeError("Templates are not configured on app.state.templates")
    return templates


@router.get("/login")
async def login_page(request: Request, next: str = "/servers"):
    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    if is_authenticated(request):
        return RedirectResponse(url=safe_next_path(next), status_code=302)

    templates = get_templates(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "theme": theme,
            "active_path": "",
            "is_authenticated": False,
            "error_message": "",
            "next_path": safe_next_path(next),
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_path: str = Form("/servers"),
):
    theme = normalize_theme(request.cookies.get(THEME_COOKIE_NAME))
    redirect_path = safe_next_path(next_path)

    if not verify_user(username, password):
        templates = get_templates(request)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "theme": theme,
                "active_path": "",
                "is_authenticated": False,
                "error_message": "Invalid username or password.",
                "next_path": redirect_path,
            },
            status_code=401,
        )

    response = RedirectResponse(url=redirect_path, status_code=303)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=username,
        httponly=True,
        max_age=24 * 60 * 60,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return response
