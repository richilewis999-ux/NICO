import io
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import messagebox
from urllib.parse import urlparse

import customtkinter as ctk
import requests
from PIL import Image

from config import (
    DEFAULT_MODEL,
    BG,
    PANEL,
    CYAN,
    BLUE,
    WHITE,
    MUTED,
    AMBER,
    VALID_STATES,
    STATE_COLORS,
)
from database import load_memory, save_memory, search_knowledge
from ollama_client import (
    ask,
    check_connection,
    fetch_models,
    search_web,
    should_search_web,
    warm_model,
)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

MAX_IMAGE_BYTES = 2_000_000
ALLOWED_IMAGE_TYPES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
)


def time_greeting():
    hour = datetime.now().astimezone().hour

    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
    elif 17 <= hour < 22:
        greeting = "Good evening"
    else:
        greeting = "Hello"

    return f"{greeting}, sir. I'm NICO. How can I help you?"


def should_search_images(message):
    text = message.lower().strip()
    return any(
        phrase in text
        for phrase in (
            "show me",
            "find image",
            "find images",
            "find photo",
            "find photos",
            "picture",
            "pictures",
            "image",
            "images",
            "wallpaper",
        )
    )


def search_images(query, max_results=4):
    """Search images through DDGS. Results require user confirmation to open."""
    try:
        from ddgs import DDGS

        results = DDGS(timeout=8).images(
            query,
            max_results=max_results,
        )

        cleaned = []

        for result in results or []:
            if not isinstance(result, dict):
                continue

            image_url = result.get("image")
            page_url = result.get("url") or result.get("page")

            if not image_url or not page_url:
                continue

            cleaned.append({
                "title": str(result.get("title") or "Image result"),
                "image_url": str(image_url),
                "url": str(page_url),
                "source": str(result.get("source") or ""),
            })

        return cleaned[:max_results]

    except Exception:
        return []


def download_preview(url):
    """Download and validate a small HTTP(S) image preview."""
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return None
        if not parsed.netloc:
            return None

        with requests.get(
            url,
            timeout=(3, 8),
            stream=True,
            headers={"User-Agent": "NICO-Desktop/1.0"},
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()

            if not content_type.startswith(ALLOWED_IMAGE_TYPES):
                return None

            received = bytearray()

            for chunk in response.iter_content(chunk_size=16_384):
                if not chunk:
                    continue

                received.extend(chunk)

                if len(received) > MAX_IMAGE_BYTES:
                    return None

            return bytes(received) if received else None

    except requests.RequestException:
        return None
    except Exception:
        return None


class NICOApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("NICO")
        self.geometry("1180x780")
        self.minsize(850, 600)
        self.configure(fg_color=BG)

        self.events = queue.Queue()
        self.history = load_memory()
        self.model = DEFAULT_MODEL
        self.models = [DEFAULT_MODEL]

        self.busy = False
        self.camera_busy = False
        self.closing = False
        self.nico_state = "STANDBY"

        self.speech_enabled = tk.BooleanVar(
            master=self,
            value=True,
        )

        # Keep references to CTk/Pillow objects so Tkinter doesn't reclaim them.
        self._thumbnail_refs = []

        self._build_interface()
        self._render_history()
        self.protocol("WM_DELETE_WINDOW", self.close_app)

        threading.Thread(
            target=self._load_models_worker,
            daemon=True,
            name="NICOModelLoader",
        ).start()

        self.after(100, self._process_events)
        self.after(30000, self._update_system_status)
        self.input_box.focus_set()

    def _build_interface(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self,
            width=245,
            corner_radius=0,
            fg_color=PANEL,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(7, weight=1)

        ctk.CTkLabel(
            self.sidebar,
            text="NICO",
            font=ctk.CTkFont(size=25, weight="bold"),
            text_color=WHITE,
        ).grid(
            row=0,
            column=0,
            padx=22,
            pady=(25, 4),
            sticky="w",
        )

        ctk.CTkLabel(
            self.sidebar,
            text="Your local AI assistant",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        ).grid(
            row=1,
            column=0,
            padx=23,
            pady=(0, 20),
            sticky="w",
        )

        ctk.CTkButton(
            self.sidebar,
            text="+  New chat",
            height=42,
            corner_radius=10,
            fg_color=CYAN,
            hover_color=BLUE,
            text_color="#071018",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.new_chat,
        ).grid(
            row=2,
            column=0,
            padx=15,
            pady=(0, 10),
            sticky="ew",
        )

        ctk.CTkButton(
            self.sidebar,
            text="Analyze camera",
            height=36,
            fg_color="#172A39",
            hover_color="#244258",
            command=self.analyze_camera,
        ).grid(
            row=3,
            column=0,
            padx=15,
            pady=(0, 10),
            sticky="ew",
        )

        ctk.CTkLabel(
            self.sidebar,
            text="SYSTEM",
            text_color=MUTED,
            font=ctk.CTkFont(size=10, weight="bold"),
        ).grid(
            row=4,
            column=0,
            padx=20,
            pady=(10, 8),
            sticky="w",
        )

        self.system_label = ctk.CTkLabel(
            self.sidebar,
            text="Ollama: checking…",
            justify="left",
            anchor="nw",
            text_color="#B9C2CE",
            font=ctk.CTkFont(size=13),
        )
        self.system_label.grid(
            row=5,
            column=0,
            padx=20,
            sticky="nw",
        )

        bottom = ctk.CTkFrame(
            self.sidebar,
            fg_color="transparent",
        )
        bottom.grid(
            row=8,
            column=0,
            padx=15,
            pady=16,
            sticky="ew",
        )
        bottom.grid_columnconfigure(0, weight=1)

        self.model_menu = ctk.CTkOptionMenu(
            bottom,
            values=[DEFAULT_MODEL],
            command=self._change_model,
            height=35,
            fg_color="#263241",
            button_color="#34465B",
            button_hover_color="#405873",
            text_color=WHITE,
        )
        self.model_menu.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 9),
        )

        ctk.CTkButton(
            bottom,
            text="Clear conversation",
            height=34,
            fg_color="transparent",
            hover_color="#293544",
            border_width=1,
            border_color="#394657",
            text_color="#C7D0DA",
            command=self.clear_conversation,
        ).grid(
            row=1,
            column=0,
            sticky="ew",
        )

        ctk.CTkSwitch(
            bottom,
            text="Speak replies",
            variable=self.speech_enabled,
            onvalue=True,
            offvalue=False,
            text_color=WHITE,
        ).grid(
            row=2,
            column=0,
            sticky="w",
            pady=(10, 0),
        )

        self.main = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color=BG,
        )
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        topbar = ctk.CTkFrame(
            self.main,
            height=62,
            corner_radius=0,
            fg_color=BG,
        )
        topbar.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=26,
        )
        topbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            topbar,
            text="New conversation",
            text_color=WHITE,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=18,
        )

        self.status_label = ctk.CTkLabel(
            topbar,
            text="● STANDBY",
            text_color=CYAN,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.status_label.grid(
            row=0,
            column=1,
            sticky="e",
            pady=18,
        )

        self.chat_scroll = ctk.CTkScrollableFrame(
            self.main,
            fg_color=BG,
            corner_radius=0,
        )
        self.chat_scroll.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=26,
            pady=(8, 12),
        )
        self.chat_scroll.grid_columnconfigure(0, weight=1)

        composer_outer = ctk.CTkFrame(
            self.main,
            fg_color=BG,
            corner_radius=0,
        )
        composer_outer.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=26,
            pady=(0, 16),
        )
        composer_outer.grid_columnconfigure(0, weight=1)

        composer = ctk.CTkFrame(
            composer_outer,
            fg_color="#202B38",
            corner_radius=17,
            border_width=1,
            border_color="#344252",
        )
        composer.grid(row=0, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)

        self.input_box = ctk.CTkEntry(
            composer,
            placeholder_text="Message NICO…",
            height=52,
            corner_radius=14,
            border_width=0,
            fg_color="transparent",
            text_color=WHITE,
            placeholder_text_color="#8794A3",
            font=ctk.CTkFont(size=14),
        )
        self.input_box.grid(
            row=0,
            column=0,
            padx=(15, 5),
            pady=5,
            sticky="ew",
        )
        self.input_box.bind("<Return>", self._on_enter)
        self.input_box.bind(
            "<KeyPress>",
            self._on_input_activity,
            add="+",
        )

        self.send_button = ctk.CTkButton(
            composer,
            text="↑",
            width=42,
            height=42,
            corner_radius=12,
            fg_color=CYAN,
            hover_color=BLUE,
            text_color="#071018",
            font=ctk.CTkFont(size=22, weight="bold"),
            command=self.send_message,
        )
        self.send_button.grid(
            row=0,
            column=1,
            padx=7,
            pady=7,
        )

        ctk.CTkLabel(
            composer_outer,
            text=(
                "NICO runs locally using Ollama. "
                "Web and image links open only when you select them."
            ),
            text_color="#718092",
            font=ctk.CTkFont(size=10),
        ).grid(
            row=1,
            column=0,
            pady=(7, 0),
        )

    def set_state(self, state):
        if state not in VALID_STATES:
            state = "STANDBY"

        self.nico_state = state
        self.status_label.configure(
            text=f"● {state}",
            text_color=STATE_COLORS[state],
        )

    def _on_input_activity(self, _event=None):
        # Speech cancellation is handled in the camera/speech module.
        pass

    def _on_enter(self, _event):
        self.send_message()
        return "break"

    def _show_greeting(self):
        self._add_message(
            "assistant",
            time_greeting(),
        )

    def _clear_welcome(self):
        for child in self.chat_scroll.winfo_children():
            for widget in child.winfo_children():
                if isinstance(widget, ctk.CTkLabel):
                    text = widget.cget("text")
                    if "What can I help you with?" in str(text):
                        child.destroy()
                        return

    def _add_message(self, role, content):
        is_user = role == "user"

        row = ctk.CTkFrame(
            self.chat_scroll,
            fg_color="transparent",
        )
        row.grid(sticky="ew", pady=9)
        row.grid_columnconfigure(0, weight=1)

        bubble = ctk.CTkFrame(
            row,
            fg_color="#26384B" if is_user else "#1B2530",
            corner_radius=14,
            border_width=1,
            border_color="#344252" if is_user else "#283543",
        )
        bubble.grid(
            row=0,
            column=0,
            sticky="e" if is_user else "w",
            padx=(90, 0) if is_user else (0, 90),
        )

        ctk.CTkLabel(
            bubble,
            text="You" if is_user else "NICO",
            text_color="#B7C9DC" if is_user else CYAN,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(
            anchor="w",
            padx=14,
            pady=(10, 3),
        )

        ctk.CTkLabel(
            bubble,
            text=str(content),
            text_color=WHITE,
            justify="left",
            anchor="w",
            wraplength=650,
            font=ctk.CTkFont(size=14),
        ).pack(
            anchor="w",
            padx=14,
            pady=(0, 12),
        )

        self.after(40, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        try:
            canvas = self.chat_scroll._parent_canvas
            canvas.yview_moveto(1.0)
        except (AttributeError, tk.TclError):
            pass

    def _render_history(self):
        for item in self.history:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if (
                role in ("user", "assistant")
                and isinstance(content, str)
            ):
                self._add_message(role, content)

        self._show_greeting()

    def _open_link(self, url):
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            messagebox.showerror(
                "Cannot open link",
                "Only HTTP and HTTPS links can be opened.",
            )
            return

        try:
            webbrowser.open(url)
        except Exception as error:
            messagebox.showerror(
                "Could not open link",
                str(error),
            )

    def _add_search_cards(
        self,
        web_results=None,
        images=None,
    ):
        web_results = web_results or []
        images = images or []

        if not web_results and not images:
            return

        panel = ctk.CTkFrame(
            self.chat_scroll,
            fg_color="#101B27",
            corner_radius=12,
            border_width=1,
            border_color="#283543",
        )
        panel.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=8,
            padx=(0, 90),
        )
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Links and images",
            text_color=CYAN,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(
            row=0,
            column=0,
            padx=12,
            pady=(10, 5),
            sticky="w",
        )

        row = 1

        for result in web_results[:3]:
            title = str(result.get("title") or "Open result")
            url = result.get("url")
            snippet = str(result.get("snippet") or "")

            if url:
                ctk.CTkButton(
                    panel,
                    text=title,
                    anchor="w",
                    fg_color="transparent",
                    hover_color="#26384B",
                    text_color=WHITE,
                    command=lambda link=url: self._open_link(link),
                ).grid(
                    row=row,
                    column=0,
                    padx=8,
                    pady=(2, 0),
                    sticky="ew",
                )
                row += 1

            if snippet:
                ctk.CTkLabel(
                    panel,
                    text=snippet[:300],
                    text_color=MUTED,
                    justify="left",
                    anchor="w",
                    wraplength=560,
                ).grid(
                    row=row,
                    column=0,
                    padx=14,
                    pady=(0, 5),
                    sticky="w",
                )
                row += 1

        for result in images[:4]:
            preview_data = result.get("preview")

            if preview_data:
                try:
                    image = Image.open(
                        io.BytesIO(preview_data)
                    ).convert("RGB")
                    image.thumbnail((220, 150))

                    thumbnail = ctk.CTkImage(
                        light_image=image,
                        dark_image=image,
                        size=image.size,
                    )
                    self._thumbnail_refs.append(thumbnail)

                    image_label = ctk.CTkLabel(
                        panel,
                        text="",
                        image=thumbnail,
                    )
                    image_label.grid(
                        row=row,
                        column=0,
                        padx=12,
                        pady=(7, 2),
                        sticky="w",
                    )

                    page_url = result.get("url")

                    if page_url:
                        image_label.bind(
                            "<Button-1>",
                            lambda _event, link=page_url: self._open_link(link),
                        )

                    row += 1

                except Exception:
                    pass

            page_url = result.get("url")
            title = str(
                result.get("title") or "Open image source"
            )

            if page_url:
                ctk.CTkButton(
                    panel,
                    text=title,
                    anchor="w",
                    fg_color="transparent",
                    hover_color="#26384B",
                    text_color=WHITE,
                    command=lambda link=page_url: self._open_link(link),
                ).grid(
                    row=row,
                    column=0,
                    padx=8,
                    pady=(2, 5),
                    sticky="ew",
                )
                row += 1

        self.after(40, self._scroll_to_bottom)

    def send_message(self):
        if self.busy or self.camera_busy:
            return

        prompt = self.input_box.get().strip()

        if not prompt:
            return

        self.input_box.delete(0, "end")
        self._clear_welcome()
        self._add_message("user", prompt)

        self.history.append({
            "role": "user",
            "content": prompt,
        })
        save_memory(self.history)

        history_snapshot = list(self.history[:-1])
        selected_model = self.model

        self.busy = True
        self.send_button.configure(
            state="disabled",
            text="…",
        )
        self.set_state("PROCESSING")

        threading.Thread(
            target=self._ask_worker,
            args=(selected_model, history_snapshot, prompt),
            daemon=True,
            name="NICORequest",
        ).start()

    def _ask_worker(self, model, history, prompt):
        search_attempted = should_search_web(prompt)

        if search_attempted:
            web_results = search_web(
                prompt,
                max_results=3,
            )
        else:
            web_results = []

        images = []

        if should_search_images(prompt):
            for result in search_images(prompt, max_results=4):
                preview = download_preview(
                    result["image_url"]
                )
                if preview:
                    result["preview"] = preview
                images.append(result)

        try:
            knowledge = search_knowledge(prompt)
        except Exception:
            knowledge = []

        try:
            answer, connection_ok = ask(
                model,
                history,
                prompt,
                knowledge_results=knowledge,
                web_results=web_results,
                web_search_attempted=search_attempted,
            )

            self.events.put((
                "answer",
                answer,
                connection_ok,
                web_results,
                images,
            ))

        except Exception as error:
            self.events.put((
                "answer",
                f"Sorry, I ran into a problem: {error}",
                False,
                [],
                [],
            ))

    def analyze_camera(self):
        if self.busy or self.camera_busy:
            return

        confirmed = messagebox.askyesno(
            "Camera permission",
            "NICO will capture one image from your camera and send it to "
            "your local Ollama vision model for analysis. The image is not "
            "saved. Continue?",
        )

        if not confirmed:
            return

        self.camera_busy = True
        self.set_state("PROCESSING")

        threading.Thread(
            target=self._camera_worker,
            daemon=True,
            name="NICOCamera",
        ).start()

    def _camera_worker(self):
        try:
            from camera_client import analyze_camera
            result = analyze_camera()
        except Exception as error:
            result = f"Camera analysis failed:\n{error}"

        self.events.put((
            "camera_result",
            result,
        ))

    def _load_models_worker(self):
        try:
            models = fetch_models()
            connected = check_connection()
        except Exception:
            models = [DEFAULT_MODEL]
            connected = False

        if connected:
            selected_model = (
                self.model
                if self.model in models
                else models[0]
            )

            threading.Thread(
                target=warm_model,
                args=(selected_model,),
                daemon=True,
                name="NICOModelWarmup",
            ).start()

        self.events.put((
            "models",
            models,
            connected,
        ))

    def _check_connection_worker(self):
        try:
            connected = check_connection()
        except Exception:
            connected = False

        self.events.put((
            "connection",
            connected,
        ))

    def _process_events(self):
        if self.closing:
            return

        try:
            while True:
                event = self.events.get_nowait()

                if event[0] == "answer":
                    _, answer, connection_ok, web_results, images = event

                    self._add_message(
                        "assistant",
                        answer,
                    )

                    self._add_search_cards(
                        web_results,
                        images,
                    )

                    self.history.append({
                        "role": "assistant",
                        "content": answer,
                    })
                    save_memory(self.history)

                    self.busy = False
                    self.send_button.configure(
                        state="normal",
                        text="↑",
                    )
                    self.set_state(
                        "RESPONDING"
                        if connection_ok
                        else "SYSTEM ERROR"
                    )

                    self.input_box.focus_set()
                    self.after(
                        1200,
                        self._return_to_standby,
                    )

                elif event[0] == "camera_result":
                    answer = event[1]
                    self.camera_busy = False

                    self._clear_welcome()
                    self._add_message(
                        "assistant",
                        answer,
                    )

                    self.history.append({
                        "role": "assistant",
                        "content": answer,
                    })
                    save_memory(self.history)

                    self.set_state("RESPONDING")

                    self.after(
                        1200,
                        self._return_to_standby,
                    )

                elif event[0] == "models":
                    _, models, connected = event
                    self.models = models or [DEFAULT_MODEL]

                    if self.model not in self.models:
                        self.model = self.models[0]

                    self.model_menu.configure(
                        values=self.models
                    )
                    self.model_menu.set(
                        self.model
                    )
                    self._show_connection_status(
                        connected
                    )

                elif event[0] == "connection":
                    self._show_connection_status(
                        event[1]
                    )

        except queue.Empty:
            pass

        self.after(100, self._process_events)

    def _show_connection_status(self, connected):
        if connected:
            self.system_label.configure(
                text=f"Ollama: connected\nModel: {self.model}"
            )

            if not self.busy and not self.camera_busy:
                self.set_state("STANDBY")
        else:
            self.system_label.configure(
                text=(
                    "Ollama: not connected\n"
                    "Run `ollama serve`"
                )
            )

            if not self.busy and not self.camera_busy:
                self.set_state("SYSTEM ERROR")

    def _return_to_standby(self):
        if (
            not self.closing
            and not self.busy
            and not self.camera_busy
        ):
            self.set_state("STANDBY")

    def _change_model(self, selected):
        self.model = selected
        self.system_label.configure(
            text=f"Selected model: {selected}"
        )

        threading.Thread(
            target=warm_model,
            args=(selected,),
            daemon=True,
            name="NICOModelWarmup",
        ).start()

    def new_chat(self):
        if self.busy or self.camera_busy:
            return

        self.history = []
        save_memory(self.history)

        for child in self.chat_scroll.winfo_children():
            child.destroy()

        self._show_greeting()
        self.set_state("STANDBY")

    def clear_conversation(self):
        if messagebox.askyesno(
            "Clear conversation",
            "Delete the saved conversation history?",
        ):
            self.new_chat()

    def _update_system_status(self):
        if self.closing:
            return

        threading.Thread(
            target=self._check_connection_worker,
            daemon=True,
            name="NICOConnectionCheck",
        ).start()

        self.after(
            30000,
            self._update_system_status,
        )

    def close_app(self):
        self.closing = True
        save_memory(self.history)
        self.destroy()


if __name__ == "__main__":
    app = NICOApp()
    app.mainloop()