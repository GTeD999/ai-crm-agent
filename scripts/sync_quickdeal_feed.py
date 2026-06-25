from __future__ import annotations

import asyncio

from app.services.properties.sync import QuickDealSyncService


async def main() -> None:
    count = await QuickDealSyncService().sync()
    print(f"Synced {count} QuickDeal offers")


if __name__ == "__main__":
    asyncio.run(main())
