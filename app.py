"""RepoChat Streamlit User Interface.

Provides a clean chat interface for public GitHub repository Q&A.
Maintains repo URL, chat history, and index path in st.session_state across reruns.
A login gate (auth.py) guards the app: users must sign up or log in first.
"""

from pathlib import Path
import re
import shutil
import time

import streamlit as st
import streamlit.components.v1 as components

# Page configuration MUST be the very first Streamlit command executed
st.set_page_config(page_title="RepoChat", page_icon=":material/code:", layout="wide")

# Load Custom CSS
with open("assets/style.css", encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

import config  # Ensures telemetry mutes and global settings load first
from auth import create_user, verify_user
from indexer import index_repository
from loader import RepoTooLargeError, load_repository
from retriever import query_repo


def init_session_state() -> None:
    """Initialize persistent session variables if not already present."""
    defaults = {
        "messages": [], "repo_url": "", "index_path": None, "owner": "", "repo": "",
        "commit_sha": "", "files": [], "collection": None, "logged_in_user": None,
        "auth_view": "login", "view": "chat", "answer_style": "Concise", "top_k": 5,
        "show_sources": True,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session_state()

# ──────────────────────────────────────────────
# Login / Sign-up Gate
# ──────────────────────────────────────────────
if st.session_state.logged_in_user is None:
    st.markdown(
        '<div style="text-align: center; padding: 12px 0 16px;">'
        '<div class="hero-orb hero-orb-idle"><div class="hero-orb-inner"></div></div>'
        '<div class="hero-title">RepoChat</div>'
        '<div class="hero-subtitle">Sign in to start exploring repositories.</div></div>',
        unsafe_allow_html=True,
    )

    # ── View toggle ──
    col_l, col_r = st.columns(2)
    with col_l:
        if st.button("Log In", use_container_width=True,
                     type="primary" if st.session_state.auth_view == "login" else "secondary",
                     key="btn_switch_login"):
            st.session_state.auth_view = "login"
            st.rerun()
    with col_r:
        if st.button("Sign Up", use_container_width=True,
                     type="primary" if st.session_state.auth_view == "signup" else "secondary",
                     key="btn_switch_signup"):
            st.session_state.auth_view = "signup"
            st.rerun()

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

    if st.session_state.auth_view == "login":
        if st.session_state.get("signup_success_msg"):
            st.success(st.session_state.pop("signup_success_msg"))
        with st.form("login_form", border=False):
            prefill = st.session_state.pop("login_prefill", "")
            login_user = st.text_input("Username", value=prefill, placeholder="Your username")
            login_pass = st.text_input("Password", type="password", placeholder="Your password")
            submit_login = st.form_submit_button("Log In", type="primary", use_container_width=True)
            if submit_login:
                ok, msg = verify_user(login_user, login_pass)
                if ok:
                    st.session_state.logged_in_user = login_user.strip()
                    st.rerun()
                else:
                    st.error(msg)

    else:  # signup view
        with st.form("signup_form", border=False):
            signup_user = st.text_input("Choose a username", placeholder="e.g. jane_doe")
            signup_pass = st.text_input("Choose a password", type="password", placeholder="Min. 6 characters")
            signup_pass2 = st.text_input("Confirm password", type="password", placeholder="Repeat your password")
            submit_signup = st.form_submit_button("Create Account", type="primary", use_container_width=True)
            if submit_signup:
                if not signup_user.strip():
                    st.error("Username cannot be empty.")
                elif not signup_pass:
                    st.error("Password cannot be empty.")
                elif len(signup_pass) < 6:
                    st.error("Password must be at least 6 characters.")
                elif signup_pass != signup_pass2:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = create_user(signup_user, signup_pass)
                    if ok:
                        st.session_state.signup_success_msg = f'Account created! You can now log in as "{signup_user.strip()}".'
                        st.session_state.login_prefill = signup_user.strip()
                        st.session_state.auth_view = "login"
                        st.rerun()
                    else:
                        st.error(msg)

    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.stop()

# ──────────────────────────────────────────────
# Sidebar
# Contains only: title, repo URL input, index button, status & stat cards
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="padding: 0 0 12px; text-align: center;">'
        '<div style="font-weight: 800; font-size: 20px; letter-spacing: -0.04em; color: var(--ink);">RepoChat</div>'
        '<div style="font-size: 12px; color: var(--ink-tertiary); margin-top: 4px; letter-spacing: 0.04em; text-transform: uppercase;">Codebase Intelligence</div>'
        '</div>',
        unsafe_allow_html=True
    )
    st.markdown('<div style="font-size: 11px; font-weight: 700; color: var(--ink-tertiary); letter-spacing: 0.1em; margin-bottom: 8px; text-transform: uppercase;">Repository</div>', unsafe_allow_html=True)

    repo_input = st.text_input(
        "GitHub Repository URL", value=st.session_state.repo_url, placeholder="https://github.com/psf/requests",
        help="Paste a public GitHub repo URL.", label_visibility="collapsed", key="repo_url_input"
    )
    if "repo_url_input" in st.session_state:
        new_url = st.session_state.repo_url_input.strip()
        if new_url and new_url != st.session_state.repo_url:
            st.session_state.repo_url = new_url
            st.session_state.index_path = None
            st.session_state.collection = None
            st.rerun()

    if st.button("Index Repository", type="primary", use_container_width=True):
        if not repo_input.strip():
            st.error("Please enter a valid GitHub repository URL.")
        else:
            with st.status("Indexing repository...", expanded=True) as status:
                status.update(label="Downloading repository...", state="running")
                try:
                    files, owner, repo, commit_sha = load_repository(repo_input.strip())
                    status.update(label=f"Indexing {len(files)} files...", state="running")
                    collection, index_path, is_cached = index_repository(files, owner, repo, commit_sha)
                    st.session_state.repo_url = repo_input.strip()
                    st.session_state.owner, st.session_state.repo = owner, repo
                    st.session_state.commit_sha = commit_sha
                    st.session_state.files, st.session_state.collection = files, collection
                    st.session_state.index_path = index_path
                    st.session_state.messages = []
                    if collection.count() == 0:
                        status.update(label="No valid text chunks found.", state="error")
                        st.session_state.collection = None
                    else:
                        label = "Reusing cached index" if is_cached else "Indexed successfully"
                        status.update(label=f"{label} — {len(files)} files", state="complete")
                        st.session_state.just_indexed = True
                except RepoTooLargeError as exc:
                    status.update(label=f"Repository too large: {exc}", state="error")
                except Exception as exc:
                    status.update(label=f"Failed: {exc}", state="error")

    if st.session_state.index_path:
        st.markdown('<div style="margin: 12px 0 8px; border-bottom: 1px solid var(--surface-border);"></div>', unsafe_allow_html=True)
        def render_status_card(label: str, value: str) -> str:
            return (f'<div class="glass-card" style="margin-bottom: 6px;">'
                    f'<div style="font-size: 10px; font-weight: 700; color: var(--ink-tertiary); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 2px;">{label}</div>'
                    f'<div style="font-family: \'JetBrains Mono\', monospace; font-size: 13px; color: var(--ink);">{value}</div></div>')

        st.markdown(render_status_card("Repository", f"{st.session_state.owner}/{st.session_state.repo}"), unsafe_allow_html=True)
        st.markdown(render_status_card("Files", str(len(st.session_state.files))), unsafe_allow_html=True)
        if st.button("New chat", icon=":material/add:", use_container_width=True, key="btn_sidebar_new_chat"):
            st.session_state.messages = []
            st.session_state.scroll_to_top = True
            st.rerun()

# ──────────────────────────────────────────────
# Dialogs: About & Settings
# ──────────────────────────────────────────────
@st.dialog("How to use RepoChat", width="small")
def show_about_dialog() -> None:
    """User guide explaining how to use RepoChat in 6 simple steps."""
    st.markdown(
        "1. **Paste a repository link**: Copy the URL of any public GitHub repository into the box in the left panel.\n"
        "2. **Index the repository**: Click \"Index Repository\" and wait until you see the confirmation. Large repositories take longer.\n"
        "3. **Ask your question**: Type a question in the chat box or click one of the suggested cards.\n"
        "4. **Read the answer**: Answers come from the repository's real code and documentation.\n"
        "5. **Ask follow-ups**: Keep asking in the same chat to go deeper into a file or feature.\n"
        "6. **Adjust your preferences**: Open Settings to change answer style (concise or detailed), how much code is searched, and to re-index a repository.\n\n"
        "**Tips**\n"
        "- Be specific, for example \"What does login.py do?\" works better than \"Explain the code\".\n"
        "- Only public repositories are supported.\n"
        "- If an answer seems incomplete, re-index the repository from Settings and try again."
    )


@st.dialog("Settings", width="small")
def show_settings_dialog() -> None:
    """Settings modal with retrieval configurations and account logout."""
    st.markdown("**Answer style**")
    st.caption("Choose how detailed the AI's answers should be.")
    st.session_state.answer_style = st.radio(
        "Answer style", options=["Concise", "Detailed"],
        index=0 if st.session_state.answer_style == "Concise" else 1,
        horizontal=True, label_visibility="collapsed", key="settings_answer_style",
    )
    st.markdown('<div style="margin: 16px 0 4px; border-bottom: 1px solid var(--surface-border);"></div>', unsafe_allow_html=True)

    st.markdown("**Code chunks retrieved (top-k)**")
    st.caption("How many code snippets the retriever fetches per question.")
    st.session_state.top_k = st.slider("top_k", min_value=3, max_value=10, value=st.session_state.top_k, step=1, label_visibility="collapsed", key="settings_top_k")
    st.markdown('<div style="margin: 16px 0 4px; border-bottom: 1px solid var(--surface-border);"></div>', unsafe_allow_html=True)

    st.markdown("**Show sources**")
    st.caption("Display the source file chips below each answer.")
    st.session_state.show_sources = st.toggle("Show sources", value=st.session_state.show_sources, label_visibility="collapsed", key="settings_show_sources")
    st.markdown('<div style="margin: 16px 0 4px; border-bottom: 1px solid var(--surface-border);"></div>', unsafe_allow_html=True)

    st.markdown("**Re-index repository**")
    st.caption("Delete the cached index for the current repo and rebuild it from scratch.")
    if st.session_state.index_path:
        if st.button("Re-index now", type="primary", key="btn_reindex"):
            try:
                shutil.rmtree(str(st.session_state.index_path))
            except Exception:
                pass
            with st.spinner("Re-indexing repository..."):
                try:
                    files = st.session_state.files
                    if not files and st.session_state.repo_url:
                        files, owner, repo, commit_sha = load_repository(st.session_state.repo_url)
                        st.session_state.files = files
                        st.session_state.owner, st.session_state.repo = owner, repo
                        st.session_state.commit_sha = commit_sha
                    collection, index_path, _ = index_repository(
                        st.session_state.files, st.session_state.owner, st.session_state.repo, st.session_state.commit_sha
                    )
                    st.session_state.collection, st.session_state.index_path = collection, index_path
                    st.session_state.messages = []
                    st.success("Repository re-indexed successfully!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Re-indexing failed: {exc}")
    else:
        st.info("No repository is indexed yet.")
    st.markdown('<div style="margin: 16px 0 4px; border-bottom: 1px solid var(--surface-border);"></div>', unsafe_allow_html=True)

    st.markdown("**Account**")
    st.markdown(f'Signed in as <strong>{st.session_state.logged_in_user}</strong>', unsafe_allow_html=True)
    if st.button("Log Out", key="btn_settings_logout"):
        st.session_state.clear()
        st.rerun()

# ──────────────────────────────────────────────
# Fixed Top Action Bar (How to use & Settings)
# ──────────────────────────────────────────────
with st.container(key="topbar"):
    bar_about, bar_settings = st.columns(2, gap="small")
    with bar_about:
        if st.button("How to use", icon=":material/info:", key="btn_about"):
            show_about_dialog()
    with bar_settings:
        if st.button("Settings", icon=":material/settings:", key="btn_settings"):
            show_settings_dialog()

# Scroll to top after indexing completes or New chat
_SCROLL_JS = (
    '<script>'
    'var m=window.parent.document.querySelector(\'[data-testid="stMain"]\')'
    '||window.parent.document.querySelector("section.main");'
    'if(m){m.scrollTop=0;setTimeout(function(){m.scrollTop=0;},150);}'
    '</script>'
)

# Smooth scroll to keep latest question and answer positioned above the input section
_SCROLL_BOTTOM_JS = (
    '<script>'
    'var m=window.parent.document.querySelector(\'[data-testid="stMain"]\')'
    '||window.parent.document.querySelector("section.main");'
    'if(m){m.scrollTo({top: m.scrollHeight, behavior: "smooth"});}'
    '</script>'
)
if st.session_state.get("just_indexed"):
    st.session_state.just_indexed = False
    components.html(_SCROLL_JS, height=0, width=0)
elif st.session_state.get("scroll_to_top"):
    st.session_state.scroll_to_top = False
    components.html(_SCROLL_JS, height=0, width=0)

# ──────────────────────────────────────────────
# Main Area (Welcome hero / Chat view)
# ──────────────────────────────────────────────
if not st.session_state.index_path:
    st.markdown(
        '<div class="hero-welcome">'
        '<div class="hero-orb hero-orb-idle"><div class="hero-orb-inner"></div></div>'
        '<div class="hero-title">RepoChat</div>'
        '<div class="hero-subtitle">Ask anything about a public GitHub repository. Answers grounded in real code and documentation.</div>'
        '<div class="hero-hint">Paste a repository URL in the sidebar to begin</div>'
        '</div>',
        unsafe_allow_html=True
    )
else:
    if not st.session_state.messages:
        st.markdown('<div style="height: calc(45vh - 210px); min-height: 20px;"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="text-align: center; padding: 0 0 16px;">'
            f'<div class="hero-orb hero-orb-active"><div class="hero-orb-inner"></div></div>'
            f'<div class="hero-title">Ready to explore</div>'
            f'<div class="hero-subtitle">{st.session_state.owner}/{st.session_state.repo}</div></div>',
            unsafe_allow_html=True
        )
        suggestions = [
            ("Overview", "High-level summary of the project's purpose and goals."),
            ("How to run", "Setup instructions and how to execute the project locally."),
            ("Project structure", "Organization of files, directories, and modules."),
            ("Dependencies", "Key libraries and frameworks the project relies on."),
            ("Entry point", "The main starting point of the application."),
            ("Configuration", "How the project is configured and its settings."),
        ]
        cols = st.columns(3)
        for i, (title, desc) in enumerate(suggestions):
            with cols[i % 3]:
                if st.button(f"{title}\n\n{desc}", key=f"sug_{i}", use_container_width=True, help=desc):
                    st.session_state.messages.append({"role": "user", "content": f"{title}: {desc}", "best_effort": True})
                    st.rerun()

# ──────────────────────────────────────────────
# Chat History & Input
# ──────────────────────────────────────────────
prompt = None
if st.session_state.index_path:
    if st.session_state.messages:
        st.markdown('<div class="chat-spacer"></div>', unsafe_allow_html=True)

    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            content = re.sub(r'【([^】]+)】', r'<span class="inline-citation">\1</span>', msg["content"])
            st.markdown(content, unsafe_allow_html=True)
            if msg.get("citations") and st.session_state.get("show_sources", True):
                chips_html = "".join([f'<span class="source-chip">{path}</span>' for path in msg["citations"]])
                st.markdown(
                    f'<div style="margin-top: 14px;"><div style="font-size: 11px; font-weight: 600; color: var(--ink-tertiary); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Sources</div>{chips_html}</div>',
                    unsafe_allow_html=True
                )
            if msg["role"] == "assistant":
                st.feedback("thumbs", key=f"fb_{i}")
    prompt = st.chat_input("Ask about this repository...")

# ──────────────────────────────────────────────
# Process Query
# ──────────────────────────────────────────────
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

current_prompt = None
if len(st.session_state.messages) > 0 and st.session_state.messages[-1]["role"] == "user":
    current_prompt = st.session_state.messages[-1]["content"]

if current_prompt:
    if not st.session_state.collection or not st.session_state.files:
        st.warning("Please index a GitHub repository first.")
    elif not config.GROQ_API_KEY:
        st.error("GROQ_API_KEY is not configured. Please add it to your .env or Streamlit Cloud Secrets.")
    else:
        components.html(_SCROLL_BOTTOM_JS, height=0, width=0)
        is_best_effort = bool(st.session_state.messages and st.session_state.messages[-1].get("best_effort"))
        with st.chat_message("assistant"):
            with st.status("Searching codebase...", expanded=False) as status:
                status.update(label="Retrieving relevant code...", state="running")
                chat_history = [m for m in st.session_state.messages[:-1]]
                answer, chunks = query_repo(
                    query=current_prompt,
                    collection=st.session_state.collection,
                    chat_history=chat_history,
                    best_effort=is_best_effort,
                )
                citations = list(dict.fromkeys(c.file_path for c in chunks))
                status.update(label=f"Found {len(chunks)} relevant sections", state="complete")

            placeholder = st.empty()
            streamed = ""
            words = answer.split(" ")
            for j, word in enumerate(words):
                streamed += word + " "
                if j % 3 == 0 or j == len(words) - 1:
                    placeholder.markdown(streamed, unsafe_allow_html=True)
                    time.sleep(0.02)
            placeholder.markdown(streamed, unsafe_allow_html=True)

            if citations and st.session_state.get("show_sources", True):
                chips_html = "".join([f'<span class="source-chip">{path}</span>' for path in citations])
                st.markdown(
                    f'<div style="margin-top: 14px;"><div style="font-size: 11px; font-weight: 600; color: var(--ink-tertiary); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Sources</div>{chips_html}</div>',
                    unsafe_allow_html=True
                )

        st.session_state.messages.append({"role": "assistant", "content": answer, "citations": citations})
        st.rerun()
