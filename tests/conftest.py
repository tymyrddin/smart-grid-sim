import json
import pytest


@pytest.fixture
def mock_async_client():
    """A minimal async mock for aiomqtt.Client.publish."""
    class _MockClient:
        def __init__(self):
            self.published = []

        async def publish(self, topic: str, payload):
            if isinstance(payload, (str, bytes)):
                try:
                    self.published.append((topic, json.loads(payload)))
                except (json.JSONDecodeError, ValueError):
                    self.published.append((topic, payload))
            else:
                self.published.append((topic, payload))

    return _MockClient()
