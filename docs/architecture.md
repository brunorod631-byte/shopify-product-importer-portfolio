# Arquitectura

La entrada de Telegram pasa por validación de usuario y URL. El registry selecciona un extractor, `ImportService` normaliza y calcula precios, y `ShopifyClient` encapsula GraphQL. Las pruebas reemplazan fetch y servicios externos con fixtures/mocks.
