import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import time
import json

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Extractor IA Gemini - Blindado", page_icon="🤖", layout="wide")

st.title("🤖 Extractor Triple A - Inteligencia Artificial (Versión Tanque)")
st.markdown("""
Este sistema usa **Google Gemini** para leer tus facturas. 
Incluye sistema de **auto-reparación**: si un modelo falla, intenta con otro automáticamente.
""")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🔑 Llave de Acceso")
    api_key = st.text_input("Pega tu Google API Key aquí", type="password")
    st.info("Obtenla gratis en Google AI Studio.")

# --- FUNCIÓN ROBUSTA DE LLAMADA A LA IA ---
def llamar_gemini_seguro(model_name, prompt, file_bytes):
    """Intenta llamar a un modelo específico."""
    model = genai.GenerativeModel(model_name)
    response = model.generate_content([
        {'mime_type': 'application/pdf', 'data': file_bytes},
        prompt
    ])
    return response.text

def analizar_con_gemini(file_bytes, filename, api_key):
    # Configurar
    genai.configure(api_key=api_key)
    
    # PROMPT (Instrucciones)
    prompt = """
    Eres un experto contable. Analiza esta factura de Triple A (Barranquilla) y extrae datos en JSON.
    
    CAMPOS OBLIGATORIOS:
    - ARCHIVO: "{filename}"
    - NUMERO_FACTURA: El número principal de la factura.
    - FECHA_PERIODO: Mes y año facturado (ej: Abril 2023).
    - FECHA_VENCIMIENTO: Fecha límite de pago.
    - NOMBRE: Nombre del suscriptor.
    - VALOR_FACTURA: Valor del consumo del mes (Servicios del periodo).
    - VALOR_TOTAL_DEUDA: Total a Pagar (Deuda total).
    - ALUMBRADO: Impuesto de alumbrado público.
    - INTERESES: Intereses de mora.
    - POLIZA: Número de póliza.
    - MODELO: Identifica si es "LEGACY" (vieja), "TRANSICION" (2023) o "ELECTRONICA".

    REGLAS:
    - Devuelve SOLO el JSON válido. Sin markdown (```json).
    - Si un valor es 0 o no existe, pon 0.
    """.format(filename=filename)

    try:
        # INTENTO 1: Usar GEMINI 1.5 FLASH (El rápido y nuevo)
        try:
            raw_text = llamar_gemini_seguro('gemini-1.5-flash', prompt, file_bytes)
        except Exception as e:
            # Si falla (ej: error 404), intentamos con el modelo PRO (El clásico)
            print(f"Fallo Flash, intentando Pro: {e}")
            raw_text = llamar_gemini_seguro('gemini-1.5-pro', prompt, file_bytes)
        
        # Limpieza de respuesta
        json_text = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(json_text)
        
        # Garantizar nombre de archivo
        data['ARCHIVO'] = filename
        return data

    except Exception as e:
        return {"ARCHIVO": filename, "NOMBRE": f"ERROR FATAL: {str(e)}", "VALOR_TOTAL_DEUDA": 0}

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube tus Facturas (PDF)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if not api_key:
        st.error("⚠️ ¡Falta la API Key! Pégala en la izquierda.")
    else:
        if st.button(f"🚀 Procesar {len(uploaded_files)} Facturas"):
            results = []
            bar = st.progress(0)
            status = st.empty()
            
            for i, f in enumerate(uploaded_files):
                status.text(f"Analizando {i+1}/{len(uploaded_files)}: {f.name}")
                
                # Procesar
                data = analizar_con_gemini(f.getvalue(), f.name, api_key)
                results.append(data)
                
                # Pausa anti-bloqueo (4 seg)
                time.sleep(4)
                bar.progress((i+1)/len(uploaded_files))
            
            status.success("¡Finalizado!")
            
            df = pd.DataFrame(results)
            
            # Ordenar columnas
            cols = ['ARCHIVO', 'FECHA_PERIODO', 'FECHA_VENCIMIENTO', 'NUMERO_FACTURA', 
                    'NOMBRE', 'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
                    'ALUMBRADO', 'INTERESES', 'POLIZA', 'MODELO']
            
            # Rellenar faltantes
            for c in cols: 
                if c not in df.columns: df[c] = None
                
            st.dataframe(df[cols])
            
            # Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df[cols].to_excel(writer, index=False)
                
            st.download_button("Descargar Excel", buffer.getvalue(), "Reporte_IA_Final.xlsx")
