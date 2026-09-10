"""Servicio de clientes contra la base real, con RLS activo.

Cada prueba corre a través de `sesion_rls`, que es exactamente el camino que
sigue un request: rol `authenticated` y claims del usuario. Lo que aquí pasa,
pasa en producción.

    pytest tests/integration/test_clientes.py -v
"""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import sesion_rls, sesion_servicio
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado
from app.core.roles import Rol
from app.core.security import UsuarioAutenticado
from app.modules.clientes import service
from app.modules.clientes.models import TipoCliente
from app.modules.clientes.schemas import ClienteCrear, ClienteEditar
from app.shared.paginacion import ParametrosPagina

pytestmark = pytest.mark.integration

PAGINA = ParametrosPagina(limite=50, desplazamiento=0)


def _usuario(taller_id: UUID, rol: Rol = Rol.ASESOR_SERVICIO) -> UsuarioAutenticado:
    return UsuarioAutenticado(id=uuid4(), taller_id=taller_id, rol=rol)


@pytest_asyncio.fixture
async def dos_talleres() -> AsyncIterator[tuple[UUID, UUID]]:
    sfx = uuid4().hex[:8]
    async with sesion_servicio() as s:
        filas = await s.execute(
            text("""
                insert into public.talleres (nombre, slug, prefijo_orden)
                values ('Cli A ' || :sfx, 'cli-a-' || :sfx, 'CLA'),
                       ('Cli B ' || :sfx, 'cli-b-' || :sfx, 'CLB')
                returning id
            """),
            {"sfx": sfx},
        )
        a, b = (r[0] for r in filas.fetchall())

    yield a, b

    async with sesion_servicio() as s:
        await s.execute(text("delete from public.talleres where id = any(:ids)"), {"ids": [a, b]})


# -----------------------------------------------------------------------------
# Alta y consulta
# -----------------------------------------------------------------------------


async def test_crear_toma_el_taller_del_token(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        cliente = await service.crear(
            s, ClienteCrear(nombre="Andrés Villamizar", documento="V-12345678"), _usuario(a)
        )

    assert cliente.taller_id == a
    assert cliente.activo is True
    assert cliente.tipo is TipoCliente.PERSONA


async def test_obtener_devuelve_lo_creado(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        creado = await service.crear(s, ClienteCrear(nombre="Carmen Odreman"), _usuario(a))
        cliente_id = creado.id

    async with sesion_rls(_usuario(a)) as s:
        recuperado = await service.obtener(s, cliente_id)

    assert recuperado.nombre == "Carmen Odreman"


async def test_obtener_inexistente_da_no_encontrado(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener(s, uuid4())


# -----------------------------------------------------------------------------
# Aislamiento entre talleres
# -----------------------------------------------------------------------------


async def test_no_ve_clientes_de_otro_taller(dos_talleres: tuple[UUID, UUID]) -> None:
    a, b = dos_talleres

    async with sesion_rls(_usuario(b)) as s:
        ajeno = await service.crear(s, ClienteCrear(nombre="Cliente de B"), _usuario(b))
        ajeno_id = ajeno.id

    async with sesion_rls(_usuario(a)) as s:
        items, total = await service.listar(s, pagina=PAGINA)

    assert total == 0
    assert items == []

    # Y tampoco por id directo: RLS lo hace invisible, así que sale 404 y no un
    # 403, que confirmaría que el registro existe.
    async with sesion_rls(_usuario(a)) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.obtener(s, ajeno_id)


async def test_no_puede_editar_cliente_ajeno(dos_talleres: tuple[UUID, UUID]) -> None:
    a, b = dos_talleres

    async with sesion_rls(_usuario(b)) as s:
        ajeno_id = (await service.crear(s, ClienteCrear(nombre="Intocable"), _usuario(b))).id

    async with sesion_rls(_usuario(a)) as s:
        with pytest.raises(ErrorNoEncontrado):
            await service.actualizar(s, ajeno_id, ClienteEditar(nombre="Secuestrado"))


# -----------------------------------------------------------------------------
# Permisos por rol
# -----------------------------------------------------------------------------


async def test_tecnico_no_puede_dar_de_alta(dos_talleres: tuple[UUID, UUID]) -> None:
    """La política RLS rechaza al técnico aunque el router lo dejara pasar."""
    a, _ = dos_talleres
    tecnico = _usuario(a, Rol.TECNICO)

    async with sesion_rls(tecnico) as s:
        with pytest.raises(DBAPIError):
            await service.crear(s, ClienteCrear(nombre="No debería entrar"), tecnico)


async def test_tecnico_si_puede_consultar(dos_talleres: tuple[UUID, UUID]) -> None:
    """Necesita ver de quién es el vehículo que tiene asignado."""
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        await service.crear(s, ClienteCrear(nombre="Visible al técnico"), _usuario(a))

    async with sesion_rls(_usuario(a, Rol.TECNICO)) as s:
        _, total = await service.listar(s, pagina=PAGINA)

    assert total == 1


# -----------------------------------------------------------------------------
# Búsqueda, edición y borrado
# -----------------------------------------------------------------------------


async def test_busqueda_por_coincidencia_parcial(dos_talleres: tuple[UUID, UUID]) -> None:
    """El motivo de cambiar el índice a trigramas: "villa" debe hallar "Villamizar"."""
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        for nombre in ("Andrés Villamizar", "Carmen Odreman", "Luis Betancourt"):
            await service.crear(s, ClienteCrear(nombre=nombre), _usuario(a))

    async with sesion_rls(_usuario(a)) as s:
        items, total = await service.listar(s, busqueda="villa", pagina=PAGINA)

    assert total == 1
    assert items[0].nombre == "Andrés Villamizar"


async def test_busqueda_corta_se_ignora(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        await service.crear(s, ClienteCrear(nombre="Neida Colmenares"), _usuario(a))

    async with sesion_rls(_usuario(a)) as s:
        _, total = await service.listar(s, busqueda="ne", pagina=PAGINA)

    assert total == 1, "un término de menos de 3 caracteres no debe filtrar"


async def test_documento_duplicado_da_conflicto(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        await service.crear(s, ClienteCrear(nombre="Primero", documento="V-999"), _usuario(a))

    async with sesion_rls(_usuario(a)) as s:
        with pytest.raises(ErrorConflicto):
            await service.crear(s, ClienteCrear(nombre="Segundo", documento="V-999"), _usuario(a))


async def test_mismo_documento_en_talleres_distintos_es_valido(
    dos_talleres: tuple[UUID, UUID],
) -> None:
    """La unicidad es por taller: el mismo señor puede ser cliente de los dos."""
    a, b = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        await service.crear(s, ClienteCrear(nombre="Compartido", documento="V-777"), _usuario(a))

    async with sesion_rls(_usuario(b)) as s:
        cliente = await service.crear(
            s, ClienteCrear(nombre="Compartido", documento="V-777"), _usuario(b)
        )

    assert cliente.taller_id == b


async def test_patch_parcial_no_borra_los_demas_campos(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        creado = await service.crear(
            s,
            ClienteCrear(nombre="Gustavo Alcántara", documento="V-555", direccion="La Urbina"),
            _usuario(a),
        )
        cliente_id = creado.id

    async with sesion_rls(_usuario(a)) as s:
        editado = await service.actualizar(
            s, cliente_id, ClienteEditar(telefono="+58 414 111 2222")
        )

    assert editado.telefono == "+58 414 111 2222"
    assert editado.documento == "V-555"
    assert editado.direccion == "La Urbina"


async def test_desactivar_lo_saca_del_listado(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        cliente_id = (await service.crear(s, ClienteCrear(nombre="De baja"), _usuario(a))).id

    async with sesion_rls(_usuario(a)) as s:
        await service.actualizar(s, cliente_id, ClienteEditar(activo=False))

    async with sesion_rls(_usuario(a)) as s:
        _, activos = await service.listar(s, pagina=PAGINA)
        _, todos = await service.listar(s, solo_activos=False, pagina=PAGINA)

    assert activos == 0
    assert todos == 1


async def test_no_se_borra_un_cliente_con_vehiculos(dos_talleres: tuple[UUID, UUID]) -> None:
    """La FK de vehiculos es RESTRICT: borrar destruiría el historial."""
    a, _ = dos_talleres
    admin = _usuario(a, Rol.ADMIN_TALLER)

    async with sesion_rls(admin) as s:
        cliente_id = (await service.crear(s, ClienteCrear(nombre="Con carro"), admin)).id
        await s.execute(
            text("""
                insert into public.vehiculos (taller_id, cliente_id, placa, marca, modelo)
                values (:t, :c, 'AB123CD', 'Toyota', 'Corolla')
            """),
            {"t": a, "c": cliente_id},
        )

    async with sesion_rls(admin) as s:
        with pytest.raises(ErrorConflicto) as excinfo:
            await service.eliminar(s, cliente_id)

    assert "desactívalo" in str(excinfo.value).lower()


async def test_borrar_cliente_sin_historial(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres
    admin = _usuario(a, Rol.ADMIN_TALLER)

    async with sesion_rls(admin) as s:
        cliente_id = (await service.crear(s, ClienteCrear(nombre="Error de captura"), admin)).id

    async with sesion_rls(admin) as s:
        await service.eliminar(s, cliente_id)

    async with sesion_rls(admin) as s:
        _, total = await service.listar(s, solo_activos=False, pagina=PAGINA)

    assert total == 0


async def test_paginacion(dos_talleres: tuple[UUID, UUID]) -> None:
    a, _ = dos_talleres

    async with sesion_rls(_usuario(a)) as s:
        for i in range(5):
            await service.crear(s, ClienteCrear(nombre=f"Cliente {i:02d}"), _usuario(a))

    async with sesion_rls(_usuario(a)) as s:
        items, total = await service.listar(s, pagina=ParametrosPagina(limite=2, desplazamiento=2))

    assert total == 5
    assert [c.nombre for c in items] == ["Cliente 02", "Cliente 03"]
