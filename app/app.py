import os
import socket
import threading
import time

from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

APP_VERSION = os.getenv("APP_VERSION", "v1")
HOSTNAME = socket.gethostname()

# If DB_HOST is set, use PostgreSQL. Otherwise keep tasks in memory.
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME", "tasks")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
USE_DB = bool(DB_HOST)

app = Flask(__name__)

# Prometheus metrics
REQUESTS = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency in seconds", ["endpoint"])
TASKS = Gauge("tasks_count", "Number of tasks stored")

state = {"healthy": True, "table_ready": False}
memory_tasks = []
memory_lock = threading.Lock()


def db_run(sql, params=(), fetch=False):
    import psycopg2

    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER,
                            password=DB_PASSWORD, connect_timeout=3)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if fetch else None
    finally:
        conn.close()


def ensure_table():
    if not state["table_ready"]:
        db_run("CREATE TABLE IF NOT EXISTS tasks ("
               "id SERIAL PRIMARY KEY, title TEXT NOT NULL, done BOOLEAN NOT NULL DEFAULT FALSE)")
        state["table_ready"] = True


@app.before_request
def start_timer():
    g.start = time.perf_counter()


@app.after_request
def record_metrics(response):
    endpoint = request.url_rule.rule if request.url_rule else "unknown"
    if endpoint != "/metrics":
        REQUESTS.labels(request.method, endpoint, str(response.status_code)).inc()
        LATENCY.labels(endpoint).observe(time.perf_counter() - g.get("start", time.perf_counter()))
    return response


@app.route("/")
def index():
    return jsonify(app="task-api", version=APP_VERSION, pod=HOSTNAME,
                   storage="postgres" if USE_DB else "memory")


@app.route("/tasks", methods=["GET"])
def list_tasks():
    if USE_DB:
        ensure_table()
        rows = db_run("SELECT id, title, done FROM tasks ORDER BY id", fetch=True)
        tasks = [{"id": r[0], "title": r[1], "done": r[2]} for r in rows]
    else:
        with memory_lock:
            tasks = list(memory_tasks)
    TASKS.set(len(tasks))
    return jsonify(tasks)


@app.route("/tasks", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400
    if USE_DB:
        ensure_table()
        row = db_run("INSERT INTO tasks (title) VALUES (%s) RETURNING id", (title,), fetch=True)[0]
        task = {"id": row[0], "title": title, "done": False}
    else:
        with memory_lock:
            task = {"id": len(memory_tasks) + 1, "title": title, "done": False}
            memory_tasks.append(task)
    TASKS.inc()
    return jsonify(task), 201


@app.route("/healthz")
def healthz():
    if state["healthy"]:
        return jsonify(status="ok")
    return jsonify(status="broken"), 500


@app.route("/readyz")
def readyz():
    if USE_DB:
        try:
            db_run("SELECT 1")
        except Exception as exc:
            return jsonify(status="not ready", reason=str(exc)), 503
    return jsonify(status="ready")


@app.route("/admin/break", methods=["POST"])
def break_app():
    state["healthy"] = False
    return jsonify(status="liveness check will now fail")


@app.route("/work")
def work():
    ms = min(max(request.args.get("ms", 100, type=int), 0), 2000)
    end = time.perf_counter() + ms / 1000
    count = 0
    while time.perf_counter() < end:
        count += 1
    return jsonify(burned_ms=ms, pod=HOSTNAME)


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
