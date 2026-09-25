"""Cola de personas del vigía de citas DIAN (D-104), en contab.db."""
import pytest

from contab_core import cita_personas


def test_alta_normaliza_cedula_y_se_lista_en_orden():
    a = cita_personas.save_persona({"cedula": "1.234.567-8", "nombre": " Ana ", "autoriza_tratamiento": True})
    b = cita_personas.save_persona({"cedula": "99887766"})
    assert a["cedula"] == "12345678" and a["nombre"] == "Ana"
    assert a["estado"] == "pendiente" and a["autoriza_tratamiento"] is True
    assert b["autoriza_tratamiento"] is False
    assert [p["id"] for p in cita_personas.list_personas()] == [a["id"], b["id"]]


def test_cedula_invalida_o_repetida_es_error_claro():
    with pytest.raises(ValueError, match="solo números"):
        cita_personas.save_persona({"cedula": "12ab"})
    cita_personas.save_persona({"cedula": "11223344"})
    with pytest.raises(ValueError, match="Ya hay una persona"):
        cita_personas.save_persona({"cedula": "11.223.344"})
    with pytest.raises(ValueError, match="correo"):
        cita_personas.save_persona({"cedula": "55667788", "correo": "no-es-correo"})


def test_editar_conserva_el_id_y_el_estado():
    p = cita_personas.save_persona({"cedula": "10203040"})
    cita_personas.set_estado(p["id"], "en_curso", "Trámite: Medellín · Día 28 · Hora 8:00")
    e = cita_personas.save_persona({"id": p["id"], "cedula": "10203040", "celular": "3001234567"})
    assert e["id"] == p["id"] and e["celular"] == "3001234567"
    assert e["estado"] == "en_curso" and "Día 28" in e["detalle"]


def test_marcar_agendada_fecha_y_volver_a_pendiente_la_borra():
    p = cita_personas.save_persona({"cedula": "30405060"})
    ag = cita_personas.set_estado(p["id"], "agendada")
    assert ag["estado"] == "agendada" and ag["agendada_at"]
    back = cita_personas.set_estado(p["id"], "pendiente")
    assert back["estado"] == "pendiente" and back["agendada_at"] is None
    with pytest.raises(ValueError, match="estado inválido"):
        cita_personas.set_estado(p["id"], "cancelada")


def test_borrar():
    p = cita_personas.save_persona({"cedula": "70809010"})
    assert cita_personas.delete_persona(p["id"]) is True
    assert cita_personas.delete_persona(p["id"]) is False
    assert cita_personas.list_personas() == []
