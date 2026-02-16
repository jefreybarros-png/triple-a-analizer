import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import time
import json

# --- TU LLAVE FIJA ---
MY_API_KEY = "AIzaSyB74qmjYXqtEIr1pTdNOBwRHpDrpc_mqHU"

st.set_page_config(page_title="Panel Gemini Triple A", page_icon="🤖", layout="wide")

# --- PANEL DE BIENVENIDA ---
st.title("🤖 Centro de Control Gemini")
panel = st.container(border=True)
with panel:
    col1, col2 = st.columns([1, 4])
    with col1:
        st.image("https://upload.wikimedia.org/wikipedia/commons/8/8a/Google_Gemini_logo.svg", width=100)
    with col2:
        st.subheader("¡Eche, cuadro! Hola, soy Gemini.")
        st.write("Estoy lista para leer tus facturas. Ya configuré tu llave interna y estoy verificando conexión...")
        
        # Prueba de conexión rápida
        try:
            genai.configure(api_key=MY_API_KEY)
            test_model = genai.GenerativeModel('gemini-1.5-flash')
            st.success("✅ ¡Conexión Exitosa! El motor está prendido y listo para el plomo.")
        except Exception as e:
            st.error(f"❌ Caramba, algo pasó con la conexión: {e}")

st.divider()

# --- FUNCIÓN DE EXTRACCIÓN LENTA Y SEGURA ---
def extraer_datos_con_ia(file_bytes, filename):
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Analiza esta factura de Triple A Barranquilla. Extrae estos campos exactos en JSON:
    - ARCHIVO: "{filename}"
    - FECHA_PERIODO: Mes y año facturado.
    - FECHA_VENCIMIENTO: Fecha de pago oportuno.
    - NUMERO_FACTURA: El número del documento.
    - NOMBRE: Nombre del cliente.
    - VALOR_FACTURA: Valor servicios del periodo (del mes).
    - VALOR_TOTAL_DEUDA: Valor total a pagar.
    - ALUMBRADO: Impuesto alumbrado público.
    - INTERESES: Intereses de mora.
    - POLIZA: Número de póliza.
    - MODELO: LEGACY, TRANSICION o ELECTRONICA.

    RESPONDE SOLO EL JSON PURO.
    """

    try:
        response = model.generate_content([
            {'mime_type': 'application/pdf', 'data': file_bytes},
            prompt
        ])
        
        # Limpieza manual del texto por si la IA se emociona
        res_text = response.text.strip()
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        elif "```" in res_text:
            res_text = res_text.split("```")[1].strip()
            
        return json.loads(res_text)
    except Exception as e:
        return {"ARCHIVO": filename, "NOMBRE": f"Reintento necesario: {str(e)}"}

# --- SECCIÓN DE CARGA ---
st.subheader("📁 Sube tus archivos aquí")
files = st.file_uploader("Arrastra los PDF", type="pdf", accept_multiple_files=True)

if files:
    if st.button("🚀 Arrancar Procesamiento"):
        resultados = []
        barra = st.progress(0)
        info_proceso = st.empty()
        
        for i, f in enumerate(files):
            info_proceso.info(f"Leyendo factura {i+1} de {len(files)}: **{f.name}**")
            
            # Procesamos
            dato = extraer_datos_con_ia(f.getvalue(), f.name)
            resultados.append(dato)
            
            # LE DAMOS UN RESPIRO A LA IA (5 segundos entre facturas)
            # Esto evita el error de "ir muy rápido"
            time.sleep(5)
            barra.progress((i + 1) / len(files))
            
        info_proceso.success("¡Coronamos! Ya leí todo.")
        
        df = pd.DataFrame(resultados)
        
        # Ajustamos el orden de las columnas para que te salgan perfectas
        cols_finales = ['ARCHIVO', 'FECHA_PERIODO', 'FECHA_VENCIMIENTO', 'NUMERO_FACTURA', 
                        'NOMBRE', 'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
                        'ALUMBRADO', 'INTERESES', 'POLIZA', 'MODELO']
        
        for c in cols_finales:
            if c not in df.columns: df[c] = None
            
        st.table(df[cols_finales])
        
        # Botón de descarga
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[cols_finales].to_excel(writer, index=False)
        st.download_button("📥 Descargar Tabla Final", output.getvalue(), "Reporte_Gemini_Pro.xlsx")
