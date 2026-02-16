import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import time
import json

# --- TU LLAVE MAESTRA ---
MY_API_KEY = "AIzaSyB74qmjYXqtEIr1pTdNOBwRHpDrpc_mqHU"

st.set_page_config(page_title="Extractor IA Triple A - Versión Pro", page_icon="💎", layout="wide")

st.title("💎 Extractor Triple A - Inteligencia Artificial (Modo Estable)")
st.markdown("Configurado para usar la API estable y evitar errores 404.")

def analizar_factura_ia(file_bytes, filename):
    # Forzamos la configuración a la versión estable
    genai.configure(api_key=MY_API_KEY)
    
    prompt = f"""
    Actúa como un experto contable senior. Analiza esta factura de Triple A Barranquilla y extrae los datos exactos en formato JSON.
    
    CAMPOS PARA EL JSON:
    - ARCHIVO: "{filename}"
    - FECHA_PERIODO: Mes y año facturado (ej: Abril 2023).
    - FECHA_VENCIMIENTO: Fecha "Pague hasta".
    - NUMERO_FACTURA: El número de la factura.
    - NOMBRE: Nombre completo del cliente.
    - VALOR_FACTURA: Consumo del mes (Servicios del periodo).
    - VALOR_TOTAL_DEUDA: Gran total a pagar.
    - ALUMBRADO: Impuesto de alumbrado público.
    - INTERESES: Intereses de mora.
    - POLIZA: Número de Póliza.
    - MODELO: Detecta si es LEGACY, TRANSICION o ELECTRONICA.

    REGLAS:
    - Responde ÚNICAMENTE con el JSON puro.
    - Si no encuentras un valor, pon 0.
    """

    # Probamos primero con 1.5-flash (que es el más compatible) 
    # y luego con 1.5-pro (que es el que estás pagando)
    modelos_disponibles = ['gemini-1.5-flash', 'gemini-1.5-pro']
    
    for nombre_modelo in modelos_disponibles:
        try:
            # Especificamos el modelo sin prefijos raros
            model = genai.GenerativeModel(model_name=nombre_modelo)
            
            response = model.generate_content([
                {'mime_type': 'application/pdf', 'data': file_bytes},
                prompt
            ])
            
            # Limpieza de la respuesta para asegurar JSON válido
            res_text = response.text.strip()
            if "```" in res_text:
                res_text = res_text.split("```")[1]
                if res_text.startswith("json"):
                    res_text = res_text[4:]
            
            return json.loads(res_text.strip())
            
        except Exception as e:
            # Si es el último intento y falla, reportamos el error
            if nombre_modelo == modelos_disponibles[-1]:
                return {"ARCHIVO": filename, "NOMBRE": f"ERROR API FINAL: {str(e)}", "VALOR_TOTAL_DEUDA": 0}
            continue

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube tus PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🚀 Procesar {len(uploaded_files)} Facturas"):
        results = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, f in enumerate(uploaded_files):
            status.text(f"Analizando con Gemini Pro: {f.name}...")
            res = analizar_factura_ia(f.getvalue(), f.name)
            results.append(res)
            
            # Pausa técnica para evitar bloqueos
            time.sleep(2) 
            bar.progress((i + 1) / len(uploaded_files))
            
        status.success("¡Análisis completado exitosamente!")
        df = pd.DataFrame(results)
        
        # Columnas según tu requerimiento
        cols = ['ARCHIVO', 'FECHA_PERIODO', 'FECHA_VENCIMIENTO', 'NUMERO_FACTURA', 
                'NOMBRE', 'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
                'ALUMBRADO', 'INTERESES', 'POLIZA', 'MODELO']
        
        for c in cols:
            if c not in df.columns: df[c] = None
            
        st.dataframe(df[cols])
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[cols].to_excel(writer, index=False)
            
        st.download_button("📥 Descargar Excel Final", output.getvalue(), "Reporte_TripleA_Pro_Fix.xlsx")
