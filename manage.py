#!/usr/bin/env python3
"""
manage.py — CLI para gestionar categorías, direcciones y logs del watcher
"""

import os
import sys
import sqlite3
import argparse

DB_PATH = os.getenv("DB_PATH", "/data/watcher.db")

R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"
B = "\033[94m"; C = "\033[96m"; W = "\033[97m"; E = "\033[0m"
DIM = "\033[2m"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hr(char="─", width=80):
    print(char * width)

# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORÍAS
# ══════════════════════════════════════════════════════════════════════════════

def cat_add(args):
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO categories (name, webhook_url, webhook_secret, description)
                VALUES (?, ?, ?, ?)
            """, (args.name, args.webhook, args.secret or "", args.desc or ""))
        print(f"{G}✅ Categoría creada:{E} {W}{args.name}{E}")
        print(f"   Webhook : {args.webhook}")
    except sqlite3.IntegrityError:
        print(f"{Y}⚠️  Ya existe una categoría con ese nombre{E}")


def cat_edit(args):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM categories WHERE name = ?", (args.name,)
        ).fetchone()
        if not row:
            print(f"{R}No se encontró la categoría '{args.name}'{E}"); return

        new_webhook = args.webhook or row["webhook_url"]
        new_secret  = args.secret  if args.secret is not None else row["webhook_secret"]
        new_desc    = args.desc    or row["description"]

        conn.execute("""
            UPDATE categories
            SET webhook_url = ?, webhook_secret = ?, description = ?
            WHERE name = ?
        """, (new_webhook, new_secret, new_desc, args.name))
    print(f"{G}✅ Categoría '{args.name}' actualizada{E}")


def cat_remove(args):
    with get_db() as conn:
        # Verificar si tiene direcciones asignadas
        n = conn.execute(
            "SELECT COUNT(*) FROM addresses WHERE category_id = "
            "(SELECT id FROM categories WHERE name = ?)", (args.name,)
        ).fetchone()[0]
        if n and not args.force:
            print(f"{Y}⚠️  Esta categoría tiene {n} dirección(es) asignada(s).{E}")
            print(f"   Usa --force para eliminarla de todas formas "
                  f"(las dirs quedarán sin categoría).")
            return
        r = conn.execute("DELETE FROM categories WHERE name = ?", (args.name,))
    if r.rowcount:
        print(f"{R}🗑  Categoría eliminada:{E} {args.name}")
    else:
        print(f"{Y}No se encontró la categoría{E}")


def cat_list(args):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.*, COUNT(a.id) AS addr_count
            FROM categories c
            LEFT JOIN addresses a ON a.category_id = c.id AND a.active = 1
            GROUP BY c.id
            ORDER BY c.name
        """).fetchall()

    if not rows:
        print(f"{Y}No hay categorías registradas{E}")
        print(f"  Crea una con: manage.py category add <nombre> <webhook_url>")
        return

    print(f"\n{B}{'Nombre':<20} {'Dirs activas':<14} {'Webhook URL':<45} {'Desc'}{E}")
    hr()
    for r in rows:
        state = f"{G}●{E}" if r["active"] else f"{R}○{E}"
        wh = r["webhook_url"]
        wh_short = wh[:42] + "…" if len(wh) > 45 else wh
        secret_mark = f" {DIM}[🔑]{E}" if r["webhook_secret"] else ""
        print(f"{state} {r['name']:<19} {r['addr_count']:<14} {wh_short:<45} "
              f"{r['description'] or ''}{secret_mark}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  DIRECCIONES
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_category(conn, cat_name: str):
    """Devuelve category_id o None. Aborta si el nombre no existe."""
    if not cat_name:
        return None
    row = conn.execute(
        "SELECT id FROM categories WHERE name = ?", (cat_name,)
    ).fetchone()
    if not row:
        print(f"{R}Error: categoría '{cat_name}' no existe.{E}")
        print(f"  Categorías disponibles:")
        for r in conn.execute("SELECT name FROM categories ORDER BY name"):
            print(f"    • {r['name']}")
        sys.exit(1)
    return row["id"]


def addr_add(args):
    with get_db() as conn:
        cat_id = _resolve_category(conn, args.category)
        try:
            conn.execute("""
                INSERT INTO addresses (address, label, category_id)
                VALUES (?, ?, ?)
            """, (args.address, args.label or "", cat_id))
        except sqlite3.IntegrityError:
            print(f"{Y}⚠️  La dirección ya existe{E}"); return

    cat_info = f" (cat: {W}{args.category}{E})" if args.category else f" {DIM}(sin categoría){E}"
    print(f"{G}✅ Dirección agregada:{E} {args.address}{cat_info}")


def addr_edit(args):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM addresses WHERE address = ?", (args.address,)
        ).fetchone()
        if not row:
            print(f"{R}Dirección no encontrada{E}"); return

        cat_id = _resolve_category(conn, args.category) if args.category else row["category_id"]
        label  = args.label if args.label is not None else row["label"]

        conn.execute("""
            UPDATE addresses SET label = ?, category_id = ? WHERE address = ?
        """, (label, cat_id, args.address))
    print(f"{G}✅ Dirección actualizada:{E} {args.address}")


def addr_remove(args):
    with get_db() as conn:
        r = conn.execute("DELETE FROM addresses WHERE address = ?", (args.address,))
    if r.rowcount:
        print(f"{R}🗑  Dirección eliminada:{E} {args.address}")
    else:
        print(f"{Y}No se encontró la dirección{E}")


def addr_toggle(args, active: int):
    with get_db() as conn:
        conn.execute("UPDATE addresses SET active = ? WHERE address = ?",
                     (active, args.address))
    state = f"{G}activada{E}" if active else f"{Y}desactivada{E}"
    print(f"Dirección {state}: {args.address}")


def addr_list(args):
    where = ""
    params = []
    if args.category:
        where = "WHERE c.name = ?"
        params = [args.category]

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT a.address, a.label, a.active, a.last_match,
                   c.name AS category_name
            FROM addresses a
            LEFT JOIN categories c ON c.id = a.category_id
            {where}
            ORDER BY c.name, a.address
        """, params).fetchall()

    if not rows:
        print(f"{Y}No hay direcciones{' en esta categoría' if args.category else ''}{E}")
        return

    print(f"\n{B}{'St':<4} {'Address':<36} {'Category':<20} {'Label':<18} {'Last match'}{E}")
    hr()
    current_cat = None
    for r in rows:
        cat = r["category_name"] or f"{DIM}sin_categoria{E}"
        if cat != current_cat:
            print(f"\n  {C}▸ {cat}{E}")
            current_cat = cat
        state = f"{G}●{E}" if r["active"] else f"{R}○{E}"
        lm = r["last_match"] or "nunca"
        print(f"  {state}  {r['address']:<36} {'':<20} {(r['label'] or ''):<18} {lm}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  LOGS & STATS
# ══════════════════════════════════════════════════════════════════════════════

def cmd_txs(args):
    where = ""
    params = [args.limit]
    if args.category:
        where = "WHERE wl.category_name = ?"
        params = [args.category, args.limit]

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT s.detected_at, s.address, s.notified, s.retries,
                   c.name AS category_name,
                   w.status_code, w.sent_at
            FROM seen_txs s
            LEFT JOIN addresses a ON a.address = s.address
            LEFT JOIN categories c ON c.id = a.category_id
            LEFT JOIN webhook_log w ON w.txid = s.txid AND w.address = s.address
            ORDER BY s.detected_at DESC
            LIMIT ?
        """, (args.limit,) if not args.category else (args.category, args.limit)).fetchall()

    # fallback simple si el join falla
    if not rows:
        print(f"{Y}Sin transacciones registradas{E}"); return

    print(f"\n{B}{'Detected':<20} {'Address':<18} {'Category':<18} {'OK':<5} {'HTTP'}{E}")
    hr()
    for r in rows:
        notif = f"{G}✓{E}" if r["notified"] else f"{R}✗{E}"
        addr = (r["address"] or "")[:16] + "…"
        cat  = (r["category_name"] or "—")[:16]
        print(f"{r['detected_at']:<20} {addr:<18} {cat:<18} {notif}    "
              f"{r['status_code'] or '-'}")
    print()


def cmd_stats(args):
    with get_db() as conn:
        total_addr  = conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0]
        active_addr = conn.execute("SELECT COUNT(*) FROM addresses WHERE active=1").fetchone()[0]
        total_cat   = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        total_txs   = conn.execute("SELECT COUNT(*) FROM seen_txs").fetchone()[0]
        notified    = conn.execute("SELECT COUNT(*) FROM seen_txs WHERE notified=1").fetchone()[0]
        failed      = conn.execute("SELECT COUNT(*) FROM seen_txs WHERE notified=0").fetchone()[0]

        # TXs por categoría
        by_cat = conn.execute("""
            SELECT c.name, COUNT(s.txid) AS cnt
            FROM seen_txs s
            LEFT JOIN addresses a ON a.address = s.address
            LEFT JOIN categories c ON c.id = a.category_id
            GROUP BY c.name
            ORDER BY cnt DESC
        """).fetchall()

    print(f"""
{C}╔══════════════════════════════════╗
║   Mempool Watcher — Estadísticas ║
╚══════════════════════════════════╝{E}
  Categorías              : {W}{total_cat}{E}
  Direcciones totales     : {W}{total_addr}{E}
  Direcciones activas     : {G}{active_addr}{E}
  TXs detectadas          : {W}{total_txs}{E}
  Webhooks OK             : {G}{notified}{E}
  Pendientes / fallidos   : {R}{failed}{E}
""")
    if by_cat:
        print(f"  {B}TXs por categoría:{E}")
        for r in by_cat:
            cat = r["name"] or "sin_categoria"
            print(f"    {cat:<22} {r['cnt']}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  ARGPARSE
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Mempool Watcher — Gestión de categorías, direcciones y logs",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = ap.add_subparsers(dest="group", required=True)

    # ── category ──────────────────────────────────────────────────────────────
    cat_p = sub.add_parser("category", aliases=["cat"],
                           help="Gestionar categorías de webhook")
    cat_sub = cat_p.add_subparsers(dest="cmd", required=True)

    p = cat_sub.add_parser("add", help="Crear categoría")
    p.add_argument("name",    help="Nombre de la categoría (ej: 'tienda', 'donaciones')")
    p.add_argument("webhook", help="URL del webhook para esta categoría")
    p.add_argument("--secret", help="Secreto HMAC (opcional)")
    p.add_argument("--desc",   help="Descripción")

    p = cat_sub.add_parser("edit", help="Editar categoría existente")
    p.add_argument("name")
    p.add_argument("--webhook", help="Nueva URL de webhook")
    p.add_argument("--secret",  help="Nuevo secreto (usa '' para borrar)")
    p.add_argument("--desc",    help="Nueva descripción")

    p = cat_sub.add_parser("remove", help="Eliminar categoría")
    p.add_argument("name")
    p.add_argument("--force", action="store_true")

    cat_sub.add_parser("list", help="Listar todas las categorías")

    # ── address ───────────────────────────────────────────────────────────────
    addr_p = sub.add_parser("address", aliases=["addr"],
                            help="Gestionar direcciones Bitcoin")
    addr_sub = addr_p.add_subparsers(dest="cmd", required=True)

    p = addr_sub.add_parser("add", help="Agregar dirección")
    p.add_argument("address")
    p.add_argument("--category", "-c", help="Nombre de la categoría")
    p.add_argument("--label",    "-l", help="Etiqueta descriptiva")

    p = addr_sub.add_parser("edit", help="Editar dirección (cambiar categoría / label)")
    p.add_argument("address")
    p.add_argument("--category", "-c")
    p.add_argument("--label",    "-l")

    p = addr_sub.add_parser("remove", help="Eliminar dirección")
    p.add_argument("address")

    p = addr_sub.add_parser("enable",  help="Activar dirección")
    p.add_argument("address")
    p = addr_sub.add_parser("disable", help="Desactivar dirección")
    p.add_argument("address")

    p = addr_sub.add_parser("list", help="Listar direcciones")
    p.add_argument("--category", "-c", help="Filtrar por categoría")

    # ── txs / stats ───────────────────────────────────────────────────────────
    p = sub.add_parser("txs", help="Ver transacciones detectadas")
    p.add_argument("--limit",    type=int, default=20)
    p.add_argument("--category", "-c")

    sub.add_parser("stats", help="Estadísticas generales")

    args = ap.parse_args()

    group = args.group if args.group not in ("cat",)  else "category"
    group = group      if args.group not in ("addr",) else "address"

    if group == "category":
        {"add": cat_add, "edit": cat_edit, "remove": cat_remove, "list": cat_list}[args.cmd](args)
    elif group == "address":
        {
            "add": addr_add, "edit": addr_edit, "remove": addr_remove,
            "enable": lambda a: addr_toggle(a, 1),
            "disable": lambda a: addr_toggle(a, 0),
            "list": addr_list,
        }[args.cmd](args)
    elif args.group == "txs":
        cmd_txs(args)
    elif args.group == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
