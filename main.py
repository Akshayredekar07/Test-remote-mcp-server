from fastmcp import FastMCP
import os
import aiosqlite
import tempfile
import json

TEMP_DIR = tempfile.gettempdir()
DB_PATH = os.path.join(TEMP_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("ExpenseTrackerRemote")

def init_db():
    import sqlite3
    with sqlite3.connect(DB_PATH) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)
        c.execute("INSERT OR IGNORE INTO expenses(date, amount, category) VALUES ('2000-01-01', 0, 'test')")
        c.execute("DELETE FROM expenses WHERE category = 'test'")

init_db()

@mcp.tool()
async def add_expense(date, amount, category, subcategory="", note=""):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, amount, category, subcategory, note)
            )
            expense_id = cur.lastrowid
            await c.commit()
            return {"status": "success", "id": expense_id}
    except Exception as e:
        if "readonly" in str(e).lower():
            return {"status": "error", "message": "Database is read-only"}
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def list_expenses(start_date, end_date):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                """,
                (start_date, end_date)
            )
            cols = [d[0] for d in cur.description]
            rows = await cur.fetchall()
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def summarize(start_date, end_date, category=None):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            query = """
                SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                FROM expenses
                WHERE date BETWEEN ? AND ?
            """
            params = [start_date, end_date]
            if category:
                query += " AND category = ?"
                params.append(category)
            query += " GROUP BY category ORDER BY total_amount DESC"
            cur = await c.execute(query, params)
            cols = [d[0] for d in cur.description]
            rows = await cur.fetchall()
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def get_expense(expense_id):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "SELECT id, date, amount, category, subcategory, note FROM expenses WHERE id = ?",
                (expense_id,)
            )
            row = await cur.fetchone()
            if not row:
                return {"status": "error", "message": f"Expense ID {expense_id} not found"}
            cols = [d[0] for d in cur.description]
            return {"status": "success", "expense": dict(zip(cols, row))}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def edit_expense(expense_id, date=None, amount=None, category=None, subcategory=None, note=None):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            fields, params = [], []
            if date is not None:
                fields.append("date = ?")
                params.append(date)
            if amount is not None:
                fields.append("amount = ?")
                params.append(amount)
            if category is not None:
                fields.append("category = ?")
                params.append(category)
            if subcategory is not None:
                fields.append("subcategory = ?")
                params.append(subcategory)
            if note is not None:
                fields.append("note = ?")
                params.append(note)
            if not fields:
                return {"status": "error", "message": "No fields to update"}
            params.append(expense_id)
            query = f"UPDATE expenses SET {', '.join(fields)} WHERE id = ?"
            cur = await c.execute(query, params)
            await c.commit()
            if cur.rowcount == 0:
                return {"status": "error", "message": f"Expense ID {expense_id} not found"}
            return {"status": "success", "updated_id": expense_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def delete_expense(expense_id):
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            await c.commit()
            if cur.rowcount == 0:
                return {"status": "error", "message": f"Expense ID {expense_id} not found"}
            return {"status": "success", "deleted_id": expense_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    try:
        if os.path.exists(CATEGORIES_PATH):
            with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
                return f.read()
        default = {
            "categories": [
                "Food & Dining",
                "Transportation",
                "Shopping",
                "Entertainment",
                "Bills & Utilities",
                "Healthcare",
                "Travel",
                "Education",
                "Business",
                "Other"
            ]
        }
        return json.dumps(default, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
