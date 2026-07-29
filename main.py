import csv
import sqlite3
import tkinter as tk
from datetime import datetime, date
from pathlib import Path
from tkinter import ttk, messagebox, filedialog


APP_TITLE = "家庭物品收纳管理系统"
DB_PATH = Path(__file__).resolve().parent / "family_storage.db"


class Database:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                room TEXT NOT NULL,
                location TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                purchase_date TEXT,
                expiry_date TEXT,
                status TEXT NOT NULL DEFAULT '正常使用',
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def add_item(self, data):
        self.conn.execute(
            """
            INSERT INTO items (
                item_code, name, category, room, location, quantity,
                purchase_date, expiry_date, status, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["item_code"], data["name"], data["category"],
                data["room"], data["location"], data["quantity"],
                data["purchase_date"], data["expiry_date"],
                data["status"], data["notes"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        self.conn.commit()

    def update_item(self, item_id, data):
        self.conn.execute(
            """
            UPDATE items SET
                item_code=?, name=?, category=?, room=?, location=?,
                quantity=?, purchase_date=?, expiry_date=?, status=?, notes=?
            WHERE id=?
            """,
            (
                data["item_code"], data["name"], data["category"],
                data["room"], data["location"], data["quantity"],
                data["purchase_date"], data["expiry_date"],
                data["status"], data["notes"], item_id,
            ),
        )
        self.conn.commit()

    def delete_item(self, item_id):
        self.conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self.conn.commit()

    def fetch_items(self, keyword="", category="全部", status="全部"):
        sql = "SELECT * FROM items WHERE 1=1"
        params = []

        if keyword:
            sql += """
                AND (
                    item_code LIKE ? OR name LIKE ? OR room LIKE ?
                    OR location LIKE ? OR notes LIKE ?
                )
            """
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw, kw, kw])

        if category != "全部":
            sql += " AND category=?"
            params.append(category)

        if status != "全部":
            sql += " AND status=?"
            params.append(status)

        sql += " ORDER BY id DESC"
        return self.conn.execute(sql, params).fetchall()

    def get_item(self, item_id):
        return self.conn.execute(
            "SELECT * FROM items WHERE id=?", (item_id,)
        ).fetchone()

    def count_items(self):
        return self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    def sum_quantity(self):
        return self.conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM items"
        ).fetchone()[0]

    def category_stats(self):
        return self.conn.execute(
            """
            SELECT category, COUNT(*) AS count, SUM(quantity) AS quantity
            FROM items
            GROUP BY category
            ORDER BY quantity DESC
            """
        ).fetchall()

    def expiring_count(self, days=30):
        rows = self.conn.execute(
            "SELECT expiry_date FROM items WHERE expiry_date IS NOT NULL AND expiry_date != ''"
        ).fetchall()
        today = date.today()
        count = 0
        for row in rows:
            try:
                expiry = datetime.strptime(row["expiry_date"], "%Y-%m-%d").date()
                delta = (expiry - today).days
                if 0 <= delta <= days:
                    count += 1
            except ValueError:
                pass
        return count

    def expired_count(self):
        rows = self.conn.execute(
            "SELECT expiry_date FROM items WHERE expiry_date IS NOT NULL AND expiry_date != ''"
        ).fetchall()
        today = date.today()
        count = 0
        for row in rows:
            try:
                expiry = datetime.strptime(row["expiry_date"], "%Y-%m-%d").date()
                if expiry < today:
                    count += 1
            except ValueError:
                pass
        return count


class ItemDialog(tk.Toplevel):
    CATEGORIES = [
        "衣物", "书籍", "食品", "药品", "厨房用品",
        "清洁用品", "电子产品", "工具", "证件资料", "其他"
    ]
    STATUSES = ["正常使用", "闲置", "借出", "损坏", "已丢弃", "即将过期", "已过期"]

    def __init__(self, parent, title, initial=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        self.initial = initial or {}

        self.transient(parent)
        self.grab_set()

        self.vars = {
            "item_code": tk.StringVar(value=self.initial.get("item_code", "")),
            "name": tk.StringVar(value=self.initial.get("name", "")),
            "category": tk.StringVar(value=self.initial.get("category", "其他")),
            "room": tk.StringVar(value=self.initial.get("room", "")),
            "location": tk.StringVar(value=self.initial.get("location", "")),
            "quantity": tk.StringVar(value=str(self.initial.get("quantity", 1))),
            "purchase_date": tk.StringVar(value=self.initial.get("purchase_date", "")),
            "expiry_date": tk.StringVar(value=self.initial.get("expiry_date", "")),
            "status": tk.StringVar(value=self.initial.get("status", "正常使用")),
        }

        self.build_ui()
        self.center_on_parent(parent)

    def build_ui(self):
        frame = ttk.Frame(self, padding=18)
        frame.grid(sticky="nsew")

        labels = [
            ("物品编号*", "item_code"),
            ("物品名称*", "name"),
            ("物品类别*", "category"),
            ("存放房间*", "room"),
            ("具体位置*", "location"),
            ("数量*", "quantity"),
            ("购入日期", "purchase_date"),
            ("有效期", "expiry_date"),
            ("物品状态*", "status"),
        ]

        for row, (label, key) in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="e", padx=(0, 10), pady=6)

            if key == "category":
                widget = ttk.Combobox(
                    frame, textvariable=self.vars[key],
                    values=self.CATEGORIES, state="readonly", width=28
                )
            elif key == "status":
                widget = ttk.Combobox(
                    frame, textvariable=self.vars[key],
                    values=self.STATUSES, state="readonly", width=28
                )
            else:
                widget = ttk.Entry(frame, textvariable=self.vars[key], width=31)

            widget.grid(row=row, column=1, sticky="w", pady=6)

        ttk.Label(frame, text="日期格式：YYYY-MM-DD").grid(
            row=9, column=1, sticky="w", pady=(0, 6)
        )

        ttk.Label(frame, text="备注").grid(row=10, column=0, sticky="ne", padx=(0, 10), pady=6)
        self.notes = tk.Text(frame, width=31, height=5)
        self.notes.grid(row=10, column=1, sticky="w", pady=6)
        self.notes.insert("1.0", self.initial.get("notes", "") or "")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=11, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(btn_frame, text="保存", command=self.save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=6)

    def center_on_parent(self, parent):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    @staticmethod
    def validate_date(value):
        if not value:
            return True
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def save(self):
        data = {key: var.get().strip() for key, var in self.vars.items()}
        data["notes"] = self.notes.get("1.0", "end").strip()

        required = ["item_code", "name", "category", "room", "location", "quantity", "status"]
        if any(not data[key] for key in required):
            messagebox.showwarning("提示", "请填写所有带 * 的必填项目。", parent=self)
            return

        try:
            data["quantity"] = int(data["quantity"])
            if data["quantity"] < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "数量必须是大于或等于0的整数。", parent=self)
            return

        if not self.validate_date(data["purchase_date"]):
            messagebox.showwarning("提示", "购入日期格式应为 YYYY-MM-DD。", parent=self)
            return

        if not self.validate_date(data["expiry_date"]):
            messagebox.showwarning("提示", "有效期格式应为 YYYY-MM-DD。", parent=self)
            return

        self.result = data
        self.destroy()


class FamilyStorageApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x720")
        self.minsize(980, 620)

        self.db = Database(DB_PATH)
        self.selected_item_id = None

        self.keyword_var = tk.StringVar()
        self.category_var = tk.StringVar(value="全部")
        self.status_var = tk.StringVar(value="全部")

        self.configure_style()
        self.build_ui()
        self.refresh_all()

    def configure_style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Arial", 20, "bold"))
        style.configure("CardTitle.TLabel", font=("Arial", 11))
        style.configure("CardValue.TLabel", font=("Arial", 24, "bold"))
        style.configure("Treeview", rowheight=30)
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

    def build_ui(self):
        header = ttk.Frame(self, padding=(20, 16))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")

        card_frame = ttk.Frame(self, padding=(20, 0, 20, 12))
        card_frame.pack(fill="x")

        self.total_card = self.create_card(card_frame, "物品记录数")
        self.quantity_card = self.create_card(card_frame, "物品总数量")
        self.expiring_card = self.create_card(card_frame, "30天内到期")
        self.expired_card = self.create_card(card_frame, "已过期")

        for card in [self.total_card, self.quantity_card, self.expiring_card, self.expired_card]:
            card["frame"].pack(side="left", fill="x", expand=True, padx=6)

        toolbar = ttk.LabelFrame(self, text="查询条件", padding=12)
        toolbar.pack(fill="x", padx=20, pady=(0, 12))

        ttk.Label(toolbar, text="关键词").pack(side="left")
        search_entry = ttk.Entry(toolbar, textvariable=self.keyword_var, width=24)
        search_entry.pack(side="left", padx=(6, 14))
        search_entry.bind("<Return>", lambda _event: self.refresh_table())

        ttk.Label(toolbar, text="类别").pack(side="left")
        ttk.Combobox(
            toolbar,
            textvariable=self.category_var,
            values=["全部"] + ItemDialog.CATEGORIES,
            state="readonly",
            width=12,
        ).pack(side="left", padx=(6, 14))

        ttk.Label(toolbar, text="状态").pack(side="left")
        ttk.Combobox(
            toolbar,
            textvariable=self.status_var,
            values=["全部"] + ItemDialog.STATUSES,
            state="readonly",
            width=12,
        ).pack(side="left", padx=(6, 14))

        ttk.Button(toolbar, text="查询", command=self.refresh_table).pack(side="left", padx=4)
        ttk.Button(toolbar, text="重置", command=self.reset_search).pack(side="left", padx=4)

        action_frame = ttk.Frame(self, padding=(20, 0, 20, 10))
        action_frame.pack(fill="x")
        ttk.Button(action_frame, text="新增物品", command=self.add_item).pack(side="left", padx=(0, 8))
        ttk.Button(action_frame, text="修改物品", command=self.edit_item).pack(side="left", padx=8)
        ttk.Button(action_frame, text="删除物品", command=self.delete_item).pack(side="left", padx=8)
        ttk.Button(action_frame, text="导出 CSV", command=self.export_csv).pack(side="left", padx=8)
        ttk.Button(action_frame, text="刷新", command=self.refresh_all).pack(side="left", padx=8)

        table_frame = ttk.Frame(self, padding=(20, 0, 20, 16))
        table_frame.pack(fill="both", expand=True)

        columns = (
            "id", "item_code", "name", "category", "room", "location",
            "quantity", "purchase_date", "expiry_date", "status", "notes"
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")

        headings = {
            "id": "ID",
            "item_code": "物品编号",
            "name": "物品名称",
            "category": "类别",
            "room": "房间",
            "location": "具体位置",
            "quantity": "数量",
            "purchase_date": "购入日期",
            "expiry_date": "有效期",
            "status": "状态",
            "notes": "备注",
        }

        widths = {
            "id": 55,
            "item_code": 100,
            "name": 130,
            "category": 95,
            "room": 90,
            "location": 140,
            "quantity": 60,
            "purchase_date": 95,
            "expiry_date": 95,
            "status": 90,
            "notes": 180,
        }

        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="center")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda _event: self.edit_item())

        self.status_bar = ttk.Label(self, text="", anchor="w", padding=(20, 8))
        self.status_bar.pack(fill="x")

    def create_card(self, parent, title):
        frame = ttk.LabelFrame(parent, padding=12)
        title_label = ttk.Label(frame, text=title, style="CardTitle.TLabel")
        title_label.pack()
        value_label = ttk.Label(frame, text="0", style="CardValue.TLabel")
        value_label.pack(pady=(4, 0))
        return {"frame": frame, "value": value_label}

    def refresh_all(self):
        self.refresh_table()
        self.refresh_dashboard()

    def refresh_dashboard(self):
        self.total_card["value"].configure(text=str(self.db.count_items()))
        self.quantity_card["value"].configure(text=str(self.db.sum_quantity()))
        self.expiring_card["value"].configure(text=str(self.db.expiring_count()))
        self.expired_card["value"].configure(text=str(self.db.expired_count()))

    def refresh_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        rows = self.db.fetch_items(
            keyword=self.keyword_var.get().strip(),
            category=self.category_var.get(),
            status=self.status_var.get(),
        )

        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"], row["item_code"], row["name"], row["category"],
                    row["room"], row["location"], row["quantity"],
                    row["purchase_date"] or "", row["expiry_date"] or "",
                    row["status"], row["notes"] or "",
                ),
            )

        self.selected_item_id = None
        self.status_bar.configure(text=f"当前显示 {len(rows)} 条记录")

    def reset_search(self):
        self.keyword_var.set("")
        self.category_var.set("全部")
        self.status_var.set("全部")
        self.refresh_table()

    def on_select(self, _event=None):
        selection = self.tree.selection()
        if selection:
            values = self.tree.item(selection[0], "values")
            self.selected_item_id = int(values[0])

    def add_item(self):
        dialog = ItemDialog(self, "新增物品")
        self.wait_window(dialog)

        if dialog.result:
            try:
                self.db.add_item(dialog.result)
                self.refresh_all()
                messagebox.showinfo("成功", "物品信息已保存。")
            except sqlite3.IntegrityError:
                messagebox.showerror("错误", "物品编号已存在，请更换编号。")
            except sqlite3.Error as exc:
                messagebox.showerror("数据库错误", str(exc))

    def edit_item(self):
        if not self.selected_item_id:
            messagebox.showwarning("提示", "请先选择一条物品记录。")
            return

        row = self.db.get_item(self.selected_item_id)
        if not row:
            messagebox.showerror("错误", "未找到所选记录。")
            return

        dialog = ItemDialog(self, "修改物品", dict(row))
        self.wait_window(dialog)

        if dialog.result:
            try:
                self.db.update_item(self.selected_item_id, dialog.result)
                self.refresh_all()
                messagebox.showinfo("成功", "物品信息已更新。")
            except sqlite3.IntegrityError:
                messagebox.showerror("错误", "物品编号已存在，请更换编号。")
            except sqlite3.Error as exc:
                messagebox.showerror("数据库错误", str(exc))

    def delete_item(self):
        if not self.selected_item_id:
            messagebox.showwarning("提示", "请先选择一条物品记录。")
            return

        if not messagebox.askyesno("确认删除", "确定要删除所选物品记录吗？"):
            return

        try:
            self.db.delete_item(self.selected_item_id)
            self.refresh_all()
            messagebox.showinfo("成功", "物品记录已删除。")
        except sqlite3.Error as exc:
            messagebox.showerror("数据库错误", str(exc))

    def export_csv(self):
        rows = self.db.fetch_items(
            keyword=self.keyword_var.get().strip(),
            category=self.category_var.get(),
            status=self.status_var.get(),
        )

        if not rows:
            messagebox.showwarning("提示", "当前没有可导出的数据。")
            return

        path = filedialog.asksaveasfilename(
            title="导出物品数据",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            initialfile="家庭物品清单.csv",
        )
        if not path:
            return

        headers = [
            "ID", "物品编号", "物品名称", "类别", "房间", "具体位置",
            "数量", "购入日期", "有效期", "状态", "备注", "创建时间"
        ]

        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([
                    row["id"], row["item_code"], row["name"], row["category"],
                    row["room"], row["location"], row["quantity"],
                    row["purchase_date"], row["expiry_date"], row["status"],
                    row["notes"], row["created_at"],
                ])

        messagebox.showinfo("导出成功", f"数据已导出到：\n{path}")


if __name__ == "__main__":
    app = FamilyStorageApp()
    app.mainloop()
