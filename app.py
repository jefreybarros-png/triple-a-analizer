import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import time
import json

# --- CONFIGURACIÓN DE SEGURIDAD Y API ---
MY_API_KEY = "AIzaSyB74qmjYXqtEIr1pTdNOBwRHpDrpc_mqHU"

st.set_page_config(page_title="Extractor IA Triple A - Ultra", page_icon="🤖", layout="wide")

st.title("🤖 Extractor Triple A - Inteligencia Artificial (Solución 404)")
st.markdown("Procesando facturas con modelos actualizados de Google Gemini.")

def analizar_factura_ia(file_bytes, filename):
    genai.configure(api_key=MY_API_KEY)
    
    prompt = f"""
    Actúa como un experto contable. Analiza esta factura de Triple A Barranquilla y extrae los datos exactos.
    IMPORTANTE: Busca los valores en las tablas y desgloses.
    
    CAMPOS PARA EL JSON:
    - ARCHIVO: "{filename}"
    - FECHA_PERIODO: El "Período facturado" (ej: Abril 2023).
    - FECHA_VENCIMIENTO: La fecha "Pague hasta" (ej: Abr 05-23).
    - NUMERO_FACTURA: El número de la factura.
    - NOMBRE: Nombre completo del cliente.
    - VALOR_FACTURA: Consumo del mes (TOTAL FACTURA SERVICIOS DEL PERIODO).
    - VALOR_TOTAL_DEUDA: Gran total a pagar (TOTAL FACTURA A PAGAR).
    - ALUMBRADO: Valor del Alumbrado Público.
    - INTERESES: Valor de Intereses de Mora.
    - POLIZA: Número de Póliza.
    - MODELO: Detecta si es LEGACY (vieja), TRANSICION (2023) o ELECTRONICA.

    REGLAS:
    - Responde ÚNICAMENTE con el objeto JSON puro.
    - No uses ```json ni texto adicional.
    - Si un valor no existe, pon 0 o null.
    """

    # LISTA DE MODELOS ACTUALIZADOS (Flash es el más moderno)
    modelos_actuales = ['gemini-1.5-flash', 'gemini-1.5-pro']
    
    for nombre_modelo in modelos_actuales:
        try:
            model = genai.GenerativeModel(nombre_modelo)
            response = model.generate_content([
                {'mime_type': 'application/pdf', 'data': file_bytes},
                prompt
            ])
            
            # Limpieza profunda de la respuesta
            clean_text = response.text.strip()
            if clean_text.startswith("```"):
                clean_text = clean_text.split("```")[1]
                if clean_text.startswith("json"):
                    clean_text = clean_text[4:]
            
            return json.loads(clean_text.strip())
            
        except Exception as e:
            # Si es el último modelo y falla, devolvemos el error en el Excel
            if nombre_modelo == modelos_actuales[-1]:
                return {"ARCHIVO": filename, "NOMBRE": f"ERROR API: {str(e)}", "VALOR_TOTAL_DEUDA": 0}
            continue 

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube tus PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🚀 Procesar {len(uploaded_files)} Facturas"):
        results = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, f in enumerate(uploaded_files):
            status.text(f"Analizando: {f.name}...")
            res = analizar_factura_ia(f.getvalue(), f.name)
            results.append(res)
            time.sleep(2) # Pausa mínima para no saturar la cuenta gratis
            bar.progress((i + 1) / len(uploaded_files))
            
        status.success("¡Análisis completado!")
        df = pd.DataFrame(results)
        
        cols = ['ARCHIVO', 'FECHA_PERIODO', 'FECHA_VENCIMIENTO', 'NUMERO_FACTURA', 
                'NOMBRE', 'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
                'ALUMBRADO', 'INTERESES', 'POLIZA', 'MODELO']
        
        for c in cols:
            if c not in df.columns: df[c] = None
            
        st.dataframe(df[cols])
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[cols].to_excel(writer, index=False)
            
        st.download_button("📥 Descargar Excel Final", output.getvalue(), "Reporte_TripleA_IA_Fix.xlsx")
