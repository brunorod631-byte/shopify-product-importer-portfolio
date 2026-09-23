# Shopify Product Importer

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![Shopify](https://img.shields.io/badge/Shopify-GraphQL-96BF48?logo=shopify&logoColor=white)
![Tests](https://img.shields.io/github/actions/workflow/status/brunorod631-byte/shopify-product-importer-portfolio/tests.yml?label=tests)

Bot de Telegram que recibe el enlace de un producto de un proveedor, extrae y normaliza su información y crea un **borrador en Shopify** listo para revisar. Esta es una versión pública y saneada: no contiene credenciales, datos reales ni configuración de producción.

## Problema

Cargar productos de proveedores en una tienda Shopify a mano implica copiar título, descripción, especificaciones, SKU y fotos, convertir el precio a pesos uruguayos y aplicar el recargo del negocio. Es lento, repetitivo y fácil de equivocarse (precios mal convertidos, productos duplicados, fotos de baja calidad).

## Solución

El operador pega una URL en Telegram. El bot identifica el proveedor, extrae los datos, los limpia, calcula el precio final y muestra una vista previa editable. Solo después de la confirmación crea el producto en Shopify, siempre como `DRAFT`. Publicarlo en la tienda online es un paso aparte que requiere confirmación explícita.

```text
URL del proveedor ─► Bot de Telegram ─► validación de usuario y URL
                                      ─► extractor del proveedor (o genérico)
                                      ─► limpieza + conversión de moneda + recargo
                                      ─► vista previa editable ─► confirmación
                                      ─► Shopify Admin GraphQL (DRAFT)
                                      ─► /publicar (opcional, con confirmación)
```

## Funcionalidades

**Extracción**
- Extractores específicos por proveedor (Ingco, Emtop, Würth, Goldfarb, Orofino, Vicas, Ferretera del Norte, Mercado Libre).
- Extractor genérico con fallback JSON-LD y Open Graph para sitios sin adaptador propio.
- Obtiene nombre, marca, categoría, precio, moneda, descripción, especificaciones, contenido incluido, SKU / MPN / código de barras e imágenes.
- Páginas de listado de Ferretera del Norte: detecta la grilla y deja elegir qué producto importar.
- Búsqueda de imágenes en páginas renderizadas con Playwright (atributos lazy-load y `srcset`), filtrando logos, íconos y banners.

**Procesamiento de datos**
- Elimina códigos internos del título, la descripción y las especificaciones.
- Conversión a UYU con una API de tipo de cambio o con la cotización de venta del BROU (según el proveedor), con caché configurable.
- Recargo porcentual configurable por usuario (`/recargo`).
- Descripción HTML generada solo a partir de datos extraídos (ventajas, características, usos, contenido incluido) + meta descripción SEO.

**Imágenes**
- Validación del archivo, corrección de orientación EXIF, descarte de imágenes chicas y conversión a JPEG optimizado.
- Deduplicación por hash perceptual.
- Reemplazo manual de la foto enviándola por Telegram.

**Validaciones y control**
- Detección de duplicados por URL de origen o por hash de título + marca + SKU / código de barras / MPN.
- Historial de importaciones en base de datos con estados (`EXTRACTING`, `PREVIEW`, `COMPLETED`, `FAILED`, …) y comando `/historial`.

**Integración con Shopify**
- Cliente GraphQL con reintentos ante errores de red; soporta token de Admin o credenciales de app (client credentials) con renovación automática del token.
- Chequeo de permisos de la app (`write_products`) antes de operar.
- Crea el producto con imágenes, vendor, tipo de producto, tags de origen, SEO, metafield con la URL de origen, precio, precio comparativo, SKU y código de barras.
- Verifica que Shopify confirme el estado `DRAFT` y devuelve el enlace al producto en el admin.

## Seguridad

- Solo usuarios de Telegram autorizados por ID pueden usar el bot.
- Validación de URLs: solo `http`/`https` hacia IPs públicas (bloquea `localhost`, redes privadas y `file://`).
- Límites de tamaño en páginas e imágenes descargadas.
- Los secretos se cargan desde `.env` (excluido por `.gitignore`) y se reemplazan por `[REDACTED]` en los logs.
- El contenedor Docker corre con un usuario sin privilegios.

## Stack

Python 3.12 · python-telegram-bot · httpx · BeautifulSoup + lxml · Pydantic / pydantic-settings · SQLAlchemy · Pillow + ImageHash · Playwright · tenacity · Shopify Admin GraphQL API · pytest · Ruff · Docker · GitHub Actions

## Arquitectura

| Carpeta | Responsabilidad |
| --- | --- |
| `app/telegram/` | Comandos, teclados, estados de la conversación y autorización |
| `app/extractors/` | Un adaptador por proveedor + extractor genérico; `registry.py` elige cuál usar según el dominio |
| `app/services/` | Orquestación de la importación, precios y cotizaciones, imágenes, duplicados y descripciones |
| `app/shopify/` | Cliente GraphQL, creación de productos y publicación |
| `app/utils/` | Normalización de texto, montos y validación de URLs |
| `app/models.py`, `app/database.py` | Registro de importaciones con SQLAlchemy |
| `tests/` | Pruebas con fixtures HTML y mocks de HTTP (sin servicios externos) |

Más detalle en [`docs/architecture.md`](docs/architecture.md).

## Desafíos técnicos

- **Sitios muy distintos entre sí:** cada proveedor publica los datos de otra forma, por eso hay un adaptador por sitio y un extractor genérico basado en datos estructurados como respaldo.
- **Imágenes cargadas con JavaScript:** algunas páginas no exponen las fotos en el HTML inicial; se renderizan con Playwright y se elige la mejor resolución del `srcset`.
- **Precios en otras monedas:** conversión con caché y, para un proveedor, lectura de la cotización de venta publicada por el BROU.
- **Evitar publicar por error:** el producto se crea como `DRAFT`, se verifica el estado devuelto por Shopify y publicar requiere un comando y una confirmación aparte.
- **Un bot que descarga URLs arbitrarias:** validación contra SSRF (IPs internas) y límites de tamaño.

## Demo offline

La copia pública no contiene tokens ni una tienda Shopify. `demo.py` carga un fixture local y no llama a Telegram, Shopify ni proveedores externos:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python demo.py
```

## Pruebas

```bash
pytest
```

40 pruebas cubren extracción, GraphQL, conversión de moneda, validación de URLs, imágenes y el flujo de importación. Corren en GitHub Actions sin credenciales externas.

## Configuración para desarrollo

```bash
cp .env.example .env             # Windows: Copy-Item .env.example .env
python -m app.main
```

Usá **solo credenciales de una tienda de prueba** y una base de datos local. El estado por defecto de los productos es `DRAFT`.

### Qué no se debe subir nunca

- El archivo `.env` o cualquier token de Telegram / Shopify.
- Bases de datos (`*.db`, `*.sqlite`), logs y backups.
- IDs reales de usuarios de Telegram, dominios de tiendas reales o capturas con datos de clientes.

## Limitaciones

Los sitios de proveedores pueden cambiar su HTML o bloquear accesos automatizados; en esos casos el bot informa el error y permite editar los datos o cargar la foto manualmente.

## Estado

Versión pública saneada, con demo offline y pruebas automatizadas. El historial Git es nuevo y no incluye datos de la instancia privada.

## Autor

Bruno Rodríguez · [Perfil de GitHub](https://github.com/brunorod631-byte)

La IA se usó como herramienta de asistencia para documentación y revisión; las capacidades descritas pueden verificarse en el código y las pruebas.
