"""AI köməkçi tətbiqinin ictimai müqaviləsi (2026-10-01).

Digər tətbiqlər ``apps.ai_assistant``-ın daxili modullarına (``gemini_client``,
``security`` …) birbaşa import etməməlidir (``scripts/public_api_boundaries.py``).
Hazırda yeganə istehlakçı ``apps.monitoring``-dir: «AI ilə təhlil et» düyməsi.
"""

from .monitoring_analysis import SEVERITIES, analyze_monitoring_snapshot, monitoring_ai_status

__all__ = ["SEVERITIES", "analyze_monitoring_snapshot", "monitoring_ai_status"]
