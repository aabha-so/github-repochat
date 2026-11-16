"""RepoChat Streamlit User Interface.

Provides a clean chat interface for public GitHub repository Q&A.
Maintains repo URL, chat history, and index path in st.session_state across reruns.
"""

import re
import time

import streamlit as st

# Page configuration MUST be the very first Streamlit command executed
st.set_page_config(
    page_title="RepoChat",
    page_icon=":material/code:",
    layout="wide",
)

# Load Custom CSS
with open("assets/style.css", encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

from pathlib import Path
import config  # Ensures telemetry mutes and global settings load first
from indexer import index_repository
from loader import RepoTooLargeError, load_repository
from retriever import query_repo


def init_session_state() -> None:
    """Initialize persistent session variables if not already present."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "repo_url" not in st.session_state:
        st.session_state.repo_url = ""
    if "index_path" not in st.session_state:
        st.session_state.index_path = None
    if "owner" not in st.session_state:
        st.session_state.owner = ""
    if "repo" not in st.session_state:
        st.session_state.repo = ""
    if "commit_sha" not in st.session_state:
        st.session_state.commit_sha = ""
    if "files" not in st.session_state:
        st.session_state.files = []
    if "collection" not in st.session_state:
        st.session_state.collection = None


init_session_state()

# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    # Brand
    st.markdown(
        '''
        <div style="
            padding: 14px 0 28px;
            text-align: center;
        ">
            <div style="
                font-weight: 800;
                font-size: 20px;
                letter-spacing: -0.04em;
                color: var(--ink);
            ">RepoChat</div>
            <div style="
                font-size: 12px;
                color: var(--ink-tertiary);
                margin-top: 4px;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            ">Codebase Intelligence</div>
        </div>
        ''',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div style="font-size: 11px; font-weight: 700; color: var(--ink-tertiary); letter-spacing: 0.1em; margin-bottom: 8px; text-transform: uppercase;">Repository</div>',
        unsafe_allow_html=True
    )

    repo_input = st.text_input(
        "GitHub Repository URL",
        value=st.session_state.repo_url,
        placeholder="https://github.com/psf/requests",
        help="Paste a public GitHub repo URL.",
        label_visibility="collapsed",
        key="repo_url_input"
    )
    # Synchronize widget value back to session state
    if "repo_url_input" in st.session_state:
        # Auto-trigger indexing if the URL changed and we aren't already indexed to this specific repo
        new_url = st.session_state.repo_url_input.strip()
        if new_url and new_url != st.session_state.repo_url:
            st.session_state.repo_url = new_url
            # We trigger the indexing logic in the main block below by clearing the index_path
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

                    # Update persistent session state
                    st.session_state.repo_url = repo_input.strip()
                    st.session_state.owner = owner
                    st.session_state.repo = repo
                    st.session_state.commit_sha = commit_sha
                    st.session_state.files = files
                    st.session_state.collection = collection
                    st.session_state.index_path = index_path
                    st.session_state.messages = []  # Reset chat on new repo

                    # Verify that the index actually contains data
                    if collection.count() == 0:
                        status.update(label="No valid text chunks found.", state="error")
                        st.session_state.collection = None
                    else:
                        label = "Reusing cached index" if is_cached else "Indexed successfully"
                        status.update(label=f"{label} — {len(files)} files", state="complete")
                except RepoTooLargeError as exc:
                    status.update(label=f"Repository too large: {exc}", state="error")
                except Exception as exc:
                    status.update(label=f"Failed: {exc}", state="error")

    if st.session_state.index_path:
        st.markdown(
            '<div style="margin: 24px 0 16px; border-bottom: 1px solid var(--surface-border);"></div>',
            unsafe_allow_html=True
        )

        # Status Cards
        def render_status_card(label, value):
            return f'''
            <div class="glass-card" style="margin-bottom: 10px; padding: 12px 16px;">
                <div style="font-size: 10px; font-weight: 700; color: var(--ink-tertiary); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px;">{label}</div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--ink);">{value}</div>
            </div>
            '''

        st.markdown(render_status_card("Repository", f"{st.session_state.owner}/{st.session_state.repo}"), unsafe_allow_html=True)
        st.markdown(render_status_card("Files", str(len(st.session_state.files))), unsafe_allow_html=True)
        st.markdown(render_status_card("Commit", st.session_state.commit_sha[:7]), unsafe_allow_html=True)

        st.markdown(
            '<div style="margin: 16px 0 8px; border-bottom: 1px solid var(--surface-border);"></div>',
            unsafe_allow_html=True
        )

        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


# ──────────────────────────────────────────────
# Main Area
# ──────────────────────────────────────────────
# State 1: No repository indexed — Welcome hero
if not st.session_state.index_path:
    st.markdown(
        '''
        <div style="text-align: center; padding: 80px 0 60px;">
            <div class="hero-orb hero-orb-idle">
                <div class="hero-orb-inner"></div>
            </div>
            <div class="hero-title">RepoChat</div>
            <div class="hero-subtitle">
                Ask anything about a public GitHub repository.
                Answers grounded in real code and documentation.
            </div>
            <div class="hero-hint">
                Paste a repository URL in the sidebar to begin
            </div>
        </div>
        ''',
        unsafe_allow_html=True
    )
else:
    # State 2: Repository indexed, no messages — Ready hero + suggestions
    if not st.session_state.messages:
        st.markdown(
            f'''
            <div style="text-align: center; padding: 60px 0 32px;">
                <div class="hero-orb hero-orb-active">
                    <div class="hero-orb-inner"></div>
                </div>
                <div class="hero-title">Ready to explore</div>
                <div class="hero-subtitle">
                    {st.session_state.owner}/{st.session_state.repo}
                </div>
            </div>
            ''',
            unsafe_allow_html=True
        )

    # Suggestion Tiles — only show when no messages
    if not st.session_state.messages:
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
                if st.button(
                    f"{title}\n\n{desc}",
                    key=f"sug_{i}",
                    use_container_width=True,
                    help=desc
                ):
                    st.session_state.messages.append({
                        "role": "user",
                        "content": f"{title}: {desc}",
                        "best_effort": True
                    })
                    st.rerun()

# ──────────────────────────────────────────────
# Chat History
# ──────────────────────────────────────────────
prompt = None
if st.session_state.index_path:
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            # Process content to replace 【filename】 with inline chips
            content = msg["content"]
            content = re.sub(r'【([^】]+)】', r'<span class="inline-citation">\1</span>', content)
            st.markdown(content, unsafe_allow_html=True)

            if msg.get("citations"):
                chips_html = "".join(
                    [f'<span class="source-chip">{path}</span>' for path in msg["citations"]]
                )
                st.markdown(
                    f'<div style="margin-top: 14px;">'
                    f'<div style="font-size: 11px; font-weight: 600; color: var(--ink-tertiary); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Sources</div>'
                    f'{chips_html}</div>',
                    unsafe_allow_html=True
                )

            # Feedback on assistant messages
            if msg["role"] == "assistant":
                st.feedback("thumbs", key=f"fb_{i}")

    # Handle user input
    prompt = st.chat_input("Ask about this repository...")

# ──────────────────────────────────────────────
# Process Query
# ──────────────────────────────────────────────
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    current_prompt = prompt
elif len(st.session_state.messages) > 0 and st.session_state.messages[-1]["role"] == "user":
    current_prompt = st.session_state.messages[-1]["content"]
else:
    current_prompt = None

if current_prompt:
    if not st.session_state.collection or not st.session_state.files:
        st.warning("Please index a GitHub repository first.")
    else:
        # Determine if this is a "best effort" query (from a suggestion button)
        is_best_effort = False
        if len(st.session_state.messages) > 0:
            last_msg = st.session_state.messages[-1]
            if last_msg.get("best_effort"):
                is_best_effort = True

        with st.chat_message("assistant"):
            with st.status("Searching codebase...", expanded=False) as status:
                status.update(label="Retrieving relevant code...", state="running")

                # Filter history to exclude the current prompt
                chat_history = [m for m in st.session_state.messages if m["content"] != current_prompt]

                answer, chunks = query_repo(
                    query=current_prompt,
                    collection=st.session_state.collection,
                    chat_history=chat_history,
                    best_effort=is_best_effort
                )
                citations = list(dict.fromkeys(c.file_path for c in chunks))

                status.update(
                    label=f"Found {len(chunks)} relevant sections",
                    state="complete"
                )

            # Stream the response
            placeholder = st.empty()
            streamed = ""
            words = answer.split(" ")
            for j, word in enumerate(words):
                streamed += word + " "
                # Update every few words for smooth feel without being too slow
                if j % 3 == 0 or j == len(words) - 1:
                    placeholder.markdown(streamed, unsafe_allow_html=True)
                    time.sleep(0.02)
            placeholder.markdown(streamed, unsafe_allow_html=True)

            if citations:
                chips_html = "".join(
                    [f'<span class="source-chip">{path}</span>' for path in citations]
                )
                st.markdown(
                    f'<div style="margin-top: 14px;">'
                    f'<div style="font-size: 11px; font-weight: 600; color: var(--ink-tertiary); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Sources</div>'
                    f'{chips_html}</div>',
                    unsafe_allow_html=True
                )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer,
                "citations": citations,
            }
        )
        st.rerun()