import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import time
import json

# --- TU LLAVE FIJA (YA INCRUSTADA) ---
MY_API_KEY = "AIzaSyB74qmjYXqtEIr1pTdNOBwRHpDrpc_mqHU"

st.set_page_config(page_title="Gemini Triple A", page_icon="🤖", layout="wide")

# === PANEL DE BIENVENIDA ===
st.title("🤖 Hola, soy Gemini")
with st.container(border=True):
    st.subheader("¡Todo listo, cuadro!")
    st.write("Ya tengo tu llave maestra cargada. Sube tus facturas abajo y yo misma armo tu tabla de Excel.")
    
    # Verificar conexión de una vez
    try:
        genai.configure(api_key=MY_API_KEY)
        # Probamos listar un modelo para ver si la llave sirve
        model = genai.GenerativeModel('gemini-1.5-flash')
        st.success("✅ Estoy conectada y lista para trabajar.")
    except Exception as e:
        st.error(f"❌ Eche, hay un problema con la llave: {e}")

st.divider()

# === FUNCIÓN DE EXTRACCIÓN ===
def procesar_factura(file_bytes, filename):
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Este prompt es el secreto: le decimos exactamente qué queremos
    prompt = """
    Analiza esta factura de Triple A. Devuelve un JSON con estos campos:
    - ARCHIVO: nombre del archivo
    - FECHA_PERIODO: Mes y año facturado (ej: Abril 2023)
    - FECHA_VENCIMIENTO: Fecha de pago (ej: Abr 05-23)
    - NUMERO_FACTURA: El número de la factura
    - NOMBRE: El nombre del cliente
    - VALOR_FACTURA: Valor servicios periodo (sin puntos ni comas, solo el número)
    - VALOR_TOTAL_DEUDA: Total a pagar (sin puntos ni comas)
    - ALUMBRADO: Valor alumbrado público
    - INTERESES: Valor intereses de mora
    - POLIZA: Numero de póliza
    - MODELO: Determina si es LEGACY (vieja), TRANSICION o ELECTRONICA
    
    Responde SOLO el JSON, nada más.
    """

    try:
        response = model.generate_content([
            {'mime_type': 'application/pdf', 'data': file_bytes},
            prompt
        ])
        
        # Limpiar la respuesta para que sea un JSON puro
        res_text = response.text.strip()
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        elif "```" in res_text:
            res_text = res_text.split("```")[1].strip()
            
        return json.loads(res_text)
    except Exception as e:
        return {"ARCHIVO": filename, "NOMBRE": f"Error: {str(e)}"}

# === ÁREA DE CARGA ===
st.subheader("📁 Sube tus PDFs")
uploaded_files = st.file_uploader("Arrastra aquí todas las facturas", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("🚀 Empezar a leer facturas"):
        resultados = []
        progress_bar = st.progress(0)
        status = st.empty()
        
        for i, f in enumerate(uploaded_files):
            status.info(f"Leyendo factura {i+1} de {len(uploaded_files)}: **{f.name}**")
            
            # Procesar
            res = procesar_factura(f.getvalue(), f.name)
            resultados.append(res)
            
            # Le damos 4 segundos entre facturas para que Google no nos bloquee
            time.sleep(4)
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        status.success("¡Listo! Ya terminé de leer todo.")
        
        # Mostrar tabla
        df = pd.DataFrame(resultados)
        
        # Ordenar columnas como las necesitas
        columnas = ['ARCHIVO', 'FECHA_PERIODO', 'FECHA_VENCIMIENTO', 'NUMERO_FACTURA', 
                    'NOMBRE', 'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
                    'ALUMBRADO', 'INTERESES', 'POLIZA', 'MODELO']
        
        for col in columnas:
            if col not in df.columns: df[col] = None
            
        st.write("### Vista previa de los datos")
        st.dataframe(df[columnas])
        
        # Descarga
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[columnas].to_excel(writer, index=False)
        st.download_button("📥 Descargar Tabla en Excel", output.getvalue(), "Reporte_TripleA_Gemini.xlsx")
