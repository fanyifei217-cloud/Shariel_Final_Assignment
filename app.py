from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path

import qrcode
from jinja2 import TemplateNotFound
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

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
    "衣物": "CLO", "书籍": "BOOK", "食品": "FOOD", "药品": "MED",
    "厨房用品": "KIT", "清洁用品": "CLE", "电子产品": "ELE",
    "工具": "TOOL", "证件资料": "DOC", "其他": "OTH",
}

STATUSES = ["正常使用", "闲置", "借出", "损坏", "已丢弃", "即将过期", "已过期"]


HOUSEHOLD_PERSONALIZATION = {
    "独居": {
        "badge": "一人生活",
        "title": "一个人的家，也可以井井有条",
        "subtitle": "重点管理日常消耗品、食品药品和个人物品，让独居生活更轻松。",
        "tips": [
            "优先设置食品和药品的有效期",
            "为纸巾、洗衣液等设置最低库存",
            "使用二维码快速定位储物柜和收纳箱",
        ],
        "recommended_categories": ["食品", "药品", "清洁用品", "证件资料"],
        "accent_class": "solo",
    },
    "情侣或已婚无子（两人）": {
        "badge": "双人生活",
        "title": "两个人的家，共享也要清清楚楚",
        "subtitle": "适合管理共同用品、个人物品和共享购物清单，减少重复购买。",
        "tips": [
            "将共同用品集中登记，避免重复购买",
            "把个人物品备注为所属成员",
            "使用购物清单同步家庭补货需求",
        ],
        "recommended_categories": ["厨房用品", "清洁用品", "电子产品", "衣物"],
        "accent_class": "couple",
    },
    "已婚有子（三人及以上）": {
        "badge": "家庭生活",
        "title": "全家的物品，各有各的位置",
        "subtitle": "适合管理儿童用品、家庭常备药、学习用品和大容量日用品。",
        "tips": [
            "为儿童用品和药品设置清晰位置",
            "常用消耗品设置最低库存提醒",
            "按房间和收纳箱生成二维码标签",
        ],
        "recommended_categories": ["药品", "食品", "书籍", "衣物"],
        "accent_class": "family",
    },
}

PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                phone TEXT UNIQUE,
                email TEXT UNIQUE,
                household_type TEXT NOT NULL DEFAULT '独居',
                children_count INTEGER NOT NULL DEFAULT 0,
                child_names TEXT NOT NULL DEFAULT '[]',
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                CHECK (phone IS NOT NULL OR email IS NOT NULL)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_code TEXT NOT NULL,
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
                child_name TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, item_code),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
        if "user_id" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN user_id INTEGER")
        if "min_quantity" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN min_quantity INTEGER NOT NULL DEFAULT 0")
        if "child_name" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN child_name TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shopping_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                source_item_id INTEGER,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        shopping_columns = {row["name"] for row in conn.execute("PRAGMA table_info(shopping_items)")}
        if "user_id" not in shopping_columns:
            conn.execute("ALTER TABLE shopping_items ADD COLUMN user_id INTEGER")

        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "household_type" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN household_type TEXT NOT NULL DEFAULT '独居'"
            )

        if "children_count" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN children_count INTEGER NOT NULL DEFAULT 0"
            )
        if "child_names" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN child_names TEXT NOT NULL DEFAULT '[]'"
            )



def ensure_latest_schema() -> None:
    """Repair columns required by newer versions without deleting existing data."""
    with get_connection() as conn:
        item_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(items)").fetchall()
        }
        if "user_id" not in item_columns:
            conn.execute("ALTER TABLE items ADD COLUMN user_id INTEGER")
        if "min_quantity" not in item_columns:
            conn.execute(
                "ALTER TABLE items ADD COLUMN min_quantity INTEGER NOT NULL DEFAULT 0"
            )
        if "child_name" not in item_columns:
            conn.execute("ALTER TABLE items ADD COLUMN child_name TEXT")

        user_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "household_type" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN household_type TEXT NOT NULL DEFAULT '独居'"
            )
        if "children_count" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN children_count INTEGER NOT NULL DEFAULT 0"
            )
        if "child_names" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN child_names TEXT NOT NULL DEFAULT '[]'"
            )

        shopping_columns = {
            row["name"] for row in conn.execute(
                "PRAGMA table_info(shopping_items)"
            ).fetchall()
        }
        if "user_id" not in shopping_columns:
            conn.execute("ALTER TABLE shopping_items ADD COLUMN user_id INTEGER")


@app.before_request
def repair_schema_before_request():
    ensure_latest_schema()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("请先登录后再使用系统。", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def current_user_id() -> int:
    return int(session["user_id"])


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
            "SELECT item_code FROM items WHERE user_id = ? AND item_code LIKE ?",
            (current_user_id(), f"{prefix}-%"),
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
        "child_name": form.get("child_name", "").strip(),
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
        rows = conn.execute(
            "SELECT id, expiry_date, status FROM items WHERE user_id = ?",
            (current_user_id(),),
        ).fetchall()
        for row in rows:
            new_status = normalize_status(row["expiry_date"] or "", row["status"])
            if new_status != row["status"]:
                conn.execute("UPDATE items SET status = ? WHERE id = ?", (new_status, row["id"]))


def sync_low_stock_to_shopping() -> int:
    created = 0
    uid = current_user_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, quantity, min_quantity
            FROM items
            WHERE user_id = ? AND min_quantity > 0 AND quantity <= min_quantity
            """,
            (uid,),
        ).fetchall()
        for row in rows:
            need = max(row["min_quantity"] - row["quantity"] + 1, 1)
            exists = conn.execute(
                """
                SELECT id FROM shopping_items
                WHERE user_id = ? AND name = ? AND completed = 0
                """,
                (uid, row["name"]),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO shopping_items
                    (user_id, name, quantity, source_item_id, completed, created_at)
                    VALUES (?, ?, ?, ?, 0, ?)
                    """,
                    (uid, row["name"], need, row["id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                created += 1
    return created


def query_items(keyword: str = "", category: str = "全部", status: str = "全部"):
    sql = "SELECT * FROM items WHERE user_id = ?"
    params: list = [current_user_id()]
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


def child_labels() -> list[str]:
    count = max(int(session.get("children_count", 0) or 0), 0)
    raw_names = session.get("child_names", [])
    if isinstance(raw_names, str):
        try:
            raw_names = json.loads(raw_names)
        except (TypeError, ValueError, json.JSONDecodeError):
            raw_names = []
    names = [str(name).strip() for name in raw_names if str(name).strip()]
    names = names[:count]
    while len(names) < count:
        names.append(f"儿童{len(names) + 1}")
    return names


def family_context() -> dict:
    return {
        "household_type": session.get("household_type", "独居"),
        "children_count": int(session.get("children_count", 0)),
        "child_labels": child_labels(),
    }


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        register_type = request.form.get("register_type", "phone")
        account = request.form.get("account", "").strip().lower()
        household_type = request.form.get("household_type", "独居").strip()
        children_count_raw = request.form.get("children_count", "0").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        phone = None
        email = None

        allowed_household_types = {
            "独居",
            "情侣或已婚无子（两人）",
            "已婚有子（三人及以上）",
        }

        try:
            children_count = int(children_count_raw or 0)
            if children_count < 0:
                raise ValueError
        except ValueError:
            children_count = -1

        if not all([display_name, account, household_type, password, confirm_password]):
            flash("请完整填写注册信息。", "error")
        elif household_type not in allowed_household_types:
            flash("请选择正确的居住成员情况。", "error")
        elif children_count < 0:
            flash("儿童数量必须是大于或等于0的整数。", "error")
        elif household_type == "已婚有子（三人及以上）" and children_count < 1:
            flash("选择“已婚有子”时，请填写至少1名儿童。", "error")
        elif household_type != "已婚有子（三人及以上）" and children_count != 0:
            children_count = 0
        elif register_type == "phone" and not PHONE_PATTERN.match(account):
            flash("请输入正确的11位中国大陆手机号。", "error")
        elif register_type == "email" and not EMAIL_PATTERN.match(account):
            flash("请输入正确的邮箱地址。", "error")
        elif len(password) < 6:
            flash("密码不能少于6位。", "error")
        elif password != confirm_password:
            flash("两次输入的密码不一致。", "error")
        else:
            if register_type == "phone":
                phone = account
            else:
                email = account

            try:
                with get_connection() as conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO users
                        (display_name, phone, email, household_type, children_count, child_names, password_hash, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            display_name,
                            phone,
                            email,
                            household_type,
                            children_count,
                            json.dumps([f"儿童{i}" for i in range(1, children_count + 1)], ensure_ascii=False),
                            generate_password_hash(password),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    )
                    user_id = cursor.lastrowid
                session["user_id"] = user_id
                session["display_name"] = display_name
                session["household_type"] = household_type
                session["children_count"] = children_count
                session["child_names"] = [f"儿童{i}" for i in range(1, children_count + 1)]
                flash("注册成功，欢迎使用家庭物品收纳管理系统。", "success")
                return redirect(url_for("index"))
            except sqlite3.IntegrityError:
                if register_type == "phone":
                    flash("该手机号已被注册。", "error")
                else:
                    flash("该邮箱已被注册。", "error")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        account = request.form.get("account", "").strip().lower()
        password = request.form.get("password", "")

        with get_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE phone = ? OR email = ?",
                (account, account),
            ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["display_name"] = user["display_name"]
            session["household_type"] = user["household_type"]
            session["children_count"] = user["children_count"]
            try:
                session["child_names"] = json.loads(user["child_names"] or "[]")
            except (TypeError, ValueError, json.JSONDecodeError, IndexError):
                session["child_names"] = []
            flash("登录成功。", "success")
            return redirect(url_for("index"))

        flash("手机号、邮箱或密码错误。", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("你已安全退出登录。", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    refresh_expiry_statuses()
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "全部")
    status = request.args.get("status", "全部")
    items = query_items(keyword, category, status)
    uid = current_user_id()

    with get_connection() as conn:
        record_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE user_id = ?", (uid,)
        ).fetchone()[0]
        quantity_total = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM items WHERE user_id = ?", (uid,)
        ).fetchone()[0]
        expiring_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE user_id = ? AND status = '即将过期'", (uid,)
        ).fetchone()[0]
        expired_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE user_id = ? AND status = '已过期'", (uid,)
        ).fetchone()[0]
        low_stock_count = conn.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE user_id = ? AND min_quantity > 0 AND quantity <= min_quantity
            """,
            (uid,),
        ).fetchone()[0]

    household_type = session.get("household_type", "独居")
    children_count = int(session.get("children_count", 0))
    personalization = HOUSEHOLD_PERSONALIZATION.get(
        household_type,
        HOUSEHOLD_PERSONALIZATION["独居"],
    )

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
        display_name=session.get("display_name", "用户"),
        household_type=household_type,
        children_count=children_count,
        personalization=personalization,
    )


@app.route("/generate-code")
@login_required
def generate_code():
    return {"code": next_item_code(request.args.get("category", "其他"))}


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_item():
    if request.method == "POST":
        data, error = validate_form(request.form)
        if error:
            flash(error, "error")
            return render_template("form.html", title="新增物品", item=data, categories=CATEGORIES, statuses=STATUSES, **family_context())
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO items (
                        user_id, item_code, name, category, room, location,
                        quantity, min_quantity, purchase_date, expiry_date,
                        status, notes, child_name, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_user_id(), data["item_code"], data["name"],
                        data["category"], data["room"], data["location"],
                        data["quantity"], data["min_quantity"], data["purchase_date"],
                        data["expiry_date"], data["status"], data["notes"],
                        data["child_name"] or None,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
            flash("物品信息已保存。", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("物品编号已存在，请更换编号。", "error")

    default_item = {
        "category": "其他",
        "item_code": next_item_code("其他"),
        "quantity": 1,
        "min_quantity": 0,
        "child_name": request.args.get("child", "").strip(),
    }
    return render_template("form.html", title="新增物品", item=default_item, categories=CATEGORIES, statuses=STATUSES, **family_context())


@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id: int):
    uid = current_user_id()
    with get_connection() as conn:
        item = conn.execute(
            "SELECT * FROM items WHERE id = ? AND user_id = ?",
            (item_id, uid),
        ).fetchone()
    if item is None:
        flash("未找到该物品记录。", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        data, error = validate_form(request.form)
        if error:
            flash(error, "error")
            return render_template("form.html", title="修改物品", item=data, categories=CATEGORIES, statuses=STATUSES, **family_context())
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE items SET item_code=?, name=?, category=?, room=?,
                        location=?, quantity=?, min_quantity=?, purchase_date=?,
                        expiry_date=?, status=?, notes=?, child_name=?
                    WHERE id=? AND user_id=?
                    """,
                    (
                        data["item_code"], data["name"], data["category"],
                        data["room"], data["location"], data["quantity"],
                        data["min_quantity"], data["purchase_date"],
                        data["expiry_date"], data["status"], data["notes"],
                        data["child_name"] or None,
                        item_id, uid,
                    ),
                )
            flash("物品信息已更新。", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("物品编号已存在，请更换编号。", "error")

    return render_template("form.html", title="修改物品", item=dict(item), categories=CATEGORIES, statuses=STATUSES, **family_context())


@app.post("/delete/<int:item_id>")
@login_required
def delete_item(item_id: int):
    uid = current_user_id()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM shopping_items WHERE source_item_id = ? AND user_id = ?",
            (item_id, uid),
        )
        conn.execute(
            "DELETE FROM items WHERE id = ? AND user_id = ?",
            (item_id, uid),
        )
    flash("物品记录已删除。", "success")
    return redirect(url_for("index"))


@app.route("/reminders")
@login_required
def reminders():
    refresh_expiry_statuses()
    uid = current_user_id()
    with get_connection() as conn:
        expiring = conn.execute(
            "SELECT * FROM items WHERE user_id = ? AND status = '即将过期' ORDER BY expiry_date",
            (uid,),
        ).fetchall()
        expired = conn.execute(
            "SELECT * FROM items WHERE user_id = ? AND status = '已过期' ORDER BY expiry_date",
            (uid,),
        ).fetchall()
        low_stock = conn.execute(
            """
            SELECT * FROM items
            WHERE user_id = ? AND min_quantity > 0 AND quantity <= min_quantity
            ORDER BY quantity ASC
            """,
            (uid,),
        ).fetchall()
    return render_template("reminders.html", expiring=expiring, expired=expired, low_stock=low_stock)


@app.post("/shopping/sync")
@login_required
def shopping_sync():
    created = sync_low_stock_to_shopping()
    flash(f"已将 {created} 个低库存物品加入购物清单。", "success")
    return redirect(url_for("shopping_list"))


@app.route("/shopping", methods=["GET", "POST"])
@login_required
def shopping_list():
    uid = current_user_id()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            quantity = max(int(request.form.get("quantity", "1")), 1)
        except ValueError:
            quantity = 1
        if not name:
            flash("请输入需要购买的物品名称。", "error")
        else:
            with get_connection() as conn:
                exists = conn.execute(
                    """
                    SELECT id FROM shopping_items
                    WHERE user_id = ? AND name = ? AND completed = 0
                    """,
                    (uid, name),
                ).fetchone()
                if exists:
                    flash("该物品已在未完成的购物清单中。", "error")
                else:
                    conn.execute(
                        """
                        INSERT INTO shopping_items
                        (user_id, name, quantity, completed, created_at)
                        VALUES (?, ?, ?, 0, ?)
                        """,
                        (uid, name, quantity, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    )
                    flash("已加入购物清单。", "success")
        return redirect(url_for("shopping_list"))

    with get_connection() as conn:
        active = conn.execute(
            "SELECT * FROM shopping_items WHERE user_id = ? AND completed = 0 ORDER BY id DESC",
            (uid,),
        ).fetchall()
        completed = conn.execute(
            """
            SELECT * FROM shopping_items
            WHERE user_id = ? AND completed = 1
            ORDER BY id DESC LIMIT 20
            """,
            (uid,),
        ).fetchall()
    return render_template("shopping.html", active=active, completed=completed)


@app.post("/shopping/toggle/<int:shopping_id>")
@login_required
def shopping_toggle(shopping_id: int):
    uid = current_user_id()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT completed FROM shopping_items WHERE id = ? AND user_id = ?",
            (shopping_id, uid),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE shopping_items SET completed = ? WHERE id = ? AND user_id = ?",
                (0 if row["completed"] else 1, shopping_id, uid),
            )
    return redirect(url_for("shopping_list"))


@app.post("/shopping/delete/<int:shopping_id>")
@login_required
def shopping_delete(shopping_id: int):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM shopping_items WHERE id = ? AND user_id = ?",
            (shopping_id, current_user_id()),
        )
    return redirect(url_for("shopping_list"))


@app.route("/children", methods=["GET", "POST"])
@login_required
def children_storage():
    if session.get("household_type") != "已婚有子（三人及以上）":
        flash("儿童收纳页面仅对已婚有子家庭开放。", "error")
        return redirect(url_for("index"))

    uid = current_user_id()
    with get_connection() as conn:
        user = conn.execute(
            "SELECT children_count, child_names FROM users WHERE id = ?", (uid,)
        ).fetchone()

        count = max(int((user["children_count"] if user else 0) or 0), 1)
        try:
            saved_names = json.loads((user["child_names"] if user else "[]") or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            saved_names = []

        names = [str(name).strip() for name in saved_names if str(name).strip()][:count]
        while len(names) < count:
            names.append(f"儿童{len(names) + 1}")

        if request.method == "POST":
            action = request.form.get("action", "save_names")
            if action == "add_child":
                count += 1
                names.append(f"儿童{count}")
            elif action == "remove_child" and count > 1:
                removed_name = names[-1]
                assigned = conn.execute(
                    "SELECT COUNT(*) FROM items WHERE user_id = ? AND child_name = ?",
                    (uid, removed_name),
                ).fetchone()[0]
                if assigned:
                    flash(f"{removed_name} 仍有物品，请先将物品重新分配后再删除。", "error")
                    return redirect(url_for("children_storage"))
                count -= 1
                names = names[:count]
            else:
                submitted = request.form.getlist("child_name")
                cleaned = []
                for index in range(count):
                    value = submitted[index].strip() if index < len(submitted) else ""
                    cleaned.append(value or f"儿童{index + 1}")
                if len(set(cleaned)) != len(cleaned):
                    flash("儿童昵称不能重复。", "error")
                    return redirect(url_for("children_storage"))
                # Update item assignments when a child is renamed.
                for old_name, new_name in zip(names, cleaned):
                    if old_name != new_name:
                        conn.execute(
                            "UPDATE items SET child_name = ? WHERE user_id = ? AND child_name = ?",
                            (new_name, uid, old_name),
                        )
                names = cleaned

            conn.execute(
                "UPDATE users SET children_count = ?, child_names = ? WHERE id = ?",
                (count, json.dumps(names, ensure_ascii=False), uid),
            )
            session["children_count"] = count
            session["child_names"] = names
            flash("儿童收纳设置已保存。", "success")
            return redirect(url_for("children_storage"))

        child_groups = []
        for label in names:
            rows = conn.execute(
                """
                SELECT * FROM items
                WHERE user_id = ? AND COALESCE(child_name, '') = ?
                ORDER BY category, name
                """,
                (uid, label),
            ).fetchall()
            child_groups.append({
                "name": label,
                "items": rows,
                "count": len(rows),
                "quantity": sum(int(row["quantity"] or 0) for row in rows),
            })

        unassigned = conn.execute(
            """
            SELECT * FROM items
            WHERE user_id = ? AND COALESCE(child_name, '') = ''
            ORDER BY category, name
            """,
            (uid,),
        ).fetchall()

    session["children_count"] = count
    session["child_names"] = names
    return render_template(
        "children.html",
        child_groups=child_groups,
        unassigned=unassigned,
        children_count=count,
    )


@app.route("/locations")
@login_required
def locations():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT room, location, COUNT(*) AS item_count, SUM(quantity) AS quantity_total
            FROM items
            WHERE user_id = ?
            GROUP BY room, location
            ORDER BY room, location
            """,
            (current_user_id(),),
        ).fetchall()
    return render_template("locations.html", locations=rows)


@app.route("/location")
@login_required
def location_detail():
    room = request.args.get("room", "")
    location = request.args.get("location", "")
    with get_connection() as conn:
        items = conn.execute(
            """
            SELECT * FROM items
            WHERE user_id = ? AND room = ? AND location = ?
            ORDER BY name
            """,
            (current_user_id(), room, location),
        ).fetchall()
    return render_template("location_detail.html", room=room, location=location, items=items)


@app.route("/location-qr")
@login_required
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
@login_required
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


@app.errorhandler(500)
def internal_error(error):
    app.logger.exception("Internal server error: %s", error)
    return render_template("500.html"), 500


@app.route("/diagnostic")
@login_required
def diagnostic():
    ensure_latest_schema()
    with get_connection() as conn:
        item_columns = [
            row["name"] for row in conn.execute("PRAGMA table_info(items)").fetchall()
        ]
        user_columns = [
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        ]
    return {
        "status": "ok",
        "user_id": current_user_id(),
        "household_type": session.get("household_type"),
        "children_count": session.get("children_count"),
        "items_columns": item_columns,
        "users_columns": user_columns,
    }


@app.route("/health")
def health():
    return {"status": "ok"}


init_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
