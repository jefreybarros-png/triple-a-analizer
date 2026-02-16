import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Analizador Triple A - Estructural Final", page_icon="💧", layout="wide")

st.title("💧 Analizador Triple A - Reporte Idéntico")
st.markdown("Extracción precisa basada en tu estructura de Excel (Período, Vencimiento, Nombre, Deuda).")

# --- UTILIDADES DE LIMPIEZA ---
def clean_money(text):
    """Convierte texto de dinero a float."""
    if not text: return 0.0
    # Limpieza de OCR
    text = str(text).upper().replace('S', '5').replace('O', '0').replace('B', '8').replace("'", "")
    # Buscar patrón numérico
    matches = re.findall(r'[\d\.,]+', text)
    if not matches: return 0.0
    
    # Tomar el candidato más largo
    best_match = max(matches, key=len)
    clean = best_match
    
    # Lógica Colombia (Miles = . / Decimales = ,) o viceversa
    if ',' in clean and '.' in clean:
        clean = clean.replace('.', '').replace(',', '.')
    elif ',' in clean:
        if len(clean.split(',')[-1]) == 3: clean = clean.replace(',', '') # Es miles
        else: clean = clean.replace(',', '.') # Es decimal
    elif '.' in clean:
         if len(clean.split('.')[-1]) == 3: clean = clean.replace('.', '') # Es miles
    
    try: return float(clean)
    except: return 0.0

def extract_field_next_line(lines, keyword):
    """Busca una palabra clave y devuelve la línea INMEDIATAMENTE SIGUIENTE."""
    for i, line in enumerate(lines):
        if keyword.upper() in line.upper():
            if i + 1 < len(lines):
                return lines[i+1].strip()
    return ""

def extract_field_same_line(lines, keyword):
    """Busca una palabra clave y devuelve lo que está a la derecha en la misma línea."""
    for line in lines:
        if keyword.upper() in line.upper():
            # Devuelve todo lo que está después de la keyword
            # Ej: "Pague hasta: Abr 05-23" -> "Abr 05-23"
            parts = re.split(keyword, line, flags=re.IGNORECASE)
            if len(parts) > 1:
                return parts[1].strip().replace(":", "").strip()
    return ""

def analyze_pdf_final(file_obj, filename):
    data = {
        "ARCHIVO": filename,
        "FECHA PERIODO": None,
        "FECHA DE VENCIMIENTO": None,
        "NUMERO_FACTURA": None,
        "VALOR_FACTURA": 0.0,      # Consumo del mes
        "VALOR_TOTAL_DEUDA": 0.0,  # Total a Pagar
        "ALUMBRADO": 0.0,
        "INTERESES": 0.0,
        "POLIZA": None,
        "NOMBRE": None
    }
    
    try:
        text_layout = ""
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                text_layout += (page.extract_text(layout=True) or "") + "\n"
    except Exception as e:
        return data

    lines = text_layout.split('\n')
    upper_text = text_layout.upper()

    # --- 1. EXTRACCIÓN DE CABECERA (NOMBRE, POLIZA, FACTURA) ---
    
    # POLIZA (Universal)
    m_pol = re.search(r'PÓLIZA[:\s]*(\d+)', upper_text)
    if m_pol: data['POLIZA'] = m_pol.group(1)

    # NOMBRE (Lógica Híbrida)
    # Intento 1: Etiqueta "Nombre del cliente:" (Nuevas)
    nom = extract_field_next_line(lines, "Nombre del cliente")
    if nom and len(nom) > 3: 
        data['NOMBRE'] = nom
    else:
        # Intento 2: Debajo de "Señor(a)" (Viejas)
        nom = extract_field_next_line(lines, "Señor(a)")
        if nom: data['NOMBRE'] = nom

    # NUMERO DE FACTURA
    # Busca "No." seguido de digitos
    m_fac = re.search(r'(?:Factura|No\.)\s*(?:de)?\s*(?:servicios|venta)?\s*(?:No\.?)?[:\s]*([A-Z0-9]+)', upper_text)
    if m_fac: data['NUMERO_FACTURA'] = m_fac.group(1)

    # --- 2. EXTRACCIÓN DE FECHAS (EXACTAS) ---
    
    # FECHA PERIODO (Busca "Período facturado" y toma la linea siguiente o misma linea)
    per = extract_field_next_line(lines, "Período facturado")
    if not per: per = extract_field_same_line(lines, "Período facturado")
    data['FECHA PERIODO'] = per

    # FECHA VENCIMIENTO (Busca "Pague hasta")
    venc = extract_field_next_line(lines, "Pague hasta")
    if not venc or len(venc) > 20: # Si es muy largo o vacio, intenta misma linea
         venc = extract_field_same_line(lines, "Pague hasta")
    data['FECHA DE VENCIMIENTO'] = venc

    # --- 3. EXTRACCIÓN DE VALORES (SEGÚN TU CSV) ---

    # ALUMBRADO E INTERESES (Universal)
    for line in lines:
        if "ALUMBRADO" in line.upper():
            data['ALUMBRADO'] = clean_money(line.split('$')[-1])
        if "INTERESES DE MORA" in line.upper():
            # A veces el interés está al final de la linea
            vals = re.findall(r'[\d\.,]+', line)
            if vals: data['INTERESES'] = clean_money(vals[-1])

    # VALORES PRINCIPALES (Distinción Modelo Nuevo vs Viejo)
    
    if "TOTAL FACTURA SERVICIOS DEL PERIODO" in upper_text:
        # === MODELO NUEVO (2023-2025) ===
        for line in lines:
            if "TOTAL FACTURA SERVICIOS DEL PERIODO" in line.upper():
                data['VALOR_FACTURA'] = clean_money(line.split('$')[-1])
            
            if "TOTAL FACTURA A PAGAR" in line.upper():
                data['VALOR_TOTAL_DEUDA'] = clean_money(line.split('$')[-1])
            
            # A veces dice "TOTAL DEUDA" aparte
            if "TOTAL DEUDA" in line.upper() and data['VALOR_TOTAL_DEUDA'] == 0:
                 data['VALOR_TOTAL_DEUDA'] = clean_money(line.split('$')[-1])

    else:
        # === MODELO VIEJO (Legacy) ===
        # En el viejo, "Total a Pagar" suele ser el valor de la factura DEL MES si no hay deuda,
        # pero si hay deuda, es el total. 
        # Tu CSV muestra que para 'marzo2017' VALOR_FACTURA es 1.419.467 (que es el total grande).
        
        for line in lines:
            if "TOTAL A PAGAR" in line.upper() and "PERIODO" not in line.upper():
                parts = line.split()
                # Buscar el último número válido de la línea
                for part in reversed(parts):
                    val = clean_money(part)
                    if val > 100:
                        data['VALOR_FACTURA'] = val      # En legacy asumimos este como principal
                        data['VALOR_TOTAL_DEUDA'] = val  # Y también como deuda total
                        break
    
    # Limpieza final de fechas (si agarró basura)
    if data['FECHA PERIODO'] and len(data['FECHA PERIODO']) > 20: data['FECHA PERIODO'] = None

    return data

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube tus PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🚀 Generar Reporte ({len(uploaded_files)} archivos)"):
        results = []
        bar = st.progress(0)
        
        for i, f in enumerate(uploaded_files):
            res = analyze_pdf_final(f, f.name)
            results.append(res)
            bar.progress((i+1)/len(uploaded_files))
            
        df = pd.DataFrame(results)
        
        # Orden EXACTO de tu CSV
        cols = [
            'ARCHIVO', 
            'FECHA PERIODO', 
            'FECHA DE VENCIMIENTO', 
            'NUMERO_FACTURA', 
            'VALOR_FACTURA', 
            'VALOR_TOTAL_DEUDA', 
            'ALUMBRADO', 
            'INTERESES', 
            'POLIZA', 
            'NOMBRE'
        ]
        
        # Asegurar columnas
        for c in cols:
            if c not in df.columns: df[c] = None
            
        st.dataframe(df[cols])
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df[cols].to_excel(writer, index=False)
        st.download_button("Descargar Reporte Final", output.getvalue(), "Reporte_TripleA_Final.xlsx")
