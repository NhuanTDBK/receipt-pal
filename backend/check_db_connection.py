import os
import asyncio
import asyncpg
from dotenv import load_dotenv


async def test_connection():
    load_dotenv()

    # Use DATABASE_URL from .env
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        return

    try:
        conn = await asyncpg.connect(db_url)
        print("✅ Successfully connected to PostgreSQL")
        await conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")
        # Show detailed error for debugging
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_connection())
