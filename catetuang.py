"""
CatetUang - Personal Finance Tracker
Stack: Flask + SQLite + Bootstrap 5
"""

import os
import sqlite3
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "catetuang-secret-key-2026")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keuangan.db")

# ── Kategori default ──
KATEGORI_PENGELUARAN = [
    "Makan & Minum", "Transport", "Belanja", "Tagihan", "Hiburan",
    "Kesehatan", "Pendidikan", "Pakaian", "Lainnya"
]
KATEGORI_PENDAPATAN = [
    "Gaji", "Bonus", "Investasi", "Freelance", "Hadiah", "Lainnya"
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT NOT NULL,
            tipe TEXT NOT NULL CHECK(tipe IN ('pemasukan', 'pengeluaran')),
            kategori TEXT NOT NULL,
            jumlah REAL NOT NULL,
            keterangan TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_tanggal ON transaksi(tanggal);
        CREATE INDEX IF NOT EXISTS idx_tipe ON transaksi(tipe);
    """)
    conn.commit()
    conn.close()


# ── Helper: format rupiah ──
@app.template_filter("rupiah")
def format_rupiah(value):
    try:
        return f"Rp {value:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"


# ── Routes ──

@app.route("/")
def index():
    conn = get_db()
    bulan = request.args.get("bulan", date.today().strftime("%Y-%m"))

    # Summary bulan ini
    row = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN tipe='pemasukan' THEN jumlah ELSE 0 END), 0) as total_masuk,
            COALESCE(SUM(CASE WHEN tipe='pengeluaran' THEN jumlah ELSE 0 END), 0) as total_keluar,
            COUNT(*) as total_transaksi
        FROM transaksi
        WHERE strftime('%Y-%m', tanggal) = ?
    """, (bulan,)).fetchone()

    saldo = conn.execute("""
        SELECT COALESCE(SUM(CASE WHEN tipe='pemasukan' THEN jumlah ELSE -jumlah END), 0)
        FROM transaksi
    """).fetchone()[0]

    # Top 5 pengeluaran by kategori
    top_kategori = conn.execute("""
        SELECT kategori, SUM(jumlah) as total
        FROM transaksi
        WHERE tipe='pengeluaran' AND strftime('%Y-%m', tanggal) = ?
        GROUP BY kategori
        ORDER BY total DESC
        LIMIT 5
    """, (bulan,)).fetchall()

    # 10 transaksi terakhir
    transaksi = conn.execute("""
        SELECT * FROM transaksi
        WHERE strftime('%Y-%m', tanggal) = ?
        ORDER BY tanggal DESC, id DESC
        LIMIT 10
    """, (bulan,)).fetchall()

    # Data chart 6 bulan terakhir
    chart_data = conn.execute("""
        SELECT
            strftime('%Y-%m', tanggal) as bulan,
            SUM(CASE WHEN tipe='pemasukan' THEN jumlah ELSE 0 END) as pemasukan,
            SUM(CASE WHEN tipe='pengeluaran' THEN jumlah ELSE 0 END) as pengeluaran
        FROM transaksi
        WHERE tanggal >= date('now', '-6 months', 'start of month')
        GROUP BY strftime('%Y-%m', tanggal)
        ORDER BY bulan
    """).fetchall()

    conn.close()

    return render_template("index.html",
        summary={"masuk": row["total_masuk"], "keluar": row["total_keluar"],
                 "transaksi": row["total_transaksi"], "saldo": saldo},
        top_kategori=top_kategori,
        transaksi=transaksi,
        chart_data=[dict(r) for r in chart_data],
        bulan=bulan,
        kategori_pengeluaran=KATEGORI_PENGELUARAN,
        kategori_pendapatan=KATEGORI_PENDAPATAN,
        today=date.today().isoformat()
    )


@app.route("/tambah", methods=["POST"])
def tambah():
    tanggal = request.form.get("tanggal", date.today().isoformat())
    tipe = request.form.get("tipe", "pengeluaran")
    kategori = request.form.get("kategori", "Lainnya")
    jumlah = float(request.form.get("jumlah", 0))
    keterangan = request.form.get("keterangan", "")

    if jumlah <= 0:
        flash("Jumlah harus lebih dari 0!", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    conn.execute("INSERT INTO transaksi (tanggal, tipe, kategori, jumlah, keterangan) VALUES (?, ?, ?, ?, ?)",
                 (tanggal, tipe, kategori, jumlah, keterangan))
    conn.commit()
    conn.close()

    flash(f"Transaksi berhasil ditambahkan!", "success")
    return redirect(url_for("index", bulan=tanggal[:7]))


@app.route("/hapus/<int:id>", methods=["POST"])
def hapus(id):
    conn = get_db()
    conn.execute("DELETE FROM transaksi WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Transaksi dihapus.", "warning")
    return redirect(url_for("index"))


@app.route("/riwayat")
def riwayat():
    conn = get_db()
    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page

    total = conn.execute("SELECT COUNT(*) FROM transaksi").fetchone()[0]
    rows = conn.execute("""
        SELECT * FROM transaksi ORDER BY tanggal DESC, id DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    conn.close()

    return render_template("riwayat.html",
        transaksi=rows, page=page,
        total_pages=max(1, (total + per_page - 1) // per_page),
        total=total
    )


@app.route("/api/chart-data")
def api_chart_data():
    conn = get_db()
    data = conn.execute("""
        SELECT
            strftime('%Y-%m', tanggal) as bulan,
            SUM(CASE WHEN tipe='pemasukan' THEN jumlah ELSE 0 END) as pemasukan,
            SUM(CASE WHEN tipe='pengeluaran' THEN jumlah ELSE 0 END) as pengeluaran
        FROM transaksi
        GROUP BY strftime('%Y-%m', tanggal)
        ORDER BY bulan DESC
        LIMIT 12
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in data])


# ── Init & Run ──
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
