import streamlit as st
import pdfplumber
import pandas as pd
import io
import re

st.set_page_config(page_title="Extractor Espacial Triple A", layout="wide")
st.title("🛡️ Extractor Triple A - Lógica Espacial")
st.warning("Este modelo usa la ubicación física del texto (Arriba/Abajo/Derecha) en lugar de adivinar.")

def clean_value(text):
    if not text: return 0.0
    # Limpieza dura para quitar letras que se cuelan
    text = str(text).upper().replace('S', '5').replace('O', '0').replace('B', '8')
    # Solo deja números, puntos y comas
    text = re.sub(r'[^\d,\.]', '', text)
    if not text: return 0.0
    
    # Decisión Colombia: Si hay punto al final con 3 digitos, es mil.
    # Ej: 1.000 -> 1000.0 | 1,000 -> 1000.0
    try:
        if ',' in text and '.' in text:
            text = text.replace('.', '').replace(',', '.')
        elif ',' in text:
            if len(text.split(',')[-1]) == 3: text = text.replace(',', '') # Miles
            else: text = text.replace(',', '.') # Decimal
        elif '.' in text:
             if len(text.split('.')[-1]) == 3: text = text.replace('.', '')
        return float(text)
    except: return 0.0

def get_text_below(lines, keyword, max_lines=2):
    """Busca una palabra y devuelve lo que está DEBAJO (para modelos viejos)."""
    for i, line in enumerate(lines):
        if keyword.upper() in line.upper():
            # Devuelve la primera línea no vacía que encuentre abajo
            for offset in range(1, max_lines + 1):
                if i + offset < len(lines):
                    candidate = lines[i + offset].strip()
                    if candidate: return candidate
    return None

def get_text_right(lines, keyword):
    """Busca una palabra y devuelve lo que está A LA DERECHA (para modelos nuevos)."""
    for line in lines:
        if keyword.upper() in line.upper():
            # Parte la línea usando la keyword como separador
            parts = re.split(keyword, line, flags=re.IGNORECASE)
            if len(parts) > 1:
                clean_part = parts[1].replace(":", "").strip()
                if clean_part: return clean_part
    return None

def extract_by_spatial_logic(file_obj, filename):
    data = {
        "ARCHIVO": filename,
        "FECHA PERIODO": None,        # Tu columna exacta
        "FECHA DE VENCIMIENTO": None, # Tu columna exacta
        "NUMERO_FACTURA": None,
        "VALOR_FACTURA": 0.0,
        "VALOR_TOTAL_DEUDA": 0.0,
        "POLIZA": None,
        "NOMBRE": None
    }
    
    try:
        # layout=True es vital para mantener la posición visual
        text_content = ""
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                text_content += (page.extract_text(layout=True) or "") + "\n"
    except: return data

    lines = text_layout = text_content.split('\n')
    upper_text = text_content.upper()

    # --- 1. DETECCIÓN DE MODELO ---
    es_legacy = False
    if "TOTAL A PAGAR" in upper_text and "PERIODO" not in upper_text:
        es_legacy = True # Modelos 2017-2020
    if re.search(r'[A-Z]{3}-\d{4}', upper_text):
        es_legacy = True # Modelos 2001 (Retro)

    # --- 2. EXTRACCIÓN SEGÚN "DE DONDE LA TOMAS" ---

    # == FECHA PERIODO ==
    # En tus facturas viejas, la fecha está DEBAJO del título "Período facturado".
    # En las nuevas, está al lado.
    if es_legacy:
        data['FECHA PERIODO'] = get_text_below(lines, "Período facturado")
    else:
        # En nuevas a veces dice "Periodo facturado" o solo está la fecha cerca de emisión
        val = get_text_right(lines, "Período facturado")
        if not val: val = get_text_right(lines, "Fecha de emisión") # Fallback nuevas
        data['FECHA PERIODO'] = val

    # == FECHA VENCIMIENTO ==
    # Viejas: Debajo de "Pague hasta"
    # Nuevas: Al lado de "Pague hasta"
    if es_legacy:
        data['FECHA DE VENCIMIENTO'] = get_text_below(lines, "Pague hasta")
        # A veces en Legacy hay basura, limpiamos si es muy largo
        if data['FECHA DE VENCIMIENTO'] and len(data['FECHA DE VENCIMIENTO']) > 20:
             # Intenta buscar a la derecha por si acaso cambió el formato
             data['FECHA DE VENCIMIENTO'] = get_text_right(lines, "Pague hasta")
    else:
        data['FECHA DE VENCIMIENTO'] = get_text_right(lines, "Pague hasta")

    # == NOMBRE ==
    # Viejas: Debajo de "Señor(a)"
    # Nuevas: A la derecha de "Nombre del cliente:"
    if es_legacy:
        data['NOMBRE'] = get_text_below(lines, "Señor(a)")
    else:
        data['NOMBRE'] = get_text_right(lines, "Nombre del cliente")

    # == POLIZA ==
    # Siempre está a la derecha de PÓLIZA
    data['POLIZA'] = get_text_right(lines, "PÓLIZA")

    # == FACTURA ==
    # Puede ser "Factura de servicios No." (vieja) o "No. de factura" (nueva)
    fac = get_text_right(lines, "Factura de servicios No.") # Vieja abajo/lado
    if not fac: fac = get_text_below(lines, "Factura de servicios No.") # Vieja abajo
    if not fac: fac = get_text_right(lines, "No. de factura") # Nueva
    if not fac: fac = get_text_right(lines, "Factura electrónica de venta") # Electronica
    
    # Limpieza del número de factura (quitar espacios)
    if fac: data['NUMERO_FACTURA'] = fac.split()[0] 

    # --- 3. VALORES (CRÍTICO) ---
    
    if es_legacy:
        # EN LEGACY: Tu columna VALOR_FACTURA toma el "Total a Pagar"
        # Buscamos la línea que tenga "Total a Pagar" y sacamos el último número
        for line in lines:
            if "TOTAL A PAGAR" in line.upper() and "PERIODO" not in line.upper():
                # En Legacy a veces hay puntos: "Total a pagar .......... $ 500"
                parts = line.split()
                # Buscamos de atrás para adelante
                for p in reversed(parts):
                    v = clean_value(p)
                    if v > 0:
                        data['VALOR_FACTURA'] = v
                        data['VALOR_TOTAL_DEUDA'] = v
                        break
    else:
        # EN NUEVAS:
        # VALOR_FACTURA = "TOTAL FACTURA SERVICIOS DEL PERIODO"
        # VALOR_TOTAL_DEUDA = "TOTAL FACTURA A PAGAR"
        for line in lines:
            if "TOTAL FACTURA SERVICIOS DEL PERIODO" in line.upper():
                data['VALOR_FACTURA'] = clean_value(line.split('$')[-1])
            
            if "TOTAL FACTURA A PAGAR" in line.upper():
                data['VALOR_TOTAL_DEUDA'] = clean_value(line.split('$')[-1])
                
    # --- 4. ALUMBRADO E INTERESES (Búsqueda línea por línea) ---
    for line in lines:
        if "ALUMBRADO" in line.upper():
            # El valor siempre es el último de la fila
            data['ALUMBRADO'] = clean_value(line.split()[-1])
        if "INTERESES DE MORA" in line.upper():
            data['INTERESES'] = clean_value(line.split()[-1])

    return data

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube los PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("Analizar con Lógica Espacial"):
        results = []
        bar = st.progress(0)
        for i, f in enumerate(uploaded_files):
            results.append(extract_by_spatial_logic(f, f.name))
            bar.progress((i+1)/len(uploaded_files))
            
        df = pd.DataFrame(results)
        
        # Columnas exactas que pediste
        cols = ['ARCHIVO', 'FECHA PERIODO', 'FECHA DE VENCIMIENTO', 'NUMERO_FACTURA', 'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 'ALUMBRADO', 'INTERESES', 'POLIZA', 'NOMBRE']
        
        # Validar existencia
        for c in cols: 
            if c not in df.columns: df[c] = None
            
        st.dataframe(df[cols])
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df[cols].to_excel(writer, index=False)
        st.download_button("Descargar Excel", buffer.getvalue(), "Reporte_TripleA_Espacial.xlsx")
