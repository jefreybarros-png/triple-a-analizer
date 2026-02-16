import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Analizador Triple A - Master", page_icon="💧", layout="wide")

st.title("💧 Analizador Triple A - Suite Completa")
st.markdown("Usa la pestaña **'Radiografía'** para diagnosticar facturas rebeldes.")

# --- LÓGICA DE EXTRACCIÓN (MOTOR) ---
def clean_money(text):
    if not text: return 0.0
    # Limpieza OCR (S->5, B->8, O->0)
    text = str(text).upper().replace('S', '5').replace('O', '0').replace('B', '8')
    # Buscar el patrón de moneda
    matches = re.findall(r'[\d\.,]+', text)
    if not matches: return 0.0
    
    # Tomar el candidato más largo (evita tomar un "1" de número de página)
    best_match = max(matches, key=len)
    clean = best_match
    
    # Normalización Colombia (Manejo de miles y decimales)
    if ',' in clean and '.' in clean:
        clean = clean.replace('.', '').replace(',', '.')
    elif ',' in clean:
        if len(clean.split(',')[-1]) == 3: clean = clean.replace(',', '')
        else: clean = clean.replace(',', '.')
    elif '.' in clean:
         if len(clean.split('.')[-1]) == 3: clean = clean.replace('.', '')
    
    try: return float(clean)
    except: return 0.0

def parse_date(text):
    try:
        # Formatos: 24-Abr-2023 | 24/04/2023 | ABR-2001
        match = re.search(r'(\d{1,2})[-/\s]+([A-Za-z]{3,}|\d{2})[-/\s]+(\d{2,4})', text)
        if match: return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
        
        match_old = re.search(r'([A-Z]{3})[-/\s]+(\d{4})', text, re.IGNORECASE)
        if match_old: return f"{match_old.group(2)}-{match_old.group(1)}-01"
    except: pass
    return None

def analyze_pdf_structure(file_obj, filename):
    """Analiza el PDF y devuelve datos + reporte de debug."""
    debug_info = []
    data = {"ARCHIVO": filename, "MODELO": "Desconocido"}
    
    try:
        text_layout = ""
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                text_layout += (page.extract_text(layout=True) or "") + "\n"
    except Exception as e:
        return data, f"Error leyendo PDF: {e}", ""

    # 1. DETECCIÓN DE MODELO
    upper_text = text_layout.upper()
    
    if "ESTADO DE CUENTA" in upper_text:
        data["MODELO"] = "ESTADO DE CUENTA"
    elif "CUFE:" in upper_text or "FACTURA ELECTRÓNICA" in upper_text:
        data["MODELO"] = "ELECTRÓNICA (2024-25)"
    elif "TOTAL FACTURA SERVICIOS DEL PERIODO" in upper_text:
        data["MODELO"] = "TRANSICIÓN (2023)"
    elif re.search(r'[A-Z]{3}-\d{4}', upper_text):
        data["MODELO"] = "RETRO (2001-2002)"
    else:
        data["MODELO"] = "LEGACY (2017-2020)"
    
    debug_info.append(f"✅ Modelo Detectado: {data['MODELO']}")

    # 2. EXTRACCIÓN (Estrategia según modelo)
    lines = text_layout.split('\n')
    
    # -- PÓLIZA (Común) --
    m_poliza = re.search(r'PÓLIZA[:\s]*(\d+)', upper_text)
    data['POLIZA'] = m_poliza.group(1) if m_poliza else "No encontrada"

    # -- ESTRATEGIA ESPECÍFICA --
    if data["MODELO"] == "ELECTRÓNICA (2024-25)" or data["MODELO"] == "TRANSICIÓN (2023)":
        # En las nuevas, buscamos la etiqueta exacta y tomamos el valor de esa línea
        for line in lines:
            if "TOTAL FACTURA SERVICIOS DEL PERIODO" in line.upper():
                val = clean_money(line.split('$')[-1]) # Tomar lo que está después del signo peso
                data['VALOR_CONSUMO_MES'] = val
                debug_info.append(f"  -> Consumo Mes encontrado en línea: '{line.strip()}' = {val}")
            
            if "TOTAL FACTURA A PAGAR" in line.upper():
                val = clean_money(line.split('$')[-1])
                data['VALOR_TOTAL_DEUDA'] = val
                debug_info.append(f"  -> Total Deuda encontrado en línea: '{line.strip()}' = {val}")

            if "FACTURA DE VENTA" in line.upper() or "NO. DE FACTURA" in line.upper():
                # Buscar código alfanumérico
                m = re.search(r'([A-Z0-9]+)$', line.strip())
                if m: data['NUMERO_FACTURA'] = m.group(1)

    elif data["MODELO"] == "LEGACY (2017-2020)":
        # En las viejas, "Total a Pagar" es la clave
        for line in lines:
            if "TOTAL A PAGAR" in line.upper() and "PERIODO" not in line.upper():
                # A veces hay puntos suspensivos "Total .... $ 500"
                parts = line.split()
                # Buscamos de atrás hacia adelante el primer número válido
                for part in reversed(parts):
                    val = clean_money(part)
                    if val > 100: # Filtro de ruido
                        data['VALOR_TOTAL_DEUDA'] = val
                        data['VALOR_CONSUMO_MES'] = val # Asumimos igual
                        debug_info.append(f"  -> Total Legacy encontrado: '{line.strip()}' = {val}")
                        break
            
            if "FACTURA DE SERVICIOS NO" in line.upper():
                nums = re.findall(r'\d+', line)
                if nums: data['NUMERO_FACTURA'] = nums[-1]

    elif data["MODELO"] == "RETRO (2001-2002)":
         # Búsqueda global de fecha tipo ABR-2001
         m_fecha = re.search(r'([A-Z]{3}[-/\s]\d{4})', upper_text)
         if m_fecha: data['FECHA'] = m_fecha.group(1)
         
         # El valor suele ser el número más grande al final del documento
         precios = re.findall(r'\$\s?([\d\.,]{4,})', upper_text)
         if precios:
             vals = [clean_money(p) for p in precios]
             data['VALOR_TOTAL_DEUDA'] = max(vals)
             debug_info.append(f"  -> Precio Retro (Max encontrado): {data['VALOR_TOTAL_DEUDA']}")

    # -- FECHA (Si no se encontró antes) --
    if 'FECHA' not in data or not data['FECHA']:
         for line in lines:
             if "FECHA DE EMISIÓN" in line.upper() or "FECHA Y HORA" in line.upper():
                 data['FECHA'] = parse_date(line)
                 break

    # Rellenar vacíos
    for k in ['VALOR_CONSUMO_MES', 'VALOR_TOTAL_DEUDA', 'ALUMBRADO', 'INTERESES']:
        if k not in data: data[k] = 0.0

    return data, debug_info, text_layout


# --- INTERFAZ DE USUARIO (TABS) ---
tab1, tab2 = st.tabs(["🚀 Extractor Masivo", "🩻 Radiografía (Debug)"])

# === PESTAÑA 1: EXTRACTOR MASIVO ===
with tab1:
    st.header("Carga Masiva de Facturas")
    files = st.file_uploader("Arrastra aquí tus 199 archivos", type="pdf", accept_multiple_files=True, key="uploader_masivo")
    
    if files:
        if st.button("Procesar Todo"):
            results = []
            bar = st.progress(0)
            for i, f in enumerate(files):
                data, _, _ = analyze_pdf_structure(f, f.name)
                results
