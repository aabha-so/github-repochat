"""Retro horror-game authentication screens for RepoChat.

Implements a three-screen flow on top of the existing auth backend:

    LANDING (CONTEXT MENU)  ->  LOG IN  /  SIGN UP  ->  dashboard

All credentials are validated by the unchanged ``auth.py`` module
(SQLite + bcrypt). This file only provides the presentation layer.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from auth import create_user, verify_user

# ──────────────────────────────────────────────
# Assets
# ──────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
_STATIC = _ROOT / "static"

# Streamlit serves ./static at /app/static/<name> when
# server.enableStaticServing is enabled in .streamlit/config.toml.
_WALLPAPER_CANDIDATES = (
    "night_cat_wallpaper_4k_3840x2160.png",
    "cat_wallpaper.jpg",
    "cat_wallpaper.jpeg",
    "cat_wallpaper.png",
    "cat_wallpaper.webp",
    "wallpaper.jpg",
    "wallpaper.png",
)

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".avif")


def _wallpaper_url() -> str | None:
    """Return the served URL of the wallpaper, or None if absent."""
    for name in _WALLPAPER_CANDIDATES:
        if (_STATIC / name).is_file():
            return f"/app/static/{name}"

    # Any other image the user drops into static/ is used as the wallpaper.
    if _STATIC.is_dir():
        for path in sorted(_STATIC.iterdir()):
            if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
                return f"/app/static/{path.name}"

    return None


# ──────────────────────────────────────────────
# Styling (injected only while the auth gate is active,
# so the dashboard is untouched)
# ──────────────────────────────────────────────
def _inject_style() -> None:
    url = _wallpaper_url()
    if url:
        background = (
            f"background-image: url('{url}') !important;"
            "background-size: cover !important;"
            "background-position: center !important;"
            "background-repeat: no-repeat !important;"
            "background-attachment: fixed !important;"
        )
    else:
        # No wallpaper supplied yet: stay atmospheric, never substitute a random image.
        background = (
            "background-image: radial-gradient(circle at 50% 25%, #16222f 0%, #0a1018 55%, #05080c 100%) !important;"
            "background-attachment: fixed !important;"
        )

    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=VT323&family=Share+Tech+Mono&display=swap');

/* ── full-bleed stage ── */
.stApp {{
    {background}
    background-color: #05080c !important;
}}
[data-testid="stHeader"] {{
    background: transparent !important;
    box-shadow: none !important;
}}
[data-testid="stMain"],
[data-testid="stAppViewContainer"] {{
    background: transparent !important;
}}
[data-testid="stMainBlockContainer"],
.block-container {{
    max-width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
}}

/* ── subtle darkening for legibility (never covers the characters) ── */
.auth-scrim {{
    position: fixed;
    inset: 0;
    background: linear-gradient(180deg, rgba(3, 7, 12, 0.34) 0%, rgba(3, 7, 12, 0.06) 45%, rgba(3, 7, 12, 0.30) 100%);
    pointer-events: none;
    z-index: 1;
}}

/* ── menu / form panel ── */
.st-key-ctx_panel,
.st-key-auth_panel {{
    position: relative;
    z-index: 3;
    padding: 16px 20px 20px 20px !important;
    background: rgba(9, 15, 24, 0.82) !important;
    border: 1px solid rgba(196, 212, 222, 0.42) !important;
    border-radius: 2px !important;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.45), 0 18px 48px rgba(0, 0, 0, 0.55) !important;
    backdrop-filter: blur(1.5px);
    -webkit-backdrop-filter: blur(1.5px);
    animation: auth-fade 260ms ease-out both;
}}

/* the menu floats above the characters */
.st-key-ctx_panel {{
    width: min(340px, calc(100vw - 40px)) !important;
    margin: 9vh auto 0 auto !important;
}}

/* the taller forms step to the left so the characters are never covered */
.st-key-auth_panel {{
    width: clamp(264px, 33vw, 340px) !important;
    margin: 7vh auto 0 4.5vw !important;
}}

/* tight, menu-like vertical rhythm */
.st-key-ctx_panel {{
    gap: 0 !important;
    row-gap: 0 !important;
}}
.st-key-ctx_panel > .stElementContainer {{
    margin: 0 !important;
}}
.st-key-auth_panel {{
    gap: 6px !important;
    row-gap: 6px !important;
}}
/* keep every child inside the fixed-width panel */
.st-key-ctx_panel > div,
.st-key-auth_panel > div,
.st-key-ctx_panel .stButton,
.st-key-auth_panel .stTextInput,
.st-key-auth_panel .stButton,
.st-key-auth_panel .stTextInput > div {{
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
}}
.st-key-auth_panel .stTextInput [data-baseweb="input"],
.st-key-auth_panel .stTextInput [data-testid="stTextInputRootElement"] {{
    min-width: 0 !important;
    width: 100% !important;
}}
/* Streamlit sizes markdown blocks against the page, not the panel */
.st-key-ctx_panel .stMarkdown,
.st-key-auth_panel .stMarkdown,
.st-key-ctx_panel .stMarkdown > div,
.st-key-auth_panel .stMarkdown > div {{
    width: 100% !important;
    max-width: 100% !important;
}}
/* hide the rainbow "running" strip above the stage */
[data-testid="stDecoration"] {{
    display: none !important;
}}
/* password field + inline show/hide toggle */
.st-key-login_pw_wrap,
.st-key-signup_pw_wrap,
.st-key-signup_pw2_wrap {{
    position: relative !important;
}}
.st-key-login_pw_toggle,
.st-key-signup_pw_toggle,
.st-key-signup_pw2_toggle {{
    position: absolute !important;
    top: auto !important;
    bottom: 4px !important;
    right: 12px !important;
    transform: none !important;
    width: auto !important;
    max-width: 46px !important;
    z-index: 5 !important;
}}

@keyframes auth-fade {{
    from {{ opacity: 0; transform: translateY(-6px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}

/* ── typography ── */
.ctx-title {{
    font-family: 'VT323', 'Share Tech Mono', monospace !important;
    font-size: 26px !important;
    line-height: 1.15 !important;
    letter-spacing: 2.5px !important;
    text-transform: uppercase !important;
    color: #E9F1F5 !important;
    margin: 0 0 10px 0 !important;
    text-shadow: 0 0 8px rgba(150, 200, 220, 0.22);
}}
.ctx-sub {{
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 12px !important;
    line-height: 1.5 !important;
    color: #93A3AE !important;
    letter-spacing: 0.4px !important;
    margin: 0 0 16px 0 !important;
}}
.ctx-label {{
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 10.5px !important;
    letter-spacing: 1.6px !important;
    text-transform: uppercase !important;
    color: #7F8F9B !important;
    margin: 13px 0 5px 0 !important;
}}
/* first field under the subtitle shouldn't double up on spacing */
.st-key-auth_panel .stTextInput label p {{
    margin-top: 0 !important;
}}
.ctx-error {{
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 12.5px !important;
    color: #D98383 !important;
    border-left: 2px solid #8C4444 !important;
    padding: 3px 0 3px 9px !important;
    margin: 4px 0 10px 0 !important;
    line-height: 1.45 !important;
}}
.ctx-ok {{
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 12.5px !important;
    color: #8FBF9B !important;
    border-left: 2px solid #3F6B4C !important;
    padding: 3px 0 3px 9px !important;
    margin: 4px 0 10px 0 !important;
    line-height: 1.45 !important;
}}

/* ── menu rows ── */
.st-key-ctx_panel .stButton > button {{
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
    height: auto !important;
    min-height: 0 !important;
    padding: 5px 8px !important;
    margin: 0 !important;
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: #B7C4CC !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 16px !important;
    font-weight: 400 !important;
    letter-spacing: 0.5px !important;
    text-align: left !important;
    justify-content: flex-start !important;
    transform: none !important;
    transition: background 140ms ease, color 140ms ease !important;
}}
/* fixed-width selection marker so rows never shift */
.st-key-ctx_panel .stButton > button::before {{
    content: "";
    display: inline-block;
    flex: 0 0 15px;
    width: 15px;
    color: #CFE6F0;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 16px !important;
    line-height: 1;
    text-align: left;
}}
.st-key-ctx_panel .stButton > button[data-rc-sel="1"]::before {{
    content: ">";
}}
.st-key-ctx_panel .stButton > button p {{
    text-align: left !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 16px !important;
    margin: 0 !important;
}}
.st-key-ctx_panel .stButton > button:hover {{
    background: rgba(160, 190, 205, 0.16) !important;
    color: #EAF2F6 !important;
    transform: none !important;
}}
.st-key-ctx_panel .stButton > button:active {{
    transform: none !important;
}}
/* selected row (default highlight + keyboard navigation) */
.st-key-ctx_panel .stButton > button[data-rc-sel="1"] {{
    background: rgba(160, 190, 205, 0.22) !important;
    color: #EAF2F6 !important;
}}
.st-key-menu_login .stButton > button,
.st-key-menu_signup .stButton > button,
.st-key-menu_exit .stButton > button {{
    cursor: pointer !important;
}}

/* title-screen button */
.st-key-ctx_panel .st-key-start_auth .stButton > button {{
    width: 100% !important;
    min-height: 38px !important;
    padding: 8px 10px !important;
    margin: 6px 0 0 0 !important;
    background: rgba(140, 175, 195, 0.14) !important;
    border: 1px solid rgba(180, 205, 220, 0.42) !important;
    border-radius: 1px !important;
    color: #E8F1F6 !important;
    font-family: 'VT323', 'Share Tech Mono', monospace !important;
    font-size: 17px !important;
    letter-spacing: 1.5px !important;
    text-align: center !important;
    justify-content: center !important;
    transition: background 140ms ease, border-color 140ms ease !important;
}}
.st-key-ctx_panel .st-key-start_auth .stButton > button::before {{
    content: none !important;
}}
.st-key-ctx_panel .st-key-start_auth .stButton > button:hover {{
    background: rgba(150, 190, 210, 0.26) !important;
    border-color: rgba(200, 225, 240, 0.6) !important;
    color: #F2F8FB !important;
}}
.st-key-ctx_panel .st-key-start_auth .stButton > button p {{
    font-family: 'VT323', 'Share Tech Mono', monospace !important;
    font-size: 17px !important;
    letter-spacing: 1.5px !important;
    margin: 0 !important;
}}

/* ── form inputs ── */
.st-key-auth_panel .stTextInput [data-baseweb="input"] {{
    background: rgba(255, 255, 255, 0.035) !important;
    border: 1px solid rgba(170, 195, 210, 0.32) !important;
    border-radius: 1px !important;
    box-shadow: none !important;
    padding-right: 0 !important;
}}
/* the inner shell must not paint a second box */
.st-key-auth_panel .stTextInput [data-baseweb="base-input"] {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    width: 100% !important;
}}
.st-key-auth_panel .stTextInput [data-baseweb="input"]:focus-within {{
    border-color: #7FB8CC !important;
    box-shadow: 0 0 0 1px rgba(127, 184, 204, 0.35) !important;
}}
.st-key-auth_panel .stTextInput input {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #E6EEF3 !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 14px !important;
    caret-color: #8FD0E0 !important;
    padding: 6px 2px !important;
}}
/* leave room for the inline SHOW / HIDE control */
.st-key-login_pw_wrap input,
.st-key-signup_pw_wrap input,
.st-key-signup_pw2_wrap input {{
    padding-right: 46px !important;
}}
.st-key-auth_panel .stTextInput input::placeholder {{
    color: rgba(160, 180, 195, 0.45) !important;
    font-family: 'Share Tech Mono', monospace !important;
}}
.st-key-auth_panel .stTextInput > label,
.st-key-auth_panel .stTextInput label[data-testid="stWidgetLabel"] {{
    display: block !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    min-height: 0 !important;
    height: auto !important;
    line-height: 1.2 !important;
}}
.st-key-auth_panel .stTextInput label p {{
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 10.5px !important;
    line-height: 1.2 !important;
    letter-spacing: 1.6px !important;
    text-transform: uppercase !important;
    color: #7F8F9B !important;
    margin: 0 0 3px 0 !important;
}}

/* ── buttons inside the auth panel ── */
.st-key-auth_panel .stButton > button {{
    width: 100% !important;
    height: auto !important;
    min-height: 38px !important;
    padding: 6px 10px !important;
    margin: 0 !important;
    background: rgba(140, 175, 195, 0.14) !important;
    border: 1px solid rgba(180, 205, 220, 0.42) !important;
    border-radius: 1px !important;
    box-shadow: none !important;
    color: #E8F1F6 !important;
    font-family: 'VT323', 'Share Tech Mono', monospace !important;
    font-size: 19px !important;
    font-weight: 400 !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    transform: none !important;
    transition: background 140ms ease, border-color 140ms ease !important;
}}
.st-key-auth_panel .stButton > button p {{
    font-family: 'VT323', 'Share Tech Mono', monospace !important;
    font-size: 19px !important;
    letter-spacing: 2px !important;
    margin: 0 !important;
}}
.st-key-auth_panel .stButton > button:hover {{
    background: rgba(150, 190, 210, 0.26) !important;
    border-color: rgba(200, 225, 240, 0.6) !important;
    color: #F2F8FB !important;
    transform: none !important;
}}
.st-key-auth_panel .stButton > button:active {{
    transform: none !important;
}}
.st-key-auth_panel .stButton > button:disabled {{
    opacity: 0.45 !important;
    cursor: default !important;
}}

/* show / hide password + link buttons stay small and flat */
.st-key-login_pw_toggle .stButton > button,
.st-key-signup_pw_toggle .stButton > button,
.st-key-signup_pw2_toggle .stButton > button {{
    min-height: 34px !important;
    padding: 4px 2px !important;
    background: transparent !important;
    border: none !important;
    color: #8FB4C6 !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 10.5px !important;
    letter-spacing: 1px !important;
}}
.st-key-login_pw_toggle .stButton > button:hover,
.st-key-signup_pw_toggle .stButton > button:hover,
.st-key-signup_pw2_toggle .stButton > button:hover {{
    background: transparent !important;
    color: #CFE6F0 !important;
}}
.st-key-link_to_signup .stButton > button,
.st-key-link_to_login .stButton > button,
.st-key-back_menu_login .stButton > button,
.st-key-back_menu_signup .stButton > button,
.st-key-back_menu_exit .stButton > button {{
    width: 100% !important;
    min-height: 24px !important;
    padding: 2px 2px !important;
    background: transparent !important;
    border: none !important;
    color: #8A9BA6 !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 11px !important;
    letter-spacing: 1px !important;
    text-transform: none !important;
    text-align: left !important;
    justify-content: flex-start !important;
}}
.st-key-link_to_signup .stButton > button p,
.st-key-link_to_login .stButton > button p,
.st-key-back_menu_login .stButton > button p,
.st-key-back_menu_signup .stButton > button p,
.st-key-back_menu_exit .stButton > button p {{
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 11px !important;
    letter-spacing: 1px !important;
    margin: 0 !important;
}}
.st-key-link_to_signup .stButton > button:hover,
.st-key-link_to_login .stButton > button:hover,
.st-key-back_menu_login .stButton > button:hover,
.st-key-back_menu_signup .stButton > button:hover,
.st-key-back_menu_exit .stButton > button:hover {{
    background: transparent !important;
    color: #DCEBF2 !important;
}}

/* spinner */
.st-key-auth_panel .stSpinner > div {{
    border-top-color: #8FD0E0 !important;
}}
.st-key-auth_panel .stSpinner p {{
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 11px !important;
    color: #8FA6B4 !important;
    letter-spacing: 1px !important;
}}

/* ── responsive ── */
@media (max-height: 720px) {{
    .st-key-ctx_panel {{
        margin-top: 5vh !important;
    }}
    .st-key-auth_panel {{
        margin-top: 3vh !important;
        padding: 14px 16px 16px 16px !important;
    }}
    .st-key-auth_panel .ctx-title {{
        font-size: 21px !important;
        letter-spacing: 1.6px !important;
        margin-bottom: 6px !important;
    }}
    .st-key-auth_panel .ctx-sub {{
        margin-bottom: 8px !important;
    }}
    .st-key-auth_panel .stTextInput label p {{
        margin-bottom: 2px !important;
    }}
}}
@media (max-width: 760px) {{
    .st-key-ctx_panel {{
        width: calc(100vw - 28px) !important;
        margin-top: 5vh !important;
        padding: 14px 16px 16px 16px !important;
    }}
    .st-key-auth_panel {{
        width: calc(100vw - 28px) !important;
        margin-left: 14px !important;
    }}
    .ctx-title {{ font-size: 22px !important; letter-spacing: 1.6px !important; }}
}}
</style>
<div class="auth-scrim"></div>
""",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────
# Keyboard support (menu arrows / enter / escape)
# ──────────────────────────────────────────────
_KEYBOARD_JS = """
<script>
(function () {
  var doc = window.parent.document;
  var win = window.parent;
  /* Streamlit re-executes this on every rerun; drop the previous
     listener first so exactly one handler is ever bound. */
  if (win.__repochatKeyHandler) {
    try { doc.removeEventListener('keydown', win.__repochatKeyHandler, true); } catch (err) {}
  }
  win.__repochatAuthKeys = true;

  function menuButtons() {
    var panel = doc.querySelector('.st-key-ctx_panel');
    if (!panel) { return []; }
    return Array.prototype.slice.call(panel.querySelectorAll('button'));
  }

  function clickIn(sel) {
    var el = doc.querySelector(sel + ' button');
    if (el) { el.click(); return true; }
    return false;
  }

  function paint(btns, n) {
    btns.forEach(function (b, i) {
      /* the ">" marker and highlight come from CSS via this attribute */
      b.setAttribute('data-rc-sel', i === n ? '1' : '0');
    });
  }

  var handler = function (e) {
    var t = e.target;
    var inInput = !!(t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'));

    if (e.key === 'Escape') {
      if (clickIn('.st-key-back_menu_login') || clickIn('.st-key-back_menu_signup')) {
        e.preventDefault();
        return;
      }
    }

    if (e.key === 'Enter' && inInput && t.closest && t.closest('.st-key-auth_panel')) {
      e.preventDefault();
      if (!clickIn('.st-key-login_submit')) { clickIn('.st-key-signup_submit'); }
      return;
    }

    if (inInput) { return; }
    var btns = menuButtons();
    if (!btns.length) { return; }

    var idx = -1;
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].getAttribute('data-rc-sel') === '1') { idx = i; break; }
    }
    if (idx < 0) { idx = 0; paint(btns, 0); }

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      var def = doc.getElementById('rc-default-sel');
      if (def) { def.remove(); }
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      paint(btns, (idx + 1) % btns.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      paint(btns, (idx - 1 + btns.length) % btns.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      btns[idx].click();
    }
  };
  doc.addEventListener('keydown', handler, true);
  win.__repochatKeyHandler = handler;
})();
</script>
"""


# ──────────────────────────────────────────────
# State helpers
# ──────────────────────────────────────────────
_SCREENS = ("welcome", "menu", "login", "signup")


def _init_state() -> None:
    st.session_state.setdefault("auth_screen", "welcome")
    st.session_state.setdefault("auth_error", "")
    st.session_state.setdefault("auth_notice", "")
    st.session_state.setdefault("show_login_pw", False)
    st.session_state.setdefault("show_signup_pw", False)
    st.session_state.setdefault("show_signup_pw2", False)


def _go(screen: str, *, error: str = "", notice: str = "") -> None:
    """Switch screens without reloading the page."""
    st.session_state.auth_screen = screen if screen in _SCREENS else "menu"
    st.session_state.auth_error = error
    st.session_state.auth_notice = notice
    st.rerun()


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _messages() -> None:
    if st.session_state.auth_notice:
        st.markdown(
            f'<div class="ctx-ok">{_escape(st.session_state.auth_notice)}</div>',
            unsafe_allow_html=True,
        )
    if st.session_state.auth_error:
        st.markdown(
            f'<div class="ctx-error">{_escape(st.session_state.auth_error)}</div>',
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────
# Screens
# ──────────────────────────────────────────────
def _screen_menu() -> None:
    index = int(st.session_state.get("menu_index", 0)) % 3
    option_keys = ("menu_login", "menu_signup", "menu_exit")

    # Default selection highlight (JS hands this over on first arrow-key press).
    st.markdown(
        '<style id="rc-default-sel">'
        f".st-key-ctx_panel .st-key-{option_keys[index]} .stButton > button {{"
        "background: rgba(160, 190, 205, 0.22) !important;"
        "color: #EAF2F6 !important;"
        "}"
        f".st-key-ctx_panel .st-key-{option_keys[index]} .stButton > button::before {{"
        'content: ">";'
        "}</style>",
        unsafe_allow_html=True,
    )

    with st.container(key="ctx_panel"):
        st.markdown('<div class="ctx-title">Context Menu</div>', unsafe_allow_html=True)

        options = (
            ("Log In", "login", "menu_login"),
            ("Sign Up", "signup", "menu_signup"),
            ("Exit", "welcome", "menu_exit"),
        )
        for i, (label, target, key) in enumerate(options):
            if st.button(label, key=key):
                st.session_state.menu_index = i
                _go(target)


def _screen_login() -> None:
    # Carry over a username from a successful registration, if any.
    prefill = st.session_state.pop("login_prefill", "")
    if prefill:
        st.session_state["login_user"] = prefill

    with st.container(key="auth_panel"):
        st.markdown('<div class="ctx-title">Identification Required</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="ctx-sub">Enter your credentials to continue.</div>',
            unsafe_allow_html=True,
        )
        _messages()

        username = st.text_input(
            "Username",
            key="login_user",
            placeholder="Enter username",
        )

        with st.container(key="login_pw_wrap"):
            password = st.text_input(
                "Password",
                key="login_pw",
                placeholder="Enter password",
                type="default" if st.session_state.show_login_pw else "password",
            )
            if st.button(
                "HIDE" if st.session_state.show_login_pw else "SHOW",
                key="login_pw_toggle",
            ):
                st.session_state.show_login_pw = not st.session_state.show_login_pw
                st.rerun()

        if st.button("Log In", key="login_submit"):
            user = (username or "").strip()
            pwd = password or ""
            if not user:
                st.session_state.auth_error = "Username cannot be empty."
                st.rerun()
            if not pwd:
                st.session_state.auth_error = "Password cannot be empty."
                st.rerun()

            st.session_state.auth_error = ""
            with st.spinner("Authenticating..."):
                ok, msg = verify_user(user, pwd)
            if ok:
                st.session_state.logged_in_user = user
                st.session_state.auth_error = ""
                st.session_state.auth_notice = ""
                st.session_state.auth_screen = "menu"
                st.rerun()
            else:
                st.session_state.auth_error = msg
                st.rerun()

        if st.button("New here? SIGN UP", key="link_to_signup"):
            _go("signup")
        if st.button("< Back to menu", key="back_menu_login"):
            _go("menu")


def _screen_signup() -> None:
    with st.container(key="auth_panel"):
        st.markdown('<div class="ctx-title">New User Registration</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="ctx-sub">Create an account to access RepoChat.</div>',
            unsafe_allow_html=True,
        )
        _messages()

        username = st.text_input(
            "Username",
            key="signup_user",
            placeholder="Choose a username",
        )

        with st.container(key="signup_pw_wrap"):
            password = st.text_input(
                "Password",
                key="signup_pw",
                placeholder="Minimum 6 characters",
                type="default" if st.session_state.show_signup_pw else "password",
            )
            if st.button(
                "HIDE" if st.session_state.show_signup_pw else "SHOW",
                key="signup_pw_toggle",
            ):
                st.session_state.show_signup_pw = not st.session_state.show_signup_pw
                st.rerun()

        with st.container(key="signup_pw2_wrap"):
            password2 = st.text_input(
                "Confirm password",
                key="signup_pw2",
                placeholder="Repeat your password",
                type="default" if st.session_state.show_signup_pw2 else "password",
            )
            if st.button(
                "HIDE" if st.session_state.show_signup_pw2 else "SHOW",
                key="signup_pw2_toggle",
            ):
                st.session_state.show_signup_pw2 = not st.session_state.show_signup_pw2
                st.rerun()

        if st.button("Create Account", key="signup_submit"):
            user = (username or "").strip()
            pwd = password or ""
            pwd2 = password2 or ""

            error = ""
            if not user:
                error = "Username cannot be empty."
            elif not pwd:
                error = "Password cannot be empty."
            elif len(pwd) < 6:
                error = "Password must be at least 6 characters."
            elif pwd != pwd2:
                error = "Passwords do not match."

            if error:
                st.session_state.auth_error = error
                st.rerun()

            st.session_state.auth_error = ""
            with st.spinner("Creating account..."):
                ok, msg = create_user(user, pwd)
            if ok:
                # Existing behaviour: registration does NOT log the user in.
                st.session_state.login_prefill = user
                for key in ("signup_user", "signup_pw", "signup_pw2"):
                    st.session_state.pop(key, None)
                st.session_state.show_signup_pw = False
                st.session_state.show_signup_pw2 = False
                _go(
                    "login",
                    notice=f'Account created. You can now log in as "{user}".',
                )
            else:
                st.session_state.auth_error = msg
                st.rerun()

        if st.button("Already registered? LOG IN", key="link_to_login"):
            _go("login")
        if st.button("< Back to menu", key="back_menu_signup"):
            _go("menu")


def _screen_welcome() -> None:
    """Title screen: the first thing shown after a reload."""
    with st.container(key="ctx_panel"):
        st.markdown('<div class="ctx-title">RepoChat</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="ctx-sub">Codebase intelligence for public GitHub repositories. '
            "Sign in, or create an account to continue.</div>",
            unsafe_allow_html=True,
        )
        if st.button("Return to login / signup", key="start_auth"):
            _go("menu")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def render_auth() -> None:
    """Render the full retro authentication experience."""
    _init_state()
    _inject_style()

    screen = st.session_state.auth_screen
    if screen == "welcome":
        _screen_welcome()
    elif screen == "login":
        _screen_login()
    elif screen == "signup":
        _screen_signup()
    else:
        _screen_menu()

    components.html(_KEYBOARD_JS, height=0, width=0)
