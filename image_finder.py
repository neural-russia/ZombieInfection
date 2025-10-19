import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, colorchooser, messagebox
from PIL import Image, ImageTk
import os
import re
import sys
import subprocess

# --- Новые импорты для расширенного взаимодействия с Windows ---
# Если этих библиотек нет, будет использован старый метод
try:
    import win32gui
    import win32com.client
    from urllib.parse import unquote

    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

# Константы
THUMBNAIL_SIZE = (150, 150)
BG_COLOR = "#f0f0f0"
FONT_TUPLE = ("Helvetica", 10)
DIM_FONT_TUPLE = ("Helvetica", 8)


class ProductionImageFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Профессиональный поиск изображений по цвету")
        self.root.geometry("950x650")
        self.root.configure(bg=BG_COLOR)

        self.folder_path = ""
        self.photo_references = []
        self.found_data = []
        self._is_updating_color1 = False
        self._is_updating_color2 = False

        # --- Фреймы интерфейса ---
        control_frame = tk.Frame(root, bg=BG_COLOR, padx=10, pady=10)
        control_frame.pack(side=tk.TOP, fill=tk.X)
        results_outer_frame = tk.Frame(root, bg="gray")
        results_outer_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        # --- Элементы управления ---
        tk.Label(control_frame, text="Папка для поиска:", bg=BG_COLOR, font=FONT_TUPLE).grid(row=0, column=0, padx=5,
                                                                                             pady=5, sticky="w")
        self.folder_btn = tk.Button(control_frame, text="Выбрать...", command=self.select_folder)
        self.folder_btn.grid(row=0, column=1, columnspan=2, padx=5, pady=5)
        self.folder_label = tk.Label(control_frame, text="Папка не выбрана", bg=BG_COLOR, font=FONT_TUPLE, width=40,
                                     anchor="w")
        self.folder_label.grid(row=0, column=3, columnspan=2, padx=5, pady=5, sticky="w")

        self.color1_var = tk.StringVar(value='FF0000')
        tk.Label(control_frame, text="Основной цвет:", bg=BG_COLOR, font=FONT_TUPLE).grid(row=1, column=0, padx=5,
                                                                                          pady=5, sticky="w")
        self.color1_btn = tk.Button(control_frame, text="Палитра", command=lambda: self.select_color(self.color1_var))
        self.color1_btn.grid(row=1, column=1, padx=5, pady=5)
        self.color1_preview = tk.Label(control_frame, text="      ", bg=f"#{self.color1_var.get()}", relief="sunken")
        self.color1_preview.grid(row=1, column=2, padx=5, pady=5)
        tk.Label(control_frame, text="#", bg=BG_COLOR, font=(FONT_TUPLE[0], 12, "bold")).grid(row=1, column=3,
                                                                                              sticky="e")
        self.color1_entry = tk.Entry(control_frame, textvariable=self.color1_var, width=8, font=FONT_TUPLE)
        self.color1_entry.grid(row=1, column=4, padx=(0, 5), pady=5, sticky="w")
        self.color1_var.trace_add("write", lambda *args: self._format_and_update(self.color1_var, self.color1_preview,
                                                                                 "_is_updating_color1"))

        self.color2_var = tk.StringVar(value='')
        tk.Label(control_frame, text="Дополнительный цвет:", bg=BG_COLOR, font=FONT_TUPLE).grid(row=2, column=0, padx=5,
                                                                                                pady=5, sticky="w")
        self.color2_btn = tk.Button(control_frame, text="Палитра", command=lambda: self.select_color(self.color2_var))
        self.color2_btn.grid(row=2, column=1, padx=5, pady=5)
        self.color2_preview = tk.Label(control_frame, text="      ", bg=BG_COLOR, relief="sunken")
        self.color2_preview.grid(row=2, column=2, padx=5, pady=5)
        tk.Label(control_frame, text="#", bg=BG_COLOR, font=(FONT_TUPLE[0], 12, "bold")).grid(row=2, column=3,
                                                                                              sticky="e")
        self.color2_entry = tk.Entry(control_frame, textvariable=self.color2_var, width=8, font=FONT_TUPLE)
        self.color2_entry.grid(row=2, column=4, padx=(0, 5), pady=5, sticky="w")
        self.color2_var.trace_add("write", lambda *args: self._format_and_update(self.color2_var, self.color2_preview,
                                                                                 "_is_updating_color2"))

        tk.Label(control_frame, text="Сортировка:", bg=BG_COLOR, font=FONT_TUPLE).grid(row=0, column=5, padx=(20, 5),
                                                                                       pady=5, sticky="w")
        self.sort_var = tk.StringVar()
        sort_options = ["По алфавиту (А-Я)", "По размеру (сначала большие)", "По размеру (сначала маленькие)"]
        self.sort_combobox = ttk.Combobox(control_frame, textvariable=self.sort_var, values=sort_options,
                                          state="readonly", width=30)
        self.sort_combobox.grid(row=1, column=5, padx=(20, 5), pady=5)
        self.sort_combobox.set(sort_options[0])
        self.sort_combobox.bind("<<ComboboxSelected>>", self.on_sort_change)

        self.search_btn = tk.Button(control_frame, text="Начать поиск", font=("Helvetica", 10, "bold"),
                                    command=self.start_search)
        self.search_btn.grid(row=0, column=6, rowspan=3, padx=20, pady=5, ipady=15, sticky="ns")

        self.canvas = tk.Canvas(results_outer_frame, bg=BG_COLOR)
        scrollbar = tk.Scrollbar(results_outer_frame, orient="vertical", command=self.canvas.yview)
        self.results_frame = tk.Frame(self.canvas, bg=BG_COLOR)
        self.results_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.results_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Configure>", self.redraw_results_grid)

    @staticmethod
    def hex_to_rgb(hex_code):
        hex_code = hex_code.lstrip('#')
        return tuple(int(hex_code[i:i + 2], 16) for i in (0, 2, 4))

    def natural_sort_key(self, s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _format_and_update(self, var, preview, flag_name):
        if getattr(self, flag_name): return
        setattr(self, flag_name, True)
        current_value = var.get()
        sanitized = re.sub(r'[^0-9a-fA-F]', '', current_value).upper()[:6]
        if current_value != sanitized: var.set(sanitized)
        if len(sanitized) == 6:
            preview.config(bg=f"#{sanitized}")
        else:
            preview.config(bg=BG_COLOR)
        setattr(self, flag_name, False)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path: self.folder_path = path; self.folder_label.config(text=self.folder_path)

    def select_color(self, var):
        initial_color = f"#{var.get()}" if var.get() else "#FFFFFF"
        color_code = colorchooser.askcolor(title="Выберите цвет", initialcolor=initial_color)
        if color_code and color_code[1]: var.set(color_code[1].lstrip('#').upper())

    def on_sort_change(self, event=None):
        if not self.found_data: return
        sort_option = self.sort_var.get()
        if "По размеру (сначала большие)" in sort_option:
            self.found_data.sort(key=lambda item: item[1], reverse=True)
        elif "По размеру (сначала маленькие)" in sort_option:
            self.found_data.sort(key=lambda item: item[1], reverse=False)
        else:
            self.found_data.sort(key=lambda item: self.natural_sort_key(os.path.basename(item[0])))
        self.redraw_results_grid()

    def start_search(self):
        if not self.folder_path: messagebox.showerror("Ошибка", "Пожалуйста, выберите папку для поиска."); return
        hex_code1 = self.color1_var.get()
        if len(hex_code1) != 6: messagebox.showerror("Ошибка",
                                                     f"Неверный формат основного цвета: '{hex_code1}'."); return
        rgb1 = self.hex_to_rgb(hex_code1)
        rgb2 = None
        hex_code2 = self.color2_var.get().strip()
        if hex_code2:
            if len(hex_code2) != 6: messagebox.showerror("Ошибка",
                                                         f"Неверный формат дополнительного цвета: '{hex_code2}'."); return
            rgb2 = self.hex_to_rgb(hex_code2)

        self.clear_results()
        status_label = tk.Label(self.results_frame, text="Идет поиск...", font=("Helvetica", 14), bg=BG_COLOR)
        status_label.pack(pady=20)
        self.root.update_idletasks()

        self.found_data = self.find_images_with_colors(rgb1, rgb2)

        status_label.destroy()
        if not self.found_data: messagebox.showinfo("Результат", "Подходящие изображения не найдены."); return
        self.on_sort_change()

    def find_images_with_colors(self, color1_rgb, color2_rgb=None):
        results_with_data = []
        supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
        for filename in os.listdir(self.folder_path):
            if filename.lower().endswith(supported_formats):
                file_path = os.path.join(self.folder_path, filename)
                try:
                    with Image.open(file_path) as img:
                        img_rgb = img.convert('RGB')
                        image_colors = set(img_rgb.getdata())
                        if color1_rgb in image_colors:
                            if color2_rgb is None or color2_rgb in image_colors:
                                width, height = img.size
                                results_with_data.append((file_path, width * height, (width, height)))
                except Exception as e:
                    print(f"Не удалось обработать файл {filename}: {e}")
        return results_with_data

    def clear_results(self):
        self.found_data = []
        self.photo_references = []
        for widget in self.results_frame.winfo_children(): widget.destroy()

    def redraw_results_grid(self, event=None):
        for widget in self.results_frame.winfo_children(): widget.destroy()
        self.photo_references = []
        if not self.found_data: return
        canvas_width = self.canvas.winfo_width()
        max_cols = max(1, canvas_width // (THUMBNAIL_SIZE[0] + 20))
        for i, (path, total_pixels, dims) in enumerate(self.found_data):
            row, col = divmod(i, max_cols)
            try:
                item_frame = tk.Frame(self.results_frame, bg=BG_COLOR)
                item_frame.grid(row=row, column=col, padx=10, pady=10)
                with Image.open(path) as img:
                    img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                self.photo_references.append(photo)
                img_label = tk.Label(item_frame, image=photo, bg=BG_COLOR)
                img_label.pack()
                filename = os.path.basename(path)
                text_label = tk.Label(item_frame, text=filename, font=FONT_TUPLE, bg=BG_COLOR,
                                      wraplength=THUMBNAIL_SIZE[0])
                text_label.pack()

                dim_text = f"{dims[0]}x{dims[1]} px"
                dim_label = tk.Label(item_frame, text=dim_text, font=DIM_FONT_TUPLE, bg=BG_COLOR, fg="gray")
                dim_label.pack()

                handler = lambda e, p=path: self.show_context_menu(e, p)
                item_frame.bind("<Button-3>", handler)
                img_label.bind("<Button-3>", handler)
                text_label.bind("<Button-3>", handler)
                dim_label.bind("<Button-3>", handler)
            except Exception as e:
                print(f"Ошибка при отображении файла {path}: {e}")

    def show_context_menu(self, event, path):
        context_menu = tk.Menu(self.root, tearoff=0)
        if sys.platform == "win32":
            label = "Открыть в Проводнике"
        elif sys.platform == "darwin":
            label = "Показать в Finder"
        else:
            label = "Открыть расположение файла"
        context_menu.add_command(label=label, command=lambda: self.open_in_explorer(path))
        context_menu.post(event.x_root, event.y_root)

    def open_in_explorer(self, path):
        path = os.path.abspath(path)
        if sys.platform == "win32":
            if PYWIN32_AVAILABLE:
                try:
                    self._open_in_explorer_windows_advanced(path)
                    return
                except Exception as e:
                    print(f"Ошибка в продвинутом методе открытия: {e}")
            subprocess.run(['explorer', '/select,', os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.run(['open', '-R', path])
        else:
            subprocess.run(['xdg-open', os.path.dirname(path)])

    def _open_in_explorer_windows_advanced(self, path):
        """
        Активирует существующее окно проводника с нужной папкой и выделяет файл.
        Если такого окна нет — открывает новое через explorer /select.
        """
        if not PYWIN32_AVAILABLE:
            raise RuntimeError("pywin32 не доступен")

        # Нормализуем пути (без чувствительности к регистру)
        target_folder = os.path.normcase(os.path.normpath(os.path.dirname(path)))
        target_name = os.path.basename(path)

        shell = win32com.client.Dispatch("Shell.Application")

        # Флаги ShellFolderView.SelectItem
        SVSI_SELECT = 0x1
        SVSI_DESELECTOTHERS = 0x4
        SVSI_ENSUREVISIBLE = 0x8

        # Перебираем все окна проводника
        for window in list(shell.Windows()):
            try:
                doc = window.Document
                # Отсекаем не-проводник (например IE, Edge WebView и пр.)
                if not hasattr(doc, "Folder") or doc.Folder is None:
                    continue

                # Текущая открытая папка окна
                current_path = os.path.normcase(os.path.normpath(doc.Folder.Self.Path or ""))

                if current_path == target_folder:
                    # Нашли нужную папку — активируем окно
                    try:
                        win32gui.SetForegroundWindow(window.HWND)
                    except Exception:
                        window.Visible = True

                    # Ищем нужный файл среди элементов папки
                    items = doc.Folder.Items()
                    match = None
                    for i in range(items.Count):
                        it = items.Item(i)
                        if it and os.path.normcase(it.Name) == os.path.normcase(target_name):
                            match = it
                            break

                    # Резервный способ (если представление не успело обновиться)
                    if match is None:
                        match = doc.Folder.ParseName(target_name)

                    if match is not None:
                        doc.SelectItem(match, SVSI_SELECT | SVSI_DESELECTOTHERS | SVSI_ENSUREVISIBLE)
                        return
                    else:
                        # Не нашли сам файл — fallback
                        break

            except Exception:
                # Игнорируем «не наши» окна/ошибки COM и идём дальше
                continue

        # Окна с нужной папкой нет — открываем новое и выделяем файл
        subprocess.run(['explorer', '/select,', os.path.normpath(path)])


# --- ВОТ ВОЗВРАЩЕННЫЙ БЛОК ДЛЯ ЗАПУСКА ПРИЛОЖЕНИЯ ---
if __name__ == "__main__":
    root = tk.Tk()
    app = ProductionImageFinderApp(root)
    root.mainloop()