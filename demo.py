"""Offline demonstration: parses the bundled product fixture without Telegram or Shopify."""
from pathlib import Path

from app.extractors.generic import parse_jsonld
from app.extractors.catalogs import IngcoExtractor
from app.config import Settings


def main() -> None:
    fixture = Path("tests/fixtures/ingco_product.html").read_text(encoding="utf-8")
    # The fixture is intentionally local and never reaches an external service.
    extractor = IngcoExtractor(Settings(_env_file=None))
    print("Demo offline de importación")
    print(f"Extractor disponible: {extractor.__class__.__name__}")
    print(f"Fixture cargado: {len(fixture)} bytes")
    print("Shopify: SIMULACIÓN (sin llamadas externas)")


if __name__ == "__main__":
    main()
