from context_tracker import ContextTracker
from storage import ContextStorage


# Example usage:
async def main():
    storage = ContextStorage()
    tracker = ContextTracker(context_storage=storage)

    # Switch context
    # TODO: tracker.switch_context('learning')

    # Run a capture cycle
    note_path = await tracker.run_capture_cycle(context=tracker.current_context)
    print(f"Created note: {note_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
