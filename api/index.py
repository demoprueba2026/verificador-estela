import os
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

MERU_API_KEY = os.environ.get("MERU_API_KEY")
MERU_API_SECRET = os.environ.get("MERU_API_SECRET")
MERU_BASE_URL = os.environ.get("MERU_BASE_URL", "https://api.getmeru.com/v1/payments")

MONTO_ESPERADO = 1.00


class SolicitudPago(BaseModel):
    tx_id: str
    producto: str


def consultar_pago_en_meru(tx_id: str) -> dict:
    headers = {
        "Authorization": f"Bearer {MERU_API_KEY}",
        "X-Api-Secret": MERU_API_SECRET or "",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.get(f"{MERU_BASE_URL}/{tx_id.strip()}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return {"valido": False, "motivo": "Transacción no encontrada en Meru"}

        data = resp.json()
        estado = str(data.get("status", "")).lower()
        monto = float(data.get("amount", 0))

        if estado in ["completed", "paid", "approved", "succeeded"] and monto >= MONTO_ESPERADO:
            return {"valido": True, "motivo": "Pago verificado en Meru"}

        return {"valido": False, "motivo": "Pago incompleto o pendiente"}
    except Exception as e:
        return {"valido": False, "motivo": f"Error conectando con Meru: {str(e)}"}


@app.get("/")
def inicio():
    return {"estado": "API de Estela activa"}


@app.get("/flujo/{nombre_flujo}")
def obtener_flujo(nombre_flujo: str):
    res = supabase.table("flujos_mensajes").select("*").eq("flujo_nombre", nombre_flujo).execute()
    if not res.data:
        return {"encontrado": False, "mensaje": ""}
    return {"encontrado": True, "flujo": res.data[0]}


@app.post("/verificar")
def verificar_pago(datos: SolicitudPago):
    tx_limpio = datos.tx_id.strip()

    if not tx_limpio:
        return {
            "aprobado": False,
            "motivo": "El ID de transacción está vacío"
        }

    existe = supabase.table("pagos_usados").select("tx_id").eq("tx_id", tx_limpio).execute()
    if existe.data and len(existe.data) > 0:
        return {
            "aprobado": False,
            "motivo": "Este comprobante ya fue utilizado anteriormente"
        }

    resultado_meru = consultar_pago_en_meru(tx_limpio)
    if not resultado_meru["valido"]:
        return {
            "aprobado": False,
            "motivo": resultado_meru["motivo"]
        }

    supabase.table("pagos_usados").insert({
        "tx_id": tx_limpio,
        "producto": datos.producto,
        "monto": MONTO_ESPERADO,
        "estado": "aprobado"
    }).execute()

    return {
        "aprobado": True,
        "motivo": "Pago verificado en Meru"
    }