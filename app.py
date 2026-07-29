from __future__ import annotations

import csv
import io
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import qrcode
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
    "衣物", "书籍", "食品", "药品", "厨房用品",
    "清洁用品", "电子产品", "工具", "证件资料", "其他",
]

CATEGORY_PREFIXES = {
    "衣物": "CLO",
    "书籍": "BOOK",
    "食品": "FOOD",
    "药品": "MED",
    "厨房用品": "KIT",
    "清洁用品": "CLE",
    "电子产品": "ELE",
    "工具": "TOOL",
    "证件资料": "DOC",
    "其他": "OTH",
}

STATUSES = ["正常使用", "闲置", "借出", "损坏", "已丢弃", "即将过期", "已过期"]


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
                min_quantity INTEGER NOT NULL DEFAULT 0,
                purchase_date TEXT,
                expiry_date TEXT,
                status TEXT NOT NULL DEFAULT '正常使用',
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
        if "min_quantity" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN min_quantity INTEGER NOT NULL DEFAULT 0")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shopping_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                source_item_id INTEGER,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(name, completed)
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
    if status in {"已过期", "即将过期"}:
        return "正常使用"
    return status


def next_item_code(category: str) -> str:
    prefix = CATEGORY_PREFIXES.get(category, "OTH")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT item_code FROM items WHERE item_code LIKE ?",
            (f"{prefix}-%",),
        ).fetchall()
    numbers = []
    for row in rows:
        try:
            numbers.append(int(row["item_code"].split("-")[-1]))
        except (ValueError, IndexError):
            continue
    return f"{prefix}-{(max(numbers, default=0) + 1):03d}"


def validate_form(form) -> tuple[dict, str | None]:
    data = {
        "item_code": form.get("item_code", "").strip(),
        "name": form.get("name", "").strip(),
        "category": form.get("category", "").strip(),
        "room": form.get("room", "").strip(),
        "location": form.get("location", "").strip(),
        "quantity": form.get("quantity", "").strip(),
        "min_quantity": form.get("min_quantity", "0").strip(),
        "purchase_date": form.get("purchase_date", "").strip(),
        "expiry_date": form.get("expiry_date", "").strip(),
        "status": form.get("status", "").strip(),
        "notes": form.get("notes", "").strip(),
    }

    if not data["item_code"] and data["category"]:
        data["item_code"] = next_item_code(data["category"])

    required = ["item_code", "name", "category", "room", "location", "quantity", "status"]
    if any(not data[key] for key in required):
        return data, "请填写所有必填项目。"

    try:
        data["quantity"] = int(data["quantity"])
        data["min_quantity"] = int(data["min_quantity"] or 0)
        if data["quantity"] < 0 or data["min_quantity"] < 0:
            raise ValueError
    except ValueError:
        return data, "数量和最低库存必须是大于或等于 0 的整数。"

    for field, label in [("purchase_date", "购入日期"), ("expiry_date", "有效期")]:
        if data[field]:
            try:
                datetime.strptime(data[field], "%Y-%m-%d")
            except ValueError:
                return data, f"{label}格式应为 YYYY-MM-DD。"

    data["status"] = normalize_status(data["expiry_date"], data["status"])
    return data, None


def refresh_expiry_statuses() -> None:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, expiry_date, status FROM items").fetchall()
        for row in rows:
            new_status = normalize_status(row["expiry_date"] or "", row["status"])
            if new_status != row["status"]:
                conn.execute("UPDATE items SET status = ? WHERE id = ?", (new_status, row["id"]))


def sync_low_stock_to_shopping() -> int:
    created = 0
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, quantity, min_quantity
            FROM items
            WHERE min_quantity > 0 AND quantity <= min_quantity
            """
        ).fetchall()
        for row in rows:
            need = max(row["min_quantity"] - row["quantity"] + 1, 1)
            exists = conn.execute(
                "SELECT id FROM shopping_items WHERE name = ? AND completed = 0",
                (row["name"],),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO shopping_items (name, quantity, source_item_id, completed, created_at)
                    VALUES (?, ?, ?, 0, ?)
                    """,
                    (row["name"], need, row["id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                created += 1
    return created


def query_items(keyword: str = "", category: str = "全部", status: str = "全部"):
    sql = "SELECT * FROM items WHERE 1=1"
    params: list[str] = []
    if keyword:
        sql += """
            AND (
                item_code LIKE ? OR name LIKE ? OR room LIKE ?
                OR location LIKE ? OR notes LIKE ?
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
    refresh_expiry_statuses()
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "全部")
    status = request.args.get("status", "全部")
    items = query_items(keyword, category, status)

    with get_connection() as conn:
        record_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        quantity_total = conn.execute("SELECT COALESCE(SUM(quantity), 0) FROM items").fetchone()[0]
        expiring_count = conn.execute("SELECT COUNT(*) FROM items WHERE status = '即将过期'").fetchone()[0]
        expired_count = conn.execute("SELECT COUNT(*) FROM items WHERE status = '已过期'").fetchone()[0]
        low_stock_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE min_quantity > 0 AND quantity <= min_quantity"
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
        low_stock_count=low_stock_count,
    )


@app.route("/generate-code")
def generate_code():
    category = request.args.get("category", "其他")
    return {"code": next_item_code(category)}


@app.route("/add", methods=["GET", "POST"])
def add_item():
    if request.method == "POST":
        data, error = validate_form(request.form)
        if error:
            flash(error, "error")
            return render_template("form.html", title="新增物品", item=data, categories=CATEGORIES, statuses=STATUSES)
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO items (
                        item_code, name, category, room, location, quantity, min_quantity,
                        purchase_date, expiry_date, status, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["item_code"], data["name"], data["category"], data["room"],
                        data["location"], data["quantity"], data["min_quantity"],
                        data["purchase_date"], data["expiry_date"], data["status"],
                        data["notes"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
            flash("物品信息已保存。", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("物品编号已存在，请更换编号。", "error")

    default_item = {"category": "其他", "item_code": next_item_code("其他"), "quantity": 1, "min_quantity": 0}
    return render_template("form.html", title="新增物品", item=default_item, categories=CATEGORIES, statuses=STATUSES)


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
            return render_template("form.html", title="修改物品", item=data, categories=CATEGORIES, statuses=STATUSES)
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE items SET item_code=?, name=?, category=?, room=?, location=?,
                        quantity=?, min_quantity=?, purchase_date=?, expiry_date=?, status=?, notes=?
                    WHERE id=?
                    """,
                    (
                        data["item_code"], data["name"], data["category"], data["room"],
                        data["location"], data["quantity"], data["min_quantity"],
                        data["purchase_date"], data["expiry_date"], data["status"],
                        data["notes"], item_id,
                    ),
                )
            flash("物品信息已更新。", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("物品编号已存在，请更换编号。", "error")

    return render_template("form.html", title="修改物品", item=dict(item), categories=CATEGORIES, statuses=STATUSES)


@app.post("/delete/<int:item_id>")
def delete_item(item_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM shopping_items WHERE source_item_id = ?", (item_id,))
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    flash("物品记录已删除。", "success")
    return redirect(url_for("index"))


@app.route("/reminders")
def reminders():
    refresh_expiry_statuses()
    with get_connection() as conn:
        expiring = conn.execute(
            "SELECT * FROM items WHERE status = '即将过期' ORDER BY expiry_date"
        ).fetchall()
        expired = conn.execute(
            "SELECT * FROM items WHERE status = '已过期' ORDER BY expiry_date"
        ).fetchall()
        low_stock = conn.execute(
            """
            SELECT * FROM items
            WHERE min_quantity > 0 AND quantity <= min_quantity
            ORDER BY quantity ASC
            """
        ).fetchall()
    return render_template("reminders.html", expiring=expiring, expired=expired, low_stock=low_stock)


@app.post("/shopping/sync")
def shopping_sync():
    created = sync_low_stock_to_shopping()
    flash(f"已将 {created} 个低库存物品加入购物清单。", "success")
    return redirect(url_for("shopping_list"))


@app.route("/shopping", methods=["GET", "POST"])
def shopping_list():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            quantity = max(int(request.form.get("quantity", "1")), 1)
        except ValueError:
            quantity = 1
        if not name:
            flash("请输入需要购买的物品名称。", "error")
        else:
            try:
                with get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO shopping_items (name, quantity, completed, created_at)
                        VALUES (?, ?, 0, ?)
                        """,
                        (name, quantity, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    )
                flash("已加入购物清单。", "success")
            except sqlite3.IntegrityError:
                flash("该物品已在未完成的购物清单中。", "error")
        return redirect(url_for("shopping_list"))

    with get_connection() as conn:
        active = conn.execute(
            "SELECT * FROM shopping_items WHERE completed = 0 ORDER BY id DESC"
        ).fetchall()
        completed = conn.execute(
            "SELECT * FROM shopping_items WHERE completed = 1 ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return render_template("shopping.html", active=active, completed=completed)


@app.post("/shopping/toggle/<int:shopping_id>")
def shopping_toggle(shopping_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT completed FROM shopping_items WHERE id = ?", (shopping_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE shopping_items SET completed = ? WHERE id = ?",
                (0 if row["completed"] else 1, shopping_id),
            )
    return redirect(url_for("shopping_list"))


@app.post("/shopping/delete/<int:shopping_id>")
def shopping_delete(shopping_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM shopping_items WHERE id = ?", (shopping_id,))
    return redirect(url_for("shopping_list"))


@app.route("/locations")
def locations():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT room, location, COUNT(*) AS item_count, SUM(quantity) AS quantity_total
            FROM items
            GROUP BY room, location
            ORDER BY room, location
            """
        ).fetchall()
    return render_template("locations.html", locations=rows)


@app.route("/location")
def location_detail():
    room = request.args.get("room", "")
    location = request.args.get("location", "")
    with get_connection() as conn:
        items = conn.execute(
            "SELECT * FROM items WHERE room = ? AND location = ? ORDER BY name",
            (room, location),
        ).fetchall()
    return render_template("location_detail.html", room=room, location=location, items=items)


@app.route("/location-qr")
def location_qr():
    room = request.args.get("room", "")
    location = request.args.get("location", "")
    target = url_for("location_detail", room=room, location=location, _external=True)
    image = qrcode.make(target)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png", download_name=f"{room}-{location}.png")


@app.route("/export")
def export_csv():
    items = query_items(
        request.args.get("keyword", "").strip(),
        request.args.get("category", "全部"),
        request.args.get("status", "全部"),
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "物品编号", "物品名称", "类别", "房间", "具体位置",
        "数量", "最低库存", "购入日期", "有效期", "状态", "备注", "创建时间",
    ])
    for item in items:
        writer.writerow([
            item["id"], item["item_code"], item["name"], item["category"],
            item["room"], item["location"], item["quantity"], item["min_quantity"],
            item["purchase_date"], item["expiry_date"], item["status"],
            item["notes"], item["created_at"],
        ])
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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
