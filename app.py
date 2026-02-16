import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import time
import json

# --- CONFIGURACIÓN DE SEGURIDAD Y API ---
# Tu llave ya queda incrustada aquí
MY_API_KEY = "AIzaSyB74qmjYXqtEIr1pTdNOBwRHpDrpc_mqHU"

st.set_page_config(page_title="Extractor IA Triple A - Pro", page_icon="🤖", layout="wide")

st.title("🤖 Extractor Triple A - Inteligencia Artificial")
st.markdown("Sube tus archivos y la IA se encarga de todo. API Key configurada internamente.")

# --- FUNCIÓN DE EXTRACCIÓN ---
def analizar_factura_ia(file_bytes, filename):
    genai.configure(api_key=MY_API_KEY)
    
    # Instrucciones precisas para la IA
    prompt = f"""
    Actúa como un experto contable. Analiza esta factura de Triple A Barranquilla y extrae los datos exactos.
    IMPORTANTE: Si el dato está en una tabla, léelo de la fila correspondiente.
    
    CAMPOS OBLIGATORIOS PARA EL JSON:
    - ARCHIVO: "{filename}"
    - FECHA_PERIODO: El "Período facturado" (ej: Abril 2023).
    - FECHA_VENCIMIENTO: La fecha "Pague hasta" (ej: Abr 05-23).
    - NUMERO_FACTURA: El número de la factura (No. de factura o Factura No.).
    - NOMBRE: Nombre completo del cliente/suscriptor.
    - VALOR_FACTURA: Consumo del mes (TOTAL FACTURA SERVICIOS DEL PERIODO).
    - VALOR_TOTAL_DEUDA: Gran total a pagar (TOTAL FACTURA A PAGAR).
    - ALUMBRADO: Valor del Alumbrado Público.
    - INTERESES: Valor de Intereses de Mora.
    - POLIZA: Número de Póliza.
    - MODELO: Detecta si es LEGACY, TRANSICION o ELECTRONICA.

    REGLAS:
    - Responde ÚNICAMENTE con el objeto JSON.
    - No uses markdown ni bloques de código.
    - Si un valor monetario no existe, pon 0.
    """

    # Intentar con flash (rápido), si falla ir a pro (robusto)
    modelos_a_probar = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro-vision']
    
    for nombre_modelo in modelos_a_probar:
        try:
            model = genai.GenerativeModel(nombre_modelo)
            response = model.generate_content([
                {'mime_type': 'application/pdf', 'data': file_bytes},
                prompt
            ])
            
            # Limpiar y parsear JSON
            res_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(res_text)
        except Exception as e:
            if nombre_modelo == modelos_a_probar[-1]: # Si es el último intento
                return {"ARCHIVO": filename, "NOMBRE": f"ERROR: {str(e)}", "VALOR_TOTAL_DEUDA": 0}
            continue # Probar el siguiente modelo

# --- INTERFAZ STREAMLIT ---
uploaded_files = st.file_uploader("Arrastra aquí tus facturas PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🚀 Procesar {len(uploaded_files)} Facturas"):
        results = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, f in enumerate(uploaded_files):
            status.text(f"Analizando: {f.name}...")
            
            # Procesar factura
            resultado = analizar_factura_ia(f.getvalue(), f.name)
            results.append(resultado)
            
            # Pausa de seguridad para no saturar la API gratuita
            time.sleep(3)
            bar.progress((i + 1) / len(uploaded_files))
            
        status.success("¡Proceso completado!")
        
        df = pd.DataFrame(results)
        
        # Reordenar columnas según tu Excel de referencia
        cols = ['ARCHIVO', 'FECHA_PERIODO', 'FECHA_VENCIMIENTO', 'NUMERO_FACTURA', 
                'NOMBRE', 'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
                'ALUMBRADO', 'INTERESES', 'POLIZA', 'MODELO']
        
        # Asegurar que todas existan
        for c in cols:
            if c not in df.columns: df[c] = None
            
        st.dataframe(df[cols])
        
        # Generar Excel para descarga
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[cols].to_excel(writer, index=False)
            
        st.download_button(
            label="📥 Descargar Reporte Final Excel",
            data=output.getvalue(),
            file_name="Reporte_TripleA_IA_Pro.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
