import sqlite3
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Intentionally hardcoded secret — demonstrates CWE-798 for SAST findings
SECRET_KEY = "hardcoded-secret-123"
app.config["SECRET_KEY"] = SECRET_KEY

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "users.db"))


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)"
    )
    conn.execute("INSERT OR IGNORE INTO users (id, username, email) VALUES (1, 'alice', 'alice@example.com')")
    conn.execute("INSERT OR IGNORE INTO users (id, username, email) VALUES (2, 'bob', 'bob@example.com')")
    conn.commit()
    conn.close()


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/search")
def search():
    # Intentional SQL injection — demonstrates CWE-89 for SAST/DAST findings
    username = request.args.get("username", "")
    conn = sqlite3.connect(DB_PATH)
    query = f"SELECT id, username, email FROM users WHERE username = '{username}'"
    try:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        results = [{"id": r[0], "username": r[1], "email": r[2]} for r in rows]
    except sqlite3.OperationalError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()
    return jsonify({"results": results})


@app.route("/users")
def users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT id, username, email FROM users")
    rows = [{"id": r[0], "username": r[1], "email": r[2]} for r in cursor.fetchall()]
    conn.close()
    return jsonify({"users": rows})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
