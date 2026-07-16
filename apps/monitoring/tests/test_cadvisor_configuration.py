from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "docker-compose.prod.yml"


class CadvisorConfigurationTests(SimpleTestCase):
    def test_production_cadvisor_uses_current_ghcr_image_and_kernel_device(self):
        source = COMPOSE_FILE.read_text(encoding="utf-8")
        cadvisor = source.split("\n  cadvisor:\n", 1)[1].split("\n  redis_exporter:\n", 1)[0]

        self.assertIn("image: ghcr.io/google/cadvisor:v0.60.5", cadvisor)
        self.assertNotIn("gcr.io/cadvisor/cadvisor", cadvisor)
        self.assertIn("privileged: true", cadvisor)
        self.assertIn("- /dev/kmsg:/dev/kmsg", cadvisor)
        self.assertIn("- /var/lib/docker:/var/lib/docker:ro", cadvisor)
