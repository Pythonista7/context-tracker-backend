from datetime import datetime
from context_tracker import ContextTracker
from data import Context
from storage import ContextStorage


# Example usage:
async def main():
    storage = ContextStorage()
    # Create a context
    current_context = storage.get_last_active_context()
    if current_context is None:
        current_context = Context(id="learning", name="learning",color="#000000", description="Learning new things", last_active=datetime.now())
        storage.save_context(current_context)

    tracker = ContextTracker(
        context=current_context,
        context_storage=storage
    )

    # Switch context
    # TODO: tracker.switch_context('learning')

    # Run a capture cycle
    note_path = await tracker.run_capture_cycle()
    print(f"Created note: {note_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
