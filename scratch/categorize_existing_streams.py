import sys

from sqlmodel import Session, select

from app.database import DB_FILE, engine, init_db
from app.models import Stream
from app.storage import storage_manager
from app.summarizer import infer_stream_category_from_title

sys.stdout.reconfigure(encoding='utf-8')


def categorize_existing_streams():
    print("Pulling current DB from GCS...")
    storage_manager.download_db(DB_FILE)
    init_db()

    with Session(engine) as session:
        streams = session.exec(select(Stream)).all()
        print(f"Categorizing {len(streams)} existing streams...")
        gaming_count = 0
        chatting_count = 0

        for stream in streams:
            category = infer_stream_category_from_title(stream.title)
            stream.stream_category = category
            session.add(stream)
            if category == "gaming":
                gaming_count += 1
            else:
                chatting_count += 1

        session.commit()
        print(f"✓ Categorized {len(streams)} streams: {chatting_count} Chatting, {gaming_count} Gaming.")

    print("Pushing updated DB back to GCS...")
    storage_manager.upload_db(DB_FILE)
    print("Done!")


if __name__ == "__main__":
    categorize_existing_streams()
