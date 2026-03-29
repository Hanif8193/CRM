"""Web chat channel handler."""
from agent.agent import get_agent_response

# Simple in-memory conversation store (replace with DB in production)
conversations: dict = {}


def handle_web_message(customer_id: str, message: str) -> dict:
    """Process a message from the web chat widget. Returns the full agent result dict."""
    history = conversations.get(customer_id, [])

    result = get_agent_response(message, channel="web", conversation_history=history)

    # Persist turn to in-memory history
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": result["response"]})
    conversations[customer_id] = history

    return result
