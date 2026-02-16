import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import time
import json

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Extractor IA Gemini", page_icon="✨", layout="wide")

st.title("✨ Extractor Triple A con Inteligencia Artificial (Gemini)")
st.markdown("""
Este sistema usa **Google Gemini 1.5 Flash** para "ver" y "entender" tus facturas. 
No usa coordenadas ni adivinanzas. Lee como una persona.
""")

# --- BARRA LATERAL PARA API KEY ---
with st.sidebar:
    st.header("🔑 Llave de Acceso")
    api_key = st.text_input("Pega tu Google API Key aquí", type="password", help="La que empieza por AIzaSy...")
    st.info("El modo gratuito permite aprox. 15 facturas por minuto.")

# --- FUNCIÓN QUE LLAMA A LA IA ---
def analizar_con_gemini(file_bytes, filename, api_key):
    # Configurar la IA con tu llave
    genai.configure(api_key=api_key)
    
    # Usamos el modelo Flash: Rápido, barato y muy capaz para documentos
    model = genai.GenerativeModel('gemini-1.5-flash')

    # EL PROMPT (LAS INSTRUCCIONES EXACTAS)
    # Aquí le decimos qué buscar, igual que en tu Excel
    prompt = """
    Actúa como un experto en extracción de datos contables.
    Analiza esta factura de servicios públicos (Triple A) y extrae la siguiente información en formato JSON.
    
    Reglas:
    - Si un valor no existe, devuelve null o 0.
    - Normaliza fechas a YYYY-MM-DD.
    - Normaliza dinero a número (sin signos $).
    - FECHA_PERIODO: Es el mes facturado (ej: "Abril 2023").
    - VALOR_FACTURA: Es el valor del consumo DEL MES ("Total servicios del periodo").
    - VALOR_TOTAL_DEUDA: Es el "Total a Pagar" o "Gran Total" (incluye deuda vieja).
    - NOMBRE: El nombre del suscriptor.
    
    JSON ESTRUCTURA:
    {
        "ARCHIVO": "nombre_archivo",
        "FECHA_PERIODO": "texto",
        "FECHA_VENCIMIENTO": "texto",
        "NUMERO_FACTURA": "texto",
        "NOMBRE": "texto",
        "VALOR_FACTURA": float,
        "VALOR_TOTAL_DEUDA": float,
        "ALUMBRADO": float,
        "INTERESES": float,
        "POLIZA": "texto",
        "MODELO": "texto (indica si es VIEJA, NUEVA o ELECTRONICA)"
    }
    """

    try:
        # Enviamos el PDF a la IA
        response = model.generate_content([
            {'mime_type': 'application/pdf', 'data': file_bytes},
            prompt
        ])
        
        # Limpiamos la respuesta para sacar solo el JSON
        raw_text = response.text
        # A veces la IA pone ```json al principio, lo quitamos
        json_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(json_text)
        data['ARCHIVO'] = filename # Aseguramos el nombre
        return data

    except Exception as e:
        # Si falla (ej: archivo corrupto), devolvemos el error
        return {"ARCHIVO": filename, "NOMBRE": f"ERROR: {str(e)}"}

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube tus 199 Facturas PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if not api_key:
        st.warning("⚠️ ¡Ojo! Necesitas pegar tu API Key a la izquierda para arrancar.")
    else:
        if st.button(f"🚀 Iniciar Extracción IA ({len(uploaded_files)} Docs)"):
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, f in enumerate(uploaded_files):
                status_text.text(f"Analizando {i+1}/{len(uploaded_files)}: {f.name}...")
                
                # Leemos el archivo
                bytes_data = f.getvalue()
                
                # Llamamos a Gemini
                data = analizar_con_gemini(bytes_data, f.name, api_key)
                results.append(data)
                
                # PAUSA OBLIGATORIA (Rate Limit)
                # Google Free Tier te deja hacer unas 15 por minuto.
                # Esperamos 4 segundos entre cada una para no bloquearnos.
                time.sleep(4) 
                
                progress_bar.progress((i+1)/len(uploaded_files))
            
            status_text.success("¡Listo el pollo! La IA leyó todo.")
            
            # Tabla Final
            df = pd.DataFrame(results)
            
            # Orden de columnas como tu Excel
            cols = [
                'ARCHIVO', 'FECHA_PERIODO', 'FECHA_VENCIMIENTO', 
                'NUMERO_FACTURA', 'NOMBRE', 
                'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
                'ALUMBRADO', 'INTERESES', 'POLIZA', 'MODELO'
            ]
            
            # Rellenar columnas que falten
            for c in cols:
                if c not in df.columns: df[c] = None
            
            st.dataframe(df[cols])
            
            # Botón Descarga
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df[cols].to_excel(writer, index=False)
            
            st.download_button(
                label="📥 Descargar Excel Inteligente",
                data=buffer.getvalue(),
                file_name="Reporte_Gemini_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
