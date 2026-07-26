from html import escape

from app.utils.text import clean_text


class EnhancedDescriptionProvider:
    """Genera texto comercial original usando solamente evidencia extraída."""

    def _evidence(self, product) -> str:
        return " ".join(
            [product.title, product.description, product.category or ""]
            + [f"{key} {value}" for key, value in product.specifications.items()]
            + list(product.included)
        ).lower()

    def _benefits(self, product) -> list[str]:
        evidence = self._evidence(product)
        rules = (
            (("batería", "bateria", "inalámbr", "inalambr"),
             "Funcionamiento a batería para trabajar con mayor libertad de movimiento."),
            (("sin carbones", "brushless", "sin escobillas"),
             "Motor sin carbones, pensado para reducir el mantenimiento habitual del motor."),
            (("maletín", "maletin", "valija"),
             "Presentación con maletín o valija para facilitar el orden y el traslado."),
            (("velocidad variable",),
             "Velocidad variable para adaptar el funcionamiento a la tarea indicada."),
            (("luz led", "luz de trabajo"),
             "Luz de trabajo integrada para mejorar la visibilidad de la zona de uso."),
            (("sumergible",),
             "Diseño sumergible, de acuerdo con la aplicación indicada por el fabricante."),
            (("autocebante", "autocebado"),
             "Sistema autocebante para simplificar la puesta en funcionamiento."),
            (("doble lente", "dual lens"),
             "Configuración de doble lente para ampliar las posibilidades de visualización."),
            (("solar", "panel solar"),
             "Alimentación solar indicada en la ficha del producto."),
        )
        return [message for terms, message in rules if any(term in evidence for term in terms)][:6]

    def _uses(self, product) -> list[str]:
        evidence = self._evidence(product)
        rules = (
            (("bomba de agua", "bomba sumergible"),
             "Movimiento de agua en instalaciones compatibles con el caudal y la altura especificados."),
            (("compresor",),
             "Tareas de aire comprimido compatibles con la presión y capacidad declaradas."),
            (("amoladora", "esmeriladora"),
             "Trabajos de corte o desbaste utilizando el disco adecuado para cada material."),
            (("taladro",),
             "Perforación y atornillado dentro de las capacidades indicadas para el equipo."),
            (("atornillador", "punta de impacto"),
             "Tareas de atornillado con herramientas y encastres compatibles."),
            (("hidrolavadora",),
             "Limpieza con agua a presión dentro de los parámetros informados."),
            (("soldadora",),
             "Trabajos de soldadura compatibles con el proceso y rango declarados."),
        )
        uses = [message for terms, message in rules if any(term in evidence for term in terms)]
        if not uses and product.category:
            uses.append(
                f"Aplicaciones relacionadas con {product.category.lower()}, respetando las capacidades del fabricante."
            )
        return uses[:3]

    def generate(self, product):
        title = escape(product.title)
        brand = escape(product.brand) if product.brand else None
        category = escape(product.category.lower()) if product.category else None
        intro = f"<p><strong>{title}</strong>"
        if brand:
            intro += f" de <strong>{brand}</strong>"
        intro += " ofrece una solución práctica y funcional"
        if category:
            intro += f" para tareas vinculadas con {category}"
        intro += ". La información presentada se basa en las características verificadas de su ficha técnica.</p>"
        sections = [intro]

        benefits = self._benefits(product)
        if benefits:
            sections.append(
                "<h2>Ventajas destacadas</h2><ul>"
                + "".join(f"<li>{escape(item)}</li>" for item in benefits)
                + "</ul>"
            )
        if product.specifications:
            sections.append(
                "<h2>Características principales</h2><ul>"
                + "".join(
                    f"<li><strong>{escape(key)}:</strong> {escape(value)}</li>"
                    for key, value in product.specifications.items()
                )
                + "</ul>"
            )
        uses = self._uses(product)
        if uses:
            sections.append(
                "<h2>Usos recomendados</h2><ul>"
                + "".join(f"<li>{escape(item)}</li>" for item in uses)
                + "</ul>"
            )
        if product.included:
            sections.append(
                "<h2>Contenido incluido</h2><ul>"
                + "".join(f"<li>{escape(item)}</li>" for item in product.included)
                + "</ul>"
            )

        important = ["Verificá medidas, capacidades y compatibilidad antes de usar."]
        if product.variants:
            important.append("Seleccioná la variante correspondiente antes de finalizar la compra.")
        if product.availability:
            important.append("La disponibilidad informada corresponde al momento de la consulta.")
        if not product.included:
            important.append("El contenido de la entrega es el indicado expresamente en la publicación.")
        sections.append(
            "<h2>Información importante</h2><ul>"
            + "".join(f"<li>{escape(item)}</li>" for item in important)
            + "</ul>"
        )
        seo = clean_text(
            f"{product.title}{f' {product.brand}' if product.brand else ''}. "
            "Conocé sus características, usos recomendados y contenido incluido."
        )[:160]
        return "".join(sections), seo
