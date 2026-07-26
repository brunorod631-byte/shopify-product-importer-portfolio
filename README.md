# importador_shopify_bot

Importador demostrativo de productos: recibe una URL por Telegram, obtiene información pública, normaliza el producto para revisión y puede crear un borrador mediante Shopify Admin GraphQL en una instalación controlada.

## Flujo

```text
URL pública -> Bot de Telegram -> extractor del sitio -> normalización
                              -> revisión y corrección -> Shopify o simulación
```

## Funciones principales

- Autorización por IDs de Telegram.
- Extractores específicos para varios proveedores y fallback JSON-LD/Open Graph.
- Nombre, marca, categoría, precio, moneda, descripción, SKU e imágenes.
- Conversión de moneda y recargos antes de crear un borrador.
- Revisión manual, edición y detección de duplicados.
- Cliente Shopify GraphQL con reintentos y estado `DRAFT`.
- Validación de URLs públicas, límites de tamaño y manejo de errores.

## Demo sin servicios reales

La copia pública no contiene tokens ni una tienda Shopify. Para demostrar la extracción local:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python demo.py
```

`demo.py` utiliza el fixture incluido y no inicia Telegram, no llama a Shopify y no publica productos. Para probar el bot completo se requiere un `.env` propio y una tienda de prueba separada; nunca uses variables de producción.

## Configuración real de desarrollo

```powershell
Copy-Item .env.example .env
```

Completá únicamente credenciales de prueba. `DATABASE_URL` debe apuntar a una base demo. El estado predeterminado de Shopify es `DRAFT`; publicar requiere una acción explícita y no está habilitado por esta demo.

## Pruebas

```powershell
pytest
```

Las pruebas cubren extracción, GraphQL, conversión de moneda, seguridad, imágenes y flujo de importación sin credenciales externas.

## Arquitectura

`app/extractors/` contiene adaptadores por proveedor; `app/services/` coordina importación, precios, imágenes y duplicados; `app/telegram/` gestiona autorización y estados; `app/shopify/` encapsula GraphQL; `app/database.py` mantiene persistencia local.

## Seguridad y privacidad

Los secretos se cargan desde `.env` y están excluidos por `.gitignore`. No se publican bases, logs, backups, IDs reales, URLs privadas ni archivos de Northflank. La copia pública tiene historial Git nuevo y no modifica el servicio de producción.

## Limitaciones y mejoras futuras

Las páginas externas pueden cambiar, bloquear automatización o requerir carga manual. Futuras mejoras: más fixtures offline, contratos por extractor y un mock de Shopify configurable.

## Capturas sugeridas

Agregar en `docs/screenshots/`: URL recibida, vista previa editada, resultado simulado y prueba de rechazo de credenciales.

## Estado y autor

Proyecto demostrativo en evolución. Autor: Bruno Rodríguez. La IA se utilizó como herramienta de asistencia para documentación y revisión; las capacidades deben verificarse mediante el código y las pruebas.
