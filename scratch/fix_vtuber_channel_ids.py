import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from sqlmodel import Session, select
from app.database import engine
from app.models import VTuber, Stream

PRIMARY_MAP = [
    {"name": "Shiori Novella", "channel_id": "UCgnfPPb9JI3e9A4cXHnWbyg", "agency": "Hololive English", "aliases": ["Shiori Novella Ch. hololive-EN", "Shiori Novella Ch. hololive"]},
    {"name": "Kobo Kanaeru", "channel_id": "UCjLEmnpCNeisMxy134KPwWw", "agency": "Hololive ID", "aliases": []},
    {"name": "Nerissa Ravencroft", "channel_id": "UC_sFNM0z0MWm9A6WlKPuMMg", "agency": "Hololive English", "aliases": []},
    {"name": "Vestia Zeta", "channel_id": "UCTvHWSfBZgtxE4sILOaurIQ", "agency": "Hololive ID", "aliases": ["Zeta Vestia", "Vestia Zeta Ch. hololive-ID"]},
    {"name": "Gawr Gura", "channel_id": "UCoSrY_IQQVpmIRZ9Xf-y93g", "agency": "Hololive English", "aliases": []},
    {"name": "FUWAMOCO", "channel_id": "UCt9H_RpQzhxzlyBxFqrdHqA", "agency": "Hololive English", "aliases": ["FUWAMOCO Ch. hololive-EN"]},
    {"name": "Ironmouse", "channel_id": "UCj_TYZ60NDQYY5QpUvOge9g", "agency": "VShojo", "aliases": []},
]

def consolidate():
    with Session(engine) as session:
        # Create or update 7 primary VTubers
        primary_objs = {}
        for p in PRIMARY_MAP:
            v = session.exec(select(VTuber).where(VTuber.name == p["name"])).first()
            if not v:
                v = VTuber(name=p["name"], channel_id=p["channel_id"], agency=p["agency"])
                session.add(v)
                session.commit()
                session.refresh(v)
            else:
                v.channel_id = p["channel_id"]
                v.agency = p["agency"]
                session.add(v)
                session.commit()
                session.refresh(v)
            primary_objs[p["name"]] = v

        # Now find all other VTuber entries
        all_vtubers = session.exec(select(VTuber)).all()
        primary_ids = {v.id for v in primary_objs.values()}

        for v in all_vtubers:
            if v.id in primary_ids:
                continue
            
            # Find matching primary object
            target_primary = None
            for p in PRIMARY_MAP:
                if v.name == p["name"] or v.name in p["aliases"]:
                    target_primary = primary_objs[p["name"]]
                    break
            
            if target_primary:
                print(f"Merging VTuber row ID {v.id} ('{v.name}') into ID {target_primary.id} ('{target_primary.name}')...")
                streams = session.exec(select(Stream).where(Stream.vtuber_id == v.id)).all()
                for s in streams:
                    s.vtuber_id = target_primary.id
                    session.add(s)
                session.commit()
                session.delete(v)
                session.commit()
            else:
                # Remove unneeded VTuber rows if any
                session.delete(v)
                session.commit()

        print("\n✓ Clean VTuber List in DB:")
        final_list = session.exec(select(VTuber)).all()
        for v in final_list:
            print(f"ID: {v.id} | Name: {v.name} | Channel ID: {v.channel_id} | Agency: {v.agency}")

if __name__ == "__main__":
    consolidate()
