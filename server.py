from datetime import datetime
from flask import Flask, jsonify, request, g
import json
import asyncio
from functools import wraps
from logging import getLogger, basicConfig, INFO
from dataclasses import dataclass
from typing import Dict

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
# storage = ContextStorage()  # Create singleton instance

# Add after app initialization
active_trackers: Dict[int, ContextTracker] = {}

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
        return asyncio.run(f(*args, **kwargs))
    return wrapped

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

    # Start capture cycle in background
    session: Session = Session(storage=storage, context_id=context.id)
    tracker: ContextTracker = ContextTracker(context_storage=storage, context=context, session=session)
    asyncio.create_task(tracker.run_capture_cycle(interval=15))
    
    # wait for session to start
    while tracker.session.session_id is None:
        logger.info("Waiting for session to start...")
        await asyncio.sleep(1)
    
    # Store tracker instance
    active_trackers[tracker.session.session_id] = tracker
    
    return jsonify({
        'session_id': tracker.session.session_id,
        'context_id': data.context_id
    })

@app.route('/session/<session_id>/end', methods=['POST'])
@async_route
async def end_session_api(session_id):
    # Get the active tracker instance
    session_id = int(session_id)
    tracker = active_trackers.get(session_id)
    if not tracker:
        return jsonify({'error': f'Session {session_id} not found or already ended. Must be one of {active_trackers.keys()}'}), 404
    
    # End the session using the original tracker instance
    await tracker.session.end()
    
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
    tracker = active_trackers.get(session_id)
    if tracker:
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
    } for session_id, tracker in active_trackers.items()]
    
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
    app.run(debug=True,port=5001) 