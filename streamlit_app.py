from __future__ import annotations

from uuid import uuid4

import httpx
import streamlit as st


DEFAULT_API_URL = "http://127.0.0.1:8000/api/v1/chat"


def initialize_state() -> None:
    st.session_state.setdefault("api_url", DEFAULT_API_URL)
    st.session_state.setdefault("jwt", "")
    st.session_state.setdefault("conversation_id", f"streamlit-{uuid4().hex[:12]}")
    st.session_state.setdefault("setup_complete", False)
    st.session_state.setdefault("messages", [])


def reset_setup() -> None:
    st.session_state.setup_complete = False
    st.session_state.messages = []


def call_chat_api(message: str) -> str:
    payload = {
        "JWT": st.session_state.jwt,
        "conversation_id": st.session_state.conversation_id,
        "message": message,
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(st.session_state.api_url, json=payload)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise RuntimeError("Could not connect to the FastAPI server. Start it before chatting.") from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise RuntimeError(f"API returned {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"API request failed: {exc}") from exc

    data = response.json()
    answer = data.get("answer")
    if not isinstance(answer, str):
        raise RuntimeError("API response did not include a valid 'answer' field.")
    return answer


def render_setup() -> None:
    st.title("Farm Assistant Chat")
    st.caption("Mock UI for testing the chatbot model through the local FastAPI backend.")

    with st.form("chat_setup"):
        api_url = st.text_input("API URL", value=st.session_state.api_url)
        jwt = st.text_input("JWT", value=st.session_state.jwt, type="password")
        conversation_id = st.text_input("Conversation ID", value=st.session_state.conversation_id)
        submitted = st.form_submit_button("Start chat")

    if not submitted:
        return

    if not jwt.strip():
        st.error("JWT is required because the backend passes it to farm data tools.")
        return

    if not conversation_id.strip():
        st.error("Conversation ID is required for backend memory.")
        return

    st.session_state.api_url = api_url.strip() or DEFAULT_API_URL
    st.session_state.jwt = jwt.strip()
    st.session_state.conversation_id = conversation_id.strip()
    st.session_state.setup_complete = True
    st.rerun()


def render_chat() -> None:
    with st.sidebar:
        st.subheader("Chat setup")
        st.text_input("API URL", value=st.session_state.api_url, disabled=True)
        st.text_input("Conversation ID", value=st.session_state.conversation_id, disabled=True)
        if st.button("Reset chat setup"):
            reset_setup()
            st.rerun()

    st.title("Farm Assistant Chat")
    st.caption("Ask farming questions in Arabic or English. Farm readings come from backend tools when requested.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Type your message...")
    if prompt is None:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                answer = call_chat_api(prompt)
            except RuntimeError as exc:
                answer = f"Error: {exc}"
                st.error(answer)
            else:
                st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})


def main() -> None:
    st.set_page_config(page_title="Farm Assistant Chat")
    initialize_state()

    if st.session_state.setup_complete:
        render_chat()
    else:
        render_setup()


if __name__ == "__main__":
    main()
