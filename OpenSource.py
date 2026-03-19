import os
import threading
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from lupa import LuaRuntime
import sys

def resource_path(relative_path):
    """ Получает путь к ресурсам для PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Попытка импорта подсветки синтаксиса
try:
    from pygments.lexers import LuaLexer
except ImportError:
    LuaLexer = None

# Конфигурация темы
CODE_COLORS = {
    'Token.Keyword': '#569cd6', 'Token.Name.Function': '#dcdcaa', 
    'Token.Literal.String': '#ce9178', 'Token.Comment': '#6a9955', 
    'Token.Literal.Number': '#b5cea8', 'Token.Operator': '#d4d4d4'
}

DARK_THEME = {
    "bg": "#1e1e1e", "fg": "#d4d4d4", "sidebar": "#252526", 
    "header": "#333333", "text_bg": "#1e1e1e", "term_bg": "#0c0c0c", "accent": "#4CAF50"
}

class InteractiveTerminal(tk.Text):
    """Окно вывода логов и результатов работы Lua"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.reset_prompt()

    def log(self, message):
        self.insert(tk.END, str(message) + "\n")
        self.see(tk.END)

    def reset_prompt(self):
        self.insert(tk.END, f"\n{os.getcwd()}> ")
        self.see(tk.END)

class EditorTab(tk.Frame):
    """Вкладка редактора с номерами строк и подсветкой"""
    def __init__(self, parent, file_path, theme, **kwargs):
        super().__init__(parent)
        self.file_path = file_path
        self.line_numbers = tk.Canvas(self, width=45, bg=theme["sidebar"], bd=0, highlightthickness=0)
        self.line_numbers.pack(side="left", fill="y")
        self.text = tk.Text(self, **kwargs)
        self.text.pack(side="right", fill="both", expand=True)
        self.text.bind("<KeyRelease>", self.on_change)

    def on_change(self, event=None):
        self.redraw_line_numbers()
        if LuaLexer: self.highlight_syntax()

    def redraw_line_numbers(self):
        self.line_numbers.delete("all")
        i = self.text.index("@0,0")
        while True:
            dline = self.text.dlineinfo(i)
            if dline is None: break
            y = dline[1]
            linenum = str(i).split(".")[0]
            self.line_numbers.create_text(38, y, anchor="ne", text=linenum, fill="#858585", font=("Consolas", 11))
            i = self.text.index("%s+1line" % i)

    def highlight_syntax(self):
        data = self.text.get("1.0", tk.END)
        lexer = LuaLexer()
        for tag in self.text.tag_names():
            if tag.startswith("Token."): self.text.tag_remove(tag, "1.0", tk.END)
        current_pos = "1.0"
        for token_type, value in lexer.get_tokens(data):
            token_str = str(token_type)
            start = current_pos
            end = f"{start}+{len(value)}c"
            if token_str in CODE_COLORS:
                self.text.tag_configure(token_str, foreground=CODE_COLORS[token_str])
                self.text.tag_add(token_str, start, end)
            current_pos = end

class LuaStorm(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LuaScriptEdition") # Обновленный заголовок
        self.geometry("1200x800")
        self.current_theme = DARK_THEME
        self.open_tabs = {}

        # 1. Тулбар
        self.toolbar = tk.Frame(self, bg=self.current_theme["header"], height=40)
        self.toolbar.pack(side='top', fill='x')
        
        tk.Button(self.toolbar, text="▶ RUN (F5)", bg="#4CAF50", fg="white", font=("Arial", 9, "bold"),
                  command=self.run_lua_code, relief='flat', padx=15).pack(side='left', padx=10, pady=5)
        
        tk.Button(self.toolbar, text="💾 SAVE (Ctrl+S)", bg="#333", fg="white", 
                  command=self.save_current_file, relief='flat', padx=10).pack(side='left', padx=5, pady=5)

        # 2. Основная рабочая область
        self.main_pw = tk.PanedWindow(self, orient='vertical', bg="#333", sashwidth=4)
        self.main_pw.pack(fill='both', expand=True)

        self.top_pw = tk.PanedWindow(self.main_pw, orient='horizontal', bg="#333", sashwidth=4)
        self.main_pw.add(self.top_pw, height=500)

        # 3. Проводник
        self.tree = ttk.Treeview(self.top_pw, show="tree")
        self.top_pw.add(self.tree, width=250)

        # 4. Редактор
        self.notebook = ttk.Notebook(self.top_pw)
        self.top_pw.add(self.notebook)

        # 5. Терминал
        self.terminal = InteractiveTerminal(self.main_pw, bg="#0c0c0c", fg="#d4d4d4", 
                                            font=("Consolas", 11), insertbackground="white", bd=0)
        self.main_pw.add(self.terminal, height=200)

        # 6. Контекстное меню
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="📄 Новый файл", command=self.create_file)
        self.context_menu.add_command(label="📁 Новая папка", command=self.create_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑 Удалить", command=self.delete_item)

        # События
        self.tree.bind("<Double-1>", self.on_tree_select)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.bind("<F5>", lambda e: self.run_lua_code())
        self.bind("<Control-s>", lambda e: self.save_current_file())

        self.init_explorer()

    def init_explorer(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        root_path = os.path.abspath(".")
        node = self.tree.insert('', 'end', text=f" 📂 PROJECT", values=[root_path], open=True)
        self.populate_tree(node)

    def populate_tree(self, parent_node):
        path = self.tree.item(parent_node, "values")[0]
        try:
            for item in sorted(os.listdir(path)):
                if item.startswith('.'): continue
                f_path = os.path.join(path, item)
                is_dir = os.path.isdir(f_path)
                node = self.tree.insert(parent_node, 'end', text=f"{'📁' if is_dir else '📄'} {item}", values=[f_path])
                if is_dir:
                    self.populate_tree(node)
        except: pass

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def get_target_dir(self):
        selected = self.tree.selection()
        if not selected: return os.path.abspath(".")
        path = self.tree.item(selected[0], "values")[0]
        return path if os.path.isdir(path) else os.path.dirname(path)

    def create_file(self):
        name = simpledialog.askstring("Новый файл", "Имя файла (.lua):")
        if name:
            path = os.path.join(self.get_target_dir(), name)
            open(path, 'w').close()
            self.init_explorer()
            self.open_file(path)

    def create_folder(self):
        name = simpledialog.askstring("Новая папка", "Имя папки:")
        if name:
            os.makedirs(os.path.join(self.get_target_dir(), name), exist_ok=True)
            self.init_explorer()

    def delete_item(self):
        selected = self.tree.selection()
        if not selected: return
        path = self.tree.item(selected[0], "values")[0]
        if messagebox.askyesno("Удаление", f"Удалить {os.path.basename(path)}?"):
            if os.path.isdir(path): shutil.rmtree(path)
            else: os.remove(path)
            self.init_explorer()

    def on_tree_select(self, event):
        item = self.tree.selection()
        if not item: return
        path = self.tree.item(item[0], "values")[0]
        if os.path.isfile(path): self.open_file(path)

    def open_file(self, path):
        if path in self.open_tabs:
            self.notebook.select(self.open_tabs[path])
            return
        
        tab = EditorTab(self.notebook, path, self.current_theme, bg="#1e1e1e", fg="#d4d4d4", 
                        insertbackground="white", font=("Consolas", 12), undo=True)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                tab.text.insert("1.0", content)
                tab.on_change()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
            return

        self.notebook.add(tab, text=os.path.basename(path))
        self.notebook.select(tab)
        self.open_tabs[path] = tab

    def save_current_file(self, event=None):
        current_tab_id = self.notebook.select()
        if not current_tab_id: return
        
        tab_obj = self.notebook.nametowidget(current_tab_id)
        path = tab_obj.file_path
        content = tab_obj.text.get("1.0", tk.END)
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content.strip())
            self.terminal.log(f"💾 Файл сохранен: {path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при сохранении: {e}")

    def run_lua_code(self):
        current_tab_id = self.notebook.select()
        if not current_tab_id: return
        
        tab_obj = self.notebook.nametowidget(current_tab_id)
        code = tab_obj.text.get("1.0", tk.END)
        
        self.terminal.log(f"--- Запуск: {os.path.basename(tab_obj.file_path)} ---")
        
        def execute():
            lua = LuaRuntime(unpack_returned_tuples=True)
            # Переопределяем Lua print для вывода в наш терминал
            lua.globals().print = lambda *args: self.terminal.log(" ".join(map(str, args)))
            
            try:
                lua.execute(code)
            except Exception as e:
                self.terminal.log(f"❌ Lua Error: {e}")
            
            self.terminal.reset_prompt()

        threading.Thread(target=execute, daemon=True).start()

if __name__ == "__main__":
    app = LuaStorm()
    app.mainloop()
  
