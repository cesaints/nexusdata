"""Nomes de tarefas e filas — fonte única da verdade (evita typos entre
publisher e worker)."""

from __future__ import annotations

TASK_PROCESS_DOCUMENT = "nexusdata.process_document"
TASK_DELIVER_WEBHOOK = "nexusdata.deliver_webhook"

QUEUE_DOCUMENTS = "nexus.documents"
QUEUE_WEBHOOKS = "nexus.webhooks"
