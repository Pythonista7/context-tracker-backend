import json
import asyncio

from context import Context
from context_tracker import ContextTracker
from data import ContextData
from session import Session
from storage import ContextStorage


async def end_session(tracker: ContextTracker):
    await tracker.session._end_session_event.wait()
    print("Session ended! Generating summary...")
    summary = await tracker.session.summarize_and_save(tracker.session.session_id)
    print(f"Session summary: {summary}")
    with open("session_summary.json", "w") as f:
        json.dump(summary.model_dump_json(), f)

async def auto_end_session(tracker: ContextTracker, timeout_seconds: int):
    print(f"Session will automatically end in {timeout_seconds} seconds...")
    await asyncio.sleep(timeout_seconds)
    tracker.session.end()

# Example usage:
async def main():
    storage = ContextStorage()
    context = Context(storage=storage).create(name="kili_tile_run")
    session = Session(storage=storage,context_id=context.id)
    tracker = ContextTracker(context_storage=storage,context=context,session=session)

    # Create tasks for all operations
    capture_task = asyncio.create_task(tracker.run_capture_cycle(interval=15))
    end_session_task = asyncio.create_task(end_session(tracker))
    auto_end_task = asyncio.create_task(auto_end_session(tracker, timeout_seconds=120))  # 60 seconds timeout
    
    # Wait for all tasks to complete
    await asyncio.gather(capture_task, end_session_task, auto_end_task)

if __name__ == "__main__":
    asyncio.run(main())