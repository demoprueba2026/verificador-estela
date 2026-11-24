import os
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI()

# Conexión con Supabase (toma los valores desde Vercel)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Credenciales y URL de Meru (toma los valores desde Vercel)
MERU_API_KEY = os.environ.get("MERU_API_KEY")
MERU_API_SECRET = os.environ.get("MERU_API_SECRET")
MERU_BASE_URL = os.environ.get("MERU_BASE_URL", "https://api.getmeru.com/v1/payments")

MONTO_ESPERADO = 1.00  # $1.00 USD


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
        respuesta = requests.get(f"{MERU_BASE_URL}/{tx_id.strip()}", headers=headers, timeout=10)

        if respuesta.status_code != 200:
            return {"valido": False, "motivo": "Transacción no encontrada en Meru"}

        datos_meru = respuesta.json()

        # Verifica estado y monto
        estado = str(datos_meru.get("status", "")).lower()
        monto = float(datos_meru.get("amount", 0))

        if estado in ["completed", "paid", "approved", "succeeded"] and monto >= MONTO_ESPERADO:
            return {"valido": True, "motivo": "Pago verificado"}

        return {"valido": False, "motivo": "Pago incompleto o pendiente"}

    except Exception as e:
        return {"valido": False, "motivo": f"Error de conexión con Meru: {str(e)}"}


@app.get("/")
def inicio():
    return {"estado": "API de Estela funcionando"}


@app.post("/verificar")
def verificar_pago(datos: SolicitudPago):
    tx_limpio = datos.tx_id.strip()

    if not tx_limpio:
        return {"aprobado": False, "mensaje": "ID de transacción vacío"}

    # 1. Revisar si el comprobante ya se usó antes en Supabase
    existe = supabase.table("pagos_usados").select("tx_id").eq("tx_id", tx_limpio).execute()

    if existe.data and len(existe.data) > 0:
        return {
            "aprobado": False,
            "mensaje": "Este comprobante ya fue utilizado."
        }

    # 2. Consultar en Meru si el pago es real y de $1.00 USD
    resultado_meru = consultar_pago_en_meru(tx_limpio)

    if not resultado_meru["valido"]:
        return {
            "aprobado": False,
            "mensaje": resultado_meru["motivo"]
        }

    # 3. Guardar el ID en Supabase para que nadie pueda volver a usarlo
    supabase.table("pagos_usados").insert({
        "tx_id": tx_limpio,
        "producto": datos.producto,
        "monto": MONTO_ESPERADO
    }).execute()

    return {
        "aprobado": True,
        "mensaje": "Pago aprobado"
    }