from __future__ import annotations

import csv
import io
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "family_storage.db"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DB)))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "family-storage-demo-secret")


CATEGORIES = [
    "衣物",
    "书籍",
    "食品",
    "药品",
    "厨房用品",
    "清洁用品",
    "电子产品",
    "工具",
    "证件资料",
    "其他",
]

STATUSES = [
    "正常使用",
    "闲置",
    "借出",
    "损坏",
    "已丢弃",
    "即将过期",
    "已过期",
]


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    with get_connection() as conn:
        conn.execute(
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


def normalize_status(expiry_date: str, status: str) -> str:
    if not expiry_date:
        return status
    try:
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
    except ValueError:
        return status

    days = (expiry - date.today()).days
    if days < 0:
        return "已过期"
    if days <= 30:
        return "即将过期"
    return status


def validate_form(form) -> tuple[dict, str | None]:
    data = {
        "item_code": form.get("item_code", "").strip(),
        "name": form.get("name", "").strip(),
        "category": form.get("category", "").strip(),
        "room": form.get("room", "").strip(),
        "location": form.get("location", "").strip(),
        "quantity": form.get("quantity", "").strip(),
        "purchase_date": form.get("purchase_date", "").strip(),
        "expiry_date": form.get("expiry_date", "").strip(),
        "status": form.get("status", "").strip(),
        "notes": form.get("notes", "").strip(),
    }

    required = ["item_code", "name", "category", "room", "location", "quantity", "status"]
    if any(not data[key] for key in required):
        return data, "请填写所有必填项目。"

    try:
        data["quantity"] = int(data["quantity"])
        if data["quantity"] < 0:
            raise ValueError
    except ValueError:
        return data, "数量必须是大于或等于 0 的整数。"

    for field, label in [("purchase_date", "购入日期"), ("expiry_date", "有效期")]:
        value = data[field]
        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return data, f"{label}格式应为 YYYY-MM-DD。"

    data["status"] = normalize_status(data["expiry_date"], data["status"])
    return data, None


def query_items(keyword: str = "", category: str = "全部", status: str = "全部"):
    sql = "SELECT * FROM items WHERE 1=1"
    params: list[str] = []

    if keyword:
        sql += """
            AND (
                item_code LIKE ? OR
                name LIKE ? OR
                room LIKE ? OR
                location LIKE ? OR
                notes LIKE ?
            )
        """
        like_value = f"%{keyword}%"
        params.extend([like_value] * 5)

    if category != "全部":
        sql += " AND category = ?"
        params.append(category)

    if status != "全部":
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY id DESC"

    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


@app.route("/")
def index():
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "全部")
    status = request.args.get("status", "全部")
    items = query_items(keyword, category, status)

    with get_connection() as conn:
        record_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        quantity_total = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM items"
        ).fetchone()[0]
        expiring_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status = '即将过期'"
        ).fetchone()[0]
        expired_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status = '已过期'"
        ).fetchone()[0]

    return render_template(
        "index.html",
        items=items,
        categories=CATEGORIES,
        statuses=STATUSES,
        keyword=keyword,
        selected_category=category,
        selected_status=status,
        record_count=record_count,
        quantity_total=quantity_total,
        expiring_count=expiring_count,
        expired_count=expired_count,
    )


@app.route("/add", methods=["GET", "POST"])
def add_item():
    if request.method == "POST":
        data, error = validate_form(request.form)
        if error:
            flash(error, "error")
            return render_template(
                "form.html",
                title="新增物品",
                item=data,
                categories=CATEGORIES,
                statuses=STATUSES,
            )

        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO items (
                        item_code, name, category, room, location, quantity,
                        purchase_date, expiry_date, status, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["item_code"],
                        data["name"],
                        data["category"],
                        data["room"],
                        data["location"],
                        data["quantity"],
                        data["purchase_date"],
                        data["expiry_date"],
                        data["status"],
                        data["notes"],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
            flash("物品信息已保存。", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("物品编号已存在，请更换编号。", "error")

    return render_template(
        "form.html",
        title="新增物品",
        item={},
        categories=CATEGORIES,
        statuses=STATUSES,
    )


@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
def edit_item(item_id: int):
    with get_connection() as conn:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

    if item is None:
        flash("未找到该物品记录。", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        data, error = validate_form(request.form)
        if error:
            flash(error, "error")
            return render_template(
                "form.html",
                title="修改物品",
                item=data,
                categories=CATEGORIES,
                statuses=STATUSES,
            )

        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE items SET
                        item_code = ?,
                        name = ?,
                        category = ?,
                        room = ?,
                        location = ?,
                        quantity = ?,
                        purchase_date = ?,
                        expiry_date = ?,
                        status = ?,
                        notes = ?
                    WHERE id = ?
                    """,
                    (
                        data["item_code"],
                        data["name"],
                        data["category"],
                        data["room"],
                        data["location"],
                        data["quantity"],
                        data["purchase_date"],
                        data["expiry_date"],
                        data["status"],
                        data["notes"],
                        item_id,
                    ),
                )
            flash("物品信息已更新。", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("物品编号已存在，请更换编号。", "error")

    return render_template(
        "form.html",
        title="修改物品",
        item=dict(item),
        categories=CATEGORIES,
        statuses=STATUSES,
    )


@app.post("/delete/<int:item_id>")
def delete_item(item_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    flash("物品记录已删除。", "success")
    return redirect(url_for("index"))


@app.route("/export")
def export_csv():
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "全部")
    status = request.args.get("status", "全部")
    items = query_items(keyword, category, status)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "物品编号",
            "物品名称",
            "类别",
            "房间",
            "具体位置",
            "数量",
            "购入日期",
            "有效期",
            "状态",
            "备注",
            "创建时间",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item["id"],
                item["item_code"],
                item["name"],
                item["category"],
                item["room"],
                item["location"],
                item["quantity"],
                item["purchase_date"],
                item["expiry_date"],
                item["status"],
                item["notes"],
                item["created_at"],
            ]
        )

    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    return send_file(
        io.BytesIO(content),
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name="家庭物品清单.csv",
    )


@app.route("/health")
def health():
    return {"status": "ok"}


init_database()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
