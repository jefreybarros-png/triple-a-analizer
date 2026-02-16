import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

st.set_page_config(page_title="Analizador Triple A - Plantillas", page_icon="🏗️", layout="wide")

st.title("🏗️ Analizador Estructural Triple A - Detección por Plantillas")
st.markdown("Sistema inteligente que identifica el 'HTML' (Plantilla) de la factura y aplica reglas específicas.")

# --- UTILIDADES ---
def clean_money(text):
    if not text: return 0.0
    text = str(text).upper().replace('S', '5').replace('O', '0').replace('B', '8')
    matches = re.findall(r'[\d\.,]+', text)
    if not matches: return 0.0
    
    # Tomar el candidato más largo y limpio
    best_match = max(matches, key=len)
    clean = best_match
    
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

# --- DEFINICIÓN DE PLANTILLAS (LOS "HTMLs") ---

def aplicar_plantilla_electronica(lines, text_block):
    """Plantilla 2024-2025: Tablas ordenadas, QR, CUFE."""
    data = {"MODELO": "ELECTRÓNICA (2024-25)"}
    
    for line in lines:
        upper = line.upper()
        # En la electrónica, la etiqueta y el valor suelen estar en la misma línea
        if "TOTAL FACTURA SERVICIOS DEL PERIODO" in upper:
            data['VALOR_CONSUMO_MES'] = clean_money(line.split('$')[-1])
        
        if "TOTAL FACTURA A PAGAR" in upper:
            data['VALOR_TOTAL_DEUDA'] = clean_money(line.split('$')[-1])

        if "IMPUESTO ALUMBRADO" in upper:
            data['ALUMBRADO'] = clean_money(line.split('$')[-1])
            
        if "INTERESES DE MORA" in upper:
             data['INTERESES'] = clean_money(line.split('$')[-1])

        if "FECHA DE EMISIÓN" in upper:
            data['FECHA'] = parse_date(line)
            
        if "FACTURA ELECTRÓNICA DE VENTA" in upper or "NO. DE FACTURA" in upper:
            m = re.search(r'([A-Z0-9]+)$', line.strip())
            if m: data['NUMERO_FACTURA'] = m.group(1)
            
    return data

def aplicar_plantilla_transicion(lines, text_block):
    """Plantilla 2023: TripleApp, dos totales confusos."""
    data = {"MODELO": "TRANSICIÓN (2023)"}
    
    for line in lines:
        upper = line.upper()
        if "TOTAL FACTURA SERVICIOS DEL PERIODO" in upper:
            data['VALOR_CONSUMO_MES'] = clean_money(line.split('$')[-1])
            
        # A veces el total a pagar está abajo solo como "Total a Pagar"
        if "TOTAL A PAGAR" in upper and "PERIODO" not in upper:
             val = clean_money(line.split('$')[-1])
             if val > 0: data['VALOR_TOTAL_DEUDA'] = val

        if "FACTURA DE SERVICIO NO" in upper:
            nums = re.findall(r'\d+', line)
            if nums: data['NUMERO_FACTURA'] = nums[-1]
            
        if "FECHA DE EMISIÓN" in upper:
             data['FECHA'] = parse_date(line)

    return data

def aplicar_plantilla_legacy(lines, text_block):
    """Plantilla 2017-2020: Texto plano, puntos suspensivos."""
    data = {"MODELO": "LEGACY (2017-2020)"}
    
    for line in lines:
        upper = line.upper()
        
        # El problema clásico: "Total a Pagar ........... $ 450.000"
        if "TOTAL A PAGAR" in upper and "PERIODO" not in upper:
            # Estrategia: partir la línea por espacios y buscar de atrás hacia adelante
            parts = line.split()
            for part in reversed(parts):
                val = clean_money(part)
                if val > 100: # Filtro para no agarrar basura
                    data['VALOR_TOTAL_DEUDA'] = val
                    data['VALOR_CONSUMO_MES'] = val # Asumimos igual
                    break
        
        if "FACTURA DE SERVICIOS NO" in upper:
            nums = re.findall(r'\d+', line)
            if nums: data['NUMERO_FACTURA'] = nums[-1]
            
        if "FECHA DE EMISIÓN" in upper:
             data['FECHA'] = parse_date(line)
             
    # Fallback fecha si no se encontró en línea
    if 'FECHA' not in data:
        m = re.search(r'([A-Z][a-z]{2}\s\d{2}-\d{2})', text_block)
        if m: data['FECHA'] = m.group(1)

    return data

def aplicar_plantilla_retro(lines, text_block):
    """Plantilla 2001: OCR, fechas viejas."""
    data = {"MODELO": "RETRO (2001)"}
    
    m_fecha = re.search(r'([A-Z]{3}[-/\s]\d{4})', text_block)
    if m_fecha: data['FECHA'] = m_fecha.group(1)
    
    precios = re.findall(r'\$\s?([\d\.,]{4,})', text_block)
    if precios:
        vals = [clean_money(p) for p in precios]
        data['VALOR_TOTAL_DEUDA'] = max(vals)
        data['VALOR_CONSUMO_MES'] = max(vals)
        
    return data

# --- CEREBRO PRINCIPAL ---
def analyze_invoice_smart(file_obj, filename):
    try:
        text_block = ""
        lines = []
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(layout=True) # CLAVE: Layout True
                if page_text:
                    text_block += page_text + "\n"
                    lines.extend(page_text.split('\n'))
    except Exception as e:
        return {"ARCHIVO": filename, "ERROR": str(e)}

    upper_block = text_block.upper()
    data = {}

    # 1. SELECCIÓN DE PLANTILLA (ROUTER)
    if "ESTADO DE CUENTA" in upper_block:
        data = {"MODELO": "ESTADO DE CUENTA", "NUMERO_FACTURA": "RESUMEN"}
        # Lógica simple para estado de cuenta
        precios = re.findall(r'TOTAL\s+\$?\s*([\d\.,]+)', upper_block)
        if precios: data['VALOR_TOTAL_DEUDA'] = clean_money(precios[-1])
        
    elif "CUFE:" in upper_block or "FACTURA ELECTRÓNICA" in upper_block:
        data = aplicar_plantilla_electronica(lines, text_block)
        
    elif "TOTAL FACTURA SERVICIOS DEL PERIODO" in upper_block:
        data = aplicar_plantilla_transicion(lines, text_block)
        
    elif re.search(r'[A-Z]{3}-\d{4}', upper_block):
        data = aplicar_plantilla_retro(lines, text_block)
        
    else:
        # Si no es ninguna, es la vieja confiable
        data = aplicar_plantilla_legacy(lines, text_block)

    # 2. DATOS GLOBALES (Póliza)
    poliza_m = re.search(r'PÓLIZA[:\s]*(\d+)', text_block, re.IGNORECASE)
    data['POLIZA'] = poliza_m.group(1) if poliza_m else None
    data['ARCHIVO'] = filename
    
    # Rellenar ceros
    for k in ['VALOR_CONSUMO_MES', 'VALOR_TOTAL_DEUDA', 'ALUMBRADO', 'INTERESES']:
        if k not in data: data[k] = 0.0

    return data

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube tus PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🚀 Procesar {len(uploaded_files)} Facturas con Plantillas"):
        results = []
        bar = st.progress(0)
        for i, f in enumerate(uploaded_files):
            res = analyze_invoice_smart(f, f.name)
            results.append(res)
            bar.progress((i+1)/len(uploaded_files))
            
        df = pd.DataFrame(results)
        
        cols = ['ARCHIVO', 'MODELO', 'FECHA', 'NUMERO_FACTURA', 'VALOR_CONSUMO_MES', 'VALOR_TOTAL_DEUDA', 'ALUMBRADO', 'INTERESES', 'POLIZA']
        for c in cols: 
            if c not in df.columns: df[c] = None
        df = df[cols]
        
        st.dataframe(df)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("Descargar Excel Final", output.getvalue(), "Reporte_Plantillas.xlsx")
