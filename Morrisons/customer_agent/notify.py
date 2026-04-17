"""notify.py — Fire-and-forget notifications to downstream enterprise agents.

Called by tools.py after a successful order placement.
OTel spans are opened and closed synchronously in the calling thread so the
dispatch intent is captured in the trace even though the HTTP call runs in a
background daemon thread.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

import httpx

from traces import start_span

logger = logging.getLogger("customer_agent.notify")

_INVENTORY_AGENT_URL = os.environ.get("INVENTORY_AGENT_URL", "http://inventory-agent:8000")
_WAREHOUSE_AGENT_URL = os.environ.get("WAREHOUSE_AGENT_URL", "http://warehouse-agent:8000")

_HTTP_TIMEOUT = 10.0  # seconds — background thread only, customer never waits


def _call_agent(agent_name: str, url: str, message: str, session_id: str) -> None:
    """HTTP POST to a downstream agent's /chat endpoint.  Runs in a daemon thread."""
    payload = {"message": message, "session_id": session_id, "context": {}}
    try:
        resp = httpx.post(url, json=payload, timeout=_HTTP_TIMEOUT)
        logger.info("notify  agent=%s  status=%s", agent_name, resp.status_code)
    except Exception as exc:
        logger.warning("notify  agent=%s  error=%s", agent_name, exc)


def notify_agents_of_order(order_result: dict[str, Any]) -> None:
    """Dispatch fire-and-forget notifications to inventory and warehouse agents.

    A synchronous OTel span is recorded for each dispatch so the intent appears
    in traces immediately, before the background threads execute.
    """
    order_id = order_result.get("order_id", "unknown")
    items    = order_result.get("items", [])
    session  = f"notify-{order_id}"

    targets = [
        (
            "inventory-agent",
            f"{_INVENTORY_AGENT_URL}/chat",
            f"New order placed. Reserve stock for order {order_id}. "
            f"Items: {json.dumps(items)}",
        ),
        (
            "warehouse-agent",
            f"{_WAREHOUSE_AGENT_URL}/chat",
            f"New order placed. Create fulfilment task for order {order_id}. "
            f"Customer: {order_result.get('customer_name', 'unknown')}. "
            f"Items: {json.dumps(items)}",
        ),
    ]

    for agent_name, url, message in targets:
        # Span recorded synchronously → visible in traces immediately
        with start_span(
            f"agent.notify.{agent_name}",
            attributes={
                "agent.target":  agent_name,
                "agent.url":     url,
                "order.id":      order_id,
                "notify.async":  "true",
                "span.kind":     "producer",
            },
        ):
            # Fire the HTTP call in a background daemon thread
            t = threading.Thread(
                target=_call_agent,
                args=(agent_name, url, message, session),
                daemon=True,
            )
            t.start()
            logger.info(
                "notify  dispatched  agent=%s  order=%s  thread=%s",
                agent_name, order_id, t.name,
            )
