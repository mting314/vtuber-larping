import re
import sys

from sqlmodel import Session, select

from app.database import engine
from app.models import Summary

sys.stdout.reconfigure(encoding='utf-8')

def migrate_timestamps():
    print("=== Migrating DB Timestamps to Clickable Markdown Links ===")
    with Session(engine) as session:
        summaries = session.exec(select(Summary)).all()
        print(f"Found {len(summaries)} summaries to update.")
        
        count = 0
        for s in summaries:
            if not s.master_summary:
                continue
            
            # Replace [HH:MM:SS] or [MM:SS] with [⏱️ HH:MM:SS](#t=HH:MM:SS) if not already converted
            new_summary = re.sub(
                r'\[(?:⏱️\s*)?(\d{1,2}:\d{2}(?::\d{2})?)\](?!\(#t=)',
                r'[⏱️ \1](#t=\1)',
                s.master_summary
            )
            
            if new_summary != s.master_summary:
                s.master_summary = new_summary
                session.add(s)
                count += 1
                
        session.commit()
        print(f"✓ Updated {count} summaries with pre-rendered clickable timestamp links!")

if __name__ == "__main__":
    migrate_timestamps()
