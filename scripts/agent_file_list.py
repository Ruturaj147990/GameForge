"""Helper script to list assigned files for each agent."""

import sys
from pathlib import Path
import sqlite3

DB_PATH = Path("docs/audit_ledger.db")

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/agent_file_list.py <agent_name>")
        sys.exit(1)
    
    agent = sys.argv[1]
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT path, status FROM files WHERE assigned_to = ? ORDER BY path", (agent,))
    rows = cur.fetchall()
    
    print(f"Total files assigned to {agent}: {len(rows)}")
    for path, status in rows:
        print(f"[{status:15s}] {path}")

if __name__ == "__main__":
    main()
