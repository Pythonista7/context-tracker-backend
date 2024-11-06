from datetime import datetime
from flask import Flask, jsonify, request, g
import json
import asyncio
from functools import wraps
from logging import getLogger, basicConfig, INFO
from dataclasses import dataclass
from typing import Dict, Tuple
import signal
import threading
from concurrent.futures import ThreadPoolExecutor

from context import Context
from context_tracker import ContextTracker
from data import ContextData
from session import Session
from storage import ContextStorage

# Add this near the top of the file, after imports but before creating the Flask app
basicConfig(
    level=INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = getLogger(__name__)

app = Flask(__name__)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Add after app initialization
active_trackers: Dict[int, Tuple[ContextTracker, asyncio.Task]] = {}

# Create a thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=10)

"""
API Request Models
"""

@dataclass
class CreateContextRequest:
    name: str
    description: str | None = None

@dataclass
class StartSessionRequest:
    context_id: str

@app.teardown_appcontext
def close_db(error):
    """Close database connection at the end of request"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def async_route(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        # Create a new event loop for each request
        async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(async_loop)
        try:
            return async_loop.run_until_complete(f(*args, **kwargs))
        finally:
            async_loop.close()
    return wrapped

# Graceful shutdown handler
def shutdown_handler(signum, frame):
    logger.info("Received shutdown signal, cleaning up...")
    
    # Shutdown the thread pool
    executor.shutdown(wait=True)
    
    # Clean up active trackers
    for session_id, (tracker, future) in active_trackers.items():
        logger.info(f"Ending session {session_id}")
        if not tracker.session.ended_at:
            loop.run_until_complete(tracker.session.end())
    
    # Close the main event loop
    loop.close()

# Register shutdown handlers
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

@app.route('/context', methods=['POST'])
@async_route
async def create_context():
    data = CreateContextRequest(**request.json)
    if not data.name:
        return jsonify({'error': 'name is required'}), 400
    
    storage = ContextStorage()
    context = Context(storage=storage).create(name=data.name, description=data.description)
    return jsonify({
        'context_id': context.id,
        'name': context.name
    })

@app.route('/session', methods=['POST'])
@async_route
async def start_session():
    data = StartSessionRequest(**request.json)
    if not data.context_id:
        return jsonify({'error': 'context_id is required'}), 400
    
    storage = ContextStorage()
    
    # Check if context exists
    context = Context(storage=storage).get(id=data.context_id)
    if context is None:
        return jsonify({'error': 'Context not found'}), 404

    # Create tracker and session
    session = Session(storage=storage, context_id=context.id)
    tracker = ContextTracker(context_storage=storage, context=context, session=session)
    
    # Wait for session initialization
    
    
    # Start the capture cycle in a separate thread
    def run_capture():
        async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(async_loop)
        try:
            # Create app context for the background thread
            with app.app_context():
                async_loop.run_until_complete(tracker.run_capture_cycle(interval=15))
        except Exception as e:
            logger.error(f"Capture cycle failed: {e}")
        finally:
            async_loop.close()
    
    # Submit the capture task to the thread pool
    capture_future = executor.submit(run_capture)

    await tracker.initialize()  # We need to wait for this to complete so that session_id is set

    # Store tracker and future
    active_trackers[tracker.session.session_id] = (tracker, capture_future)
    
    return jsonify({
        'session_id': tracker.session.session_id,
        'context_id': data.context_id
    })

@app.route('/session/<session_id>/end', methods=['POST'])
@async_route
async def end_session_api(session_id):
    session_id = int(session_id)
    tracker_tuple = active_trackers.get(session_id)
    if not tracker_tuple:
        return jsonify({'error': f'Session {session_id} not found or already ended'}), 404
    
    tracker, capture_task = tracker_tuple
    
    # End the session using the original tracker instance
    await tracker.session.end()
    
    # Cancel the background task
    capture_task.cancel()
    try:
        await capture_task
    except asyncio.CancelledError:
        logger.error(f"Capture task for session {session_id} cancelled")
        pass
    
    # Clean up the tracker reference
    del active_trackers[session_id]
    
    # Get summary from storage after session end
    storage = ContextStorage()
    session_data = storage.get_session(session_id)
    
    return jsonify({
        'session_id': session_id,
        'summary': {
            'overview': session_data[4],
            'key_topics': session_data[5],
            'learning_highlights': session_data[6],
            'resources_used': session_data[7],
            'conclusion': session_data[8]
        }
    })

@app.route('/session/<session_id>', methods=['GET'])
@async_route
async def get_session(session_id):
    storage = ContextStorage()
    
    # Load session from storage
    session = storage.get_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    return jsonify(session)

@app.route('/session/<session_id>/events', methods=['GET'])
@async_route
async def get_session_events(session_id):
    storage = ContextStorage()
    events = storage.get_session_events(session_id)
    return jsonify(events)

@app.route('/session/<session_id>/status', methods=['GET'])
@async_route
async def get_session_status(session_id):
    # First check active trackers
    tracker_tuple = active_trackers.get(session_id)
    if tracker_tuple:
        tracker, _ = tracker_tuple
        return jsonify({
            'session_id': session_id,
            'status': 'active',
            'context_id': tracker.current_context.id,
            'started_at': tracker.session.started_at.isoformat() if tracker.session.started_at else None
        })
    
    # If not active, check storage for completed session
    storage = ContextStorage()
    session_data = storage.get_session(session_id)
    
    if session_data:
        return jsonify({
            'session_id': session_id,
            'status': 'completed',
            'context_id': session_data[1],  # Assuming context_id is second column
            'started_at': session_data[2],  # Assuming started_at is third column
            'ended_at': session_data[3]     # Assuming ended_at is fourth column
        })
    
    return jsonify({
        'error': 'Session not found'
    }), 404

@app.route('/sessions/active', methods=['GET'])
@async_route
async def list_active_sessions():
    active_sessions = [{
        'session_id': session_id,
        'context_id': tracker.current_context.id,
        'started_at': tracker.session.start_time.isoformat() if tracker.session.start_time else None,
        'name': tracker.current_context.name
    } for session_id, (tracker, _) in active_trackers.items()]
    
    return jsonify({
        'active_sessions': active_sessions,
        'count': len(active_sessions)
    })

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'context-api',
        "ts": datetime.now().isoformat()
    })

if __name__ == "__main__":
    app.run(debug=False, port=5001)  # Set debug=False to avoid duplicate background tasks