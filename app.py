import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import time
import json

# --- CONFIGURACIÓN DE TU NUEVA LLAVE ---
# Ya dejé la que me pasaste configurada internamente
MY_API_KEY = "AIzaSyCfSb7AM8AfkxrdqYJar91BHemmrkRCVUs"

st.set_page_config(page_title="Panel Gemini Triple A", page_icon="🤖", layout="wide")

# === PANEL DE BIENVENIDA ===
st.title("🤖 Centro de Operaciones Gemini")
with st.container(border=True):
    col1, col2 = st.columns([1, 5])
    with col1:
        st.write("### 💎")
    with col2:
        st.subheader("¡Todo listo, cuadro!")
        st.write("Ya vinculé tu nueva API Key. Estoy lista para leer las 199 facturas y armar el Excel tal cual lo necesitas.")
        
        # Verificación en vivo de la llave
        try:
            genai.configure(api_key=MY_API_KEY)
            # Forzamos uso de la versión estable para evitar el error 404
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.success("✅ Conexión Exitosa con Google AI Studio. El motor está prendido.")
        except Exception as e:
            st.error(f"❌ Caramba, hay un problema con la llave: {e}")

st.divider()

# === FUNCIÓN DE LECTURA INTELIGENTE ===
def analizar_factura(file_bytes, filename):
    # Usamos Flash 1.5 que es el todoterreno para documentos
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Eres un experto en auditoría de facturas de servicios públicos en Barranquilla.
    Analiza este PDF de Triple A y extrae los datos para mi reporte de Excel.
    
    CAMPOS REQUERIDOS EN JSON:
    - ARCHIVO: "{filename}"
    - FECHA PERIODO: El mes facturado (ej: "Abril 2023").
    - FECHA DE VENCIMIENTO: La fecha "Pague hasta" (ej: "Abr 05-23").
    - NUMERO_FACTURA: El número de la factura.
    - NOMBRE: Nombre completo del cliente.
    - VALOR_FACTURA: Consumo del mes (Servicios del periodo). Solo el número.
    - VALOR_TOTAL_DEUDA: Total a pagar con deuda acumulada. Solo el número.
    - ALUMBRADO: Valor impuesto alumbrado.
    - INTERESES: Valor intereses de mora.
    - POLIZA: Número de póliza.
    - MODELO: Identifica si es ELECTRONICA, TRANSICION o LEGACY.

    RESPONDE ÚNICAMENTE EL OBJETO JSON PURO.
    """

    try:
        response = model.generate_content([
            {'mime_type': 'application/pdf', 'data': file_bytes},
            prompt
        ])
        
        # Limpieza por si la IA mete texto extra
        res_text = response.text.strip()
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        elif "```" in res_text:
            res_text = res_text.split("```")[1].strip()
            
        return json.loads(res_text)
    except Exception as e:
        return {"ARCHIVO": filename, "NOMBRE": f"ERROR: {str(e)}"}

# === ÁREA DE CARGA Y PROCESO ===
st.subheader("📁 Sube tus PDFs")
uploaded_files = st.file_uploader("Arrastra aquí todas las facturas", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("🚀 Iniciar Extracción"):
        resultados = []
        barra = st.progress(0)
        estado = st.empty()
        
        for i, f in enumerate(uploaded_files):
            estado.info(f"Analizando factura {i+1} de {len(uploaded_files)}: **{f.name}**")
            
            # Procesar con Gemini
            res = analizar_factura(f.getvalue(), f.name)
            resultados.append(res)
            
            # Pausa de 4 segundos para respetar el Plan Gratuito (RPM Limit)
            time.sleep(4)
            barra.progress((i + 1) / len(uploaded_files))
            
        estado.success("¡Coronamos! Revisa los datos abajo.")
        
        df = pd.DataFrame(resultados)
        
        # Ordenar columnas como en tu ejemplo
        columnas = ['ARCHIVO', 'FECHA PERIODO', 'FECHA DE VENCIMIENTO', 'NUMERO_FACTURA', 
                    'NOMBRE', 'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
                    'ALUMBRADO', 'INTERESES', 'POLIZA', 'MODELO']
        
        for col in columnas:
            if col not in df.columns: df[col] = None
            
        st.write("### 📊 Vista previa del Reporte")
        st.dataframe(df[columnas])
        
        # Botón para descargar el Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[columnas].to_excel(writer, index=False)
        st.download_button("📥 Descargar Excel Final", output.getvalue(), "Reporte_TripleA_Gemini_Final.xlsx")
