from flask import Flask, jsonify, request
import json
import asyncio
from functools import wraps
from logging import getLogger
from dataclasses import dataclass

from context import Context
from context_tracker import ContextTracker
from data import ContextData
from session import Session
from storage import ContextStorage

logger = getLogger(__name__)

app = Flask(__name__)
storage = ContextStorage()  # Create singleton instance

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
    """Close database connections when the application context ends"""
    if hasattr(storage, '_pool'):
        while not storage._pool.empty():
            conn = storage._pool.get()
            conn.close()

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
    session = Session(storage=storage, context_id=data.context_id)
    
    # Start capture cycle in background
    context = Context(storage=storage, id=data.context_id)
    tracker = ContextTracker(context_storage=storage, context=context, session=session)
    asyncio.create_task(tracker.run_capture_cycle(interval=15))
    
    return jsonify({
        'session_id': session.session_id,
        'context_id': data.context_id
    })

@app.route('/session/<session_id>/end', methods=['POST'])
@async_route
async def end_session_api(session_id):
    storage = ContextStorage()
    
    # Recreate session and tracker from stored data
    session = await Session.load(storage=storage, session_id=session_id)
    if not session:
        return jsonify({'error': 'Session not found or already ended'}), 404
    
    context = Context(storage=storage, id=session.context_id)
    tracker = ContextTracker(context_storage=storage, context=context, session=session)
    
    # End the session
    tracker.session.end()
    
    # Wait for final capture and get summary
    summary = await tracker.session.summarize_and_save(session_id)
    
    return jsonify({
        'session_id': session_id,
        'summary': summary
    })

if __name__ == "__main__":
    app.run(debug=True) 