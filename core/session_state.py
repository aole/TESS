import uuid


# Shared process token for UI state that should reset when the server restarts.
SERVER_SESSION_ID = uuid.uuid4().hex
