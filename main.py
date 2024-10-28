from context_tracker import ContextTracker


# Example usage:
async def main():
    tracker = ContextTracker()

    # Switch context
    # TODO: tracker.switch_context('learning')

    # Run a capture cycle
    note_path = await tracker.run_capture_cycle()
    print(f"Created note: {note_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
