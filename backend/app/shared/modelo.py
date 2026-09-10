"""Base declarativa de los modelos SQLAlchemy.

Estos modelos son **mapeo de lectura y escritura sobre un esquema que ya
existe**, no su definición. El esquema lo definen las migraciones SQL de
`supabase/migrations/`, que son la única fuente de verdad.

En consecuencia: nunca se llama a `Base.metadata.create_all()` ni se generan
migraciones a partir de estas clases. Si una columna cambia, primero se escribe
la migración y después se ajusta el modelo.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Raíz de los modelos."""
