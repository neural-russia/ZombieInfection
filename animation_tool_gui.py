import os
import threading
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from from_json_to_frame import (
    FrameData,
    assemble_frames,
    export_gif,
    load_transform_overrides,
    save_trimmed_frames,
)
from from_json_to_spritesheet import CELL_PADDING, build_spritesheet


class AnimationToolApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Zombie Infection Capture Tool")
        self.root.geometry("1100x700")

        self.capture_path_var = tk.StringVar()
        self.sprites_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.overrides_path_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Выберите capture JSON и директории")
        self.output_frames_var = tk.StringVar(value="—")
        self.output_gif_var = tk.StringVar(value="—")
        self.output_sheet_var = tk.StringVar(value="—")

        self.preview_frames: List[ImageTk.PhotoImage] = []
        self.preview_durations: List[int] = []
        self.frame_data: List[FrameData] = []
        self.preview_job: Optional[str] = None
        self.current_preview_index = 0
        self.processing = False

        self._build_ui()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=16)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(2, weight=0)

        inputs = ttk.LabelFrame(main, text="Исходные данные")
        inputs.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        inputs.columnconfigure(1, weight=1)

        self._add_path_row(
            inputs,
            row=0,
            label="capture JSON:",
            variable=self.capture_path_var,
            command=self._browse_capture,
        )
        self._add_path_row(
            inputs,
            row=1,
            label="Папка со спрайтами:",
            variable=self.sprites_dir_var,
            command=self._browse_sprites,
            is_directory=True,
        )
        self._add_path_row(
            inputs,
            row=2,
            label="Папка для вывода:",
            variable=self.output_dir_var,
            command=self._browse_output,
            is_directory=True,
        )
        self._add_path_row(
            inputs,
            row=3,
            label="TRANSFORM_OVERRIDES:",
            variable=self.overrides_path_var,
            command=self._browse_overrides,
        )

        buttons_frame = ttk.Frame(inputs)
        buttons_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        buttons_frame.columnconfigure(0, weight=1)

        self.run_button = ttk.Button(
            buttons_frame,
            text="Запустить обработку",
            command=self._start_processing,
        )
        self.run_button.grid(row=0, column=0, sticky="ew")

        status_label = ttk.Label(buttons_frame, textvariable=self.status_var)
        status_label.grid(row=1, column=0, sticky="w", pady=(8, 0))

        preview_area = ttk.Frame(main)
        preview_area.grid(row=1, column=0, sticky="nsew")
        preview_area.columnconfigure(0, weight=1)
        preview_area.columnconfigure(1, weight=1)
        preview_area.rowconfigure(0, weight=1)

        preview_frame = ttk.LabelFrame(preview_area, text="Предпросмотр GIF")
        preview_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self.preview_label = ttk.Label(
            preview_frame,
            text="Предпросмотр появится после сборки",
            anchor="center",
            relief="sunken",
            padding=8,
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        frames_frame = ttk.LabelFrame(preview_area, text="Кадры")
        frames_frame.grid(row=0, column=1, sticky="nsew")
        frames_frame.columnconfigure(0, weight=0)
        frames_frame.columnconfigure(1, weight=1)
        frames_frame.rowconfigure(0, weight=1)

        list_container = ttk.Frame(frames_frame)
        list_container.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        list_container.rowconfigure(0, weight=1)

        self.frames_listbox = tk.Listbox(
            list_container,
            exportselection=False,
            width=28,
        )
        self.frames_listbox.grid(row=0, column=0, sticky="ns")
        self.frames_listbox.bind("<<ListboxSelect>>", self._on_frame_selected)

        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.frames_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.frames_listbox.configure(yscrollcommand=scrollbar.set)

        preview_container = ttk.Frame(frames_frame)
        preview_container.grid(row=0, column=1, sticky="nsew")
        preview_container.columnconfigure(0, weight=1)
        preview_container.rowconfigure(1, weight=1)

        self.frame_name_var = tk.StringVar(value="—")
        frame_name_label = ttk.Label(preview_container, textvariable=self.frame_name_var, anchor="center")
        frame_name_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.frame_preview_label = ttk.Label(
            preview_container,
            text="Выберите кадр",
            anchor="center",
            relief="sunken",
            padding=8,
        )
        self.frame_preview_label.grid(row=1, column=0, sticky="nsew")

        results_frame = ttk.LabelFrame(main, text="Результаты")
        results_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        for col in range(2):
            results_frame.columnconfigure(col, weight=1)

        ttk.Label(results_frame, text="Кадры:").grid(row=0, column=0, sticky="w")
        ttk.Label(results_frame, textvariable=self.output_frames_var).grid(row=0, column=1, sticky="w")

        ttk.Label(results_frame, text="GIF:").grid(row=1, column=0, sticky="w")
        ttk.Label(results_frame, textvariable=self.output_gif_var).grid(row=1, column=1, sticky="w")

        ttk.Label(results_frame, text="Spritesheet:").grid(row=2, column=0, sticky="w")
        ttk.Label(results_frame, textvariable=self.output_sheet_var).grid(row=2, column=1, sticky="w")

    def _add_path_row(
        self,
        parent: ttk.LabelFrame,
        *,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
        is_directory: bool = False,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        button = ttk.Button(
            parent,
            text="Выбрать…" if is_directory else "Обзор…",
            command=command,
            width=14,
        )
        button.grid(row=row, column=2, sticky="ew", pady=4, padx=(8, 0))

    # -------------------------------------------------------------- Browsers --
    def _browse_capture(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите capture JSON",
            filetypes=(("JSON", "*.json"), ("Все файлы", "*")),
        )
        if path:
            self.capture_path_var.set(path)
            parent_dir = str(Path(path).parent)
            if not self.output_dir_var.get():
                self.output_dir_var.set(parent_dir)
            if not self.sprites_dir_var.get():
                self.sprites_dir_var.set(os.path.join(parent_dir, "sprites"))

    def _browse_sprites(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку со спрайтами")
        if path:
            self.sprites_dir_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку для сохранения результатов")
        if path:
            self.output_dir_var.set(path)

    def _browse_overrides(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл TRANSFORM_OVERRIDES",
            filetypes=(("JSON", "*.json"), ("Все файлы", "*")),
        )
        if path:
            self.overrides_path_var.set(path)

    # ---------------------------------------------------------- Processing --
    def _start_processing(self) -> None:
        if self.processing:
            return

        json_path = Path(self.capture_path_var.get()).expanduser()
        sprites_dir = Path(self.sprites_dir_var.get()).expanduser()
        output_dir = Path(self.output_dir_var.get()).expanduser()
        overrides_path = Path(self.overrides_path_var.get()).expanduser() if self.overrides_path_var.get() else None

        if not json_path.is_file():
            messagebox.showerror("Ошибка", "Укажите существующий файл capture JSON")
            return
        if not sprites_dir.is_dir():
            messagebox.showerror("Ошибка", "Укажите существующую папку со спрайтами")
            return
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Ошибка", f"Не удалось создать папку вывода: {exc}")
                return

        self.processing = True
        self.run_button.state(["disabled"])
        self.status_var.set("Обработка запущена…")
        self._stop_preview()
        self.preview_label.configure(text="Обработка…", image="")
        self.preview_label.image = None
        self.frame_preview_label.configure(text="Обработка…", image="")
        self.frame_preview_label.image = None
        self.frame_name_var.set("—")
        self.frames_listbox.delete(0, tk.END)

        thread = threading.Thread(
            target=self._process_worker,
            args=(json_path, sprites_dir, output_dir, overrides_path),
            daemon=True,
        )
        thread.start()

    def _process_worker(
        self,
        json_path: Path,
        sprites_dir: Path,
        output_dir: Path,
        overrides_path: Optional[Path],
    ) -> None:
        try:
            overrides = load_transform_overrides(str(overrides_path)) if overrides_path else None
        except Exception as exc:
            self._post_failure(f"Не удалось загрузить TRANSFORM_OVERRIDES: {exc}")
            return

        def progress(done: int, total: int, key: str) -> None:
            def update() -> None:
                if total == 0:
                    self.status_var.set("Чтение данных…")
                    return
                if key:
                    self.status_var.set(f"Собрано {done}/{total}: {key}")
                else:
                    self.status_var.set("Сборка завершена")

            self.root.after(0, update)

        try:
            frames = assemble_frames(
                str(json_path),
                str(sprites_dir),
                transform_overrides=overrides,
                progress=progress,
            )

            frames_dir = output_dir / "frames"
            save_trimmed_frames(frames, str(frames_dir))

            gif_path = output_dir / f"{json_path.stem}.gif"
            sheet_path = output_dir / f"{json_path.stem}_spritesheet.png"

            if frames:
                export_gif(
                    [frame.image for frame in frames],
                    [frame.duration_ms for frame in frames],
                    str(gif_path),
                )
                build_spritesheet(frames, str(sheet_path), cell_padding=CELL_PADDING)

        except Exception as exc:
            self._post_failure(f"Ошибка при обработке: {exc}")
            return

        self.root.after(
            0,
            lambda: self._processing_complete(
                frames,
                frames_dir,
                gif_path,
                sheet_path,
            ),
        )

    def _post_failure(self, message: str) -> None:
        def handler() -> None:
            self.processing = False
            self.run_button.state(["!disabled"])
            self.status_var.set(message)
            messagebox.showerror("Ошибка", message)

        self.root.after(0, handler)

    def _processing_complete(
        self,
        frames: List[FrameData],
        frames_dir: Path,
        gif_path: Path,
        sheet_path: Path,
    ) -> None:
        self.processing = False
        self.run_button.state(["!disabled"])

        self.frame_data = frames
        self.preview_frames = [ImageTk.PhotoImage(frame.trimmed) for frame in frames]
        self.preview_durations = [max(20, frame.duration_ms) for frame in frames]

        self.frames_listbox.delete(0, tk.END)
        for index, frame in enumerate(frames, start=1):
            self.frames_listbox.insert(tk.END, f"{index:03d}. {frame.key}")

        if frames:
            self.frames_listbox.selection_clear(0, tk.END)
            self.frames_listbox.selection_set(0)
            self.frames_listbox.event_generate("<<ListboxSelect>>")
            self._start_preview()
            self.status_var.set(f"Готово! Собрано кадров: {len(frames)}")
        else:
            self._stop_preview()
            self.preview_label.configure(text="Нет кадров для предпросмотра", image="")
            self.preview_label.image = None
            self.frame_preview_label.configure(text="Нет кадров", image="")
            self.frame_preview_label.image = None
            self.frame_name_var.set("—")
            self.status_var.set("В файле нет кадров")

        self.output_frames_var.set(str(frames_dir))
        self.output_gif_var.set(str(gif_path))
        self.output_sheet_var.set(str(sheet_path))

    # ----------------------------------------------------------- Previewing --
    def _start_preview(self) -> None:
        self._stop_preview()
        if not self.preview_frames:
            self.preview_label.configure(text="Нет предпросмотра", image="")
            self.preview_label.image = None
            return
        self.current_preview_index = 0
        self._schedule_next_frame()

    def _stop_preview(self) -> None:
        if self.preview_job is not None:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None

    def _schedule_next_frame(self) -> None:
        if not self.preview_frames:
            return

        frame_img = self.preview_frames[self.current_preview_index]
        self.preview_label.configure(image=frame_img, text="")
        self.preview_label.image = frame_img

        duration = self.preview_durations[self.current_preview_index]
        self.current_preview_index = (self.current_preview_index + 1) % len(self.preview_frames)
        self.preview_job = self.root.after(duration, self._schedule_next_frame)

    def _on_frame_selected(self, _event: tk.Event) -> None:
        if not self.preview_frames:
            return
        selection = self.frames_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.preview_frames):
            return

        frame = self.frame_data[index]
        frame_img = self.preview_frames[index]
        self.frame_preview_label.configure(image=frame_img, text="")
        self.frame_preview_label.image = frame_img
        self.frame_name_var.set(frame.key)

    # ----------------------------------------------------------------- Main --
    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = AnimationToolApp()
    app.run()


if __name__ == "__main__":
    main()
