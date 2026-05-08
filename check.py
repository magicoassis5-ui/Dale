import asyncio, sqlite3, os

# Verifica banco diretamente
db_path = 'data/dale.db'
print("DB existe:", os.path.exists(db_path))
print("DB tamanho:", os.path.getsize(db_path) if os.path.exists(db_path) else 0, "bytes")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tabelas:", tables)
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
        print(f"  {t[0]}: {count} registros")
    conn.close()
else:
    print("Banco nao encontrado!")
