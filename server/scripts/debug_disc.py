"""Diagnostic script to debug multi-title approval issue."""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from boz_server.database.models import DiscORM, JobORM, TitleORM


async def debug_disc(disc_name_pattern: str = "OFFICE"):
    """Query database for disc info and related jobs."""
    # Use the default database path
    db_path = Path(__file__).parent.parent / "data" / "boz.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Find disc matching pattern
        result = await session.execute(
            select(DiscORM).where(DiscORM.disc_name.contains(disc_name_pattern))
        )
        discs = result.scalars().all()

        if not discs:
            print(f"No discs found matching '{disc_name_pattern}'")
            return

        for disc in discs:
            print("=" * 80)
            print(f"DISC: {disc.disc_name}")
            print(f"  ID: {disc.disc_id}")
            print(f"  Status: {disc.status}")
            print(f"  Agent: {disc.agent_id}")
            print(f"  Drive: {disc.drive}")
            print(f"  Created: {disc.created_at}")

            # Parse titles from metadata
            if disc.titles:
                titles = json.loads(disc.titles) if isinstance(disc.titles, str) else disc.titles
                print(f"\nTITLES ({len(titles)} total):")
                selected_count = 0
                for i, title in enumerate(titles):
                    selected = title.get("selected", False)
                    if selected:
                        selected_count += 1
                    name = title.get("name", title.get("episode_name", "Unknown"))
                    duration = title.get("duration", "?")
                    print(f"  [{i}] {'[SELECTED]' if selected else '[       ]'} {name} ({duration})")
                print(f"\n  Selected titles: {selected_count}/{len(titles)}")

            # Get jobs for this disc
            result = await session.execute(
                select(JobORM).where(JobORM.disc_id == disc.disc_id)
            )
            jobs = result.scalars().all()

            print(f"\nJOBS ({len(jobs)} total):")
            if jobs:
                for job in jobs:
                    print(f"  Job {job.job_id[:8]}...")
                    print(f"    Type: {job.job_type}")
                    print(f"    Status: {job.status}")
                    print(f"    Title Index: {job.title_index}")
                    print(f"    Output: {job.output_name}")
            else:
                print("  No jobs found for this disc")

            print("=" * 80)

    await engine.dispose()


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else "OFFICE"
    asyncio.run(debug_disc(pattern))
