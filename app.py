import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

st.set_page_config(page_title="Analizador Triple A - Estructural", page_icon="🏗️", layout="wide")

st.title("🏗️ Analizador Estructural Triple A - Detección Precisa")
st.markdown("Identifica la 'firma' del documento y extrae datos leyendo línea por línea.")

# --- UTILIDADES ---
def clean_money(text):
    """Limpia una cadena para encontrar dinero, manejando basura de OCR."""
    if not text: return 0.0
    # Limpieza agresiva de OCR (letras por numeros)
    text = str(text).upper().replace('S', '5').replace('O', '0').replace('B', '8')
    # Buscar el patrón de dinero más claro en la cadena
    # Acepta: 1.000,00 | 1000,00 | 1.000 | 1,000
    matches = re.findall(r'[\d\.,]+', text)
    if not matches: return 0.0
    
    # Tomamos el match más largo (usualmente el precio real y no un '1' perdido)
    best_match = max(matches, key=len)
    
    # Normalización Colombia
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
    """Busca fechas en formatos variados."""
    try:
        # 24-Abr-2023 o 24/04/2023
        match = re.search(r'(\d{1,2})[-/\s]+([A-Za-z]{3,}|\d{2})[-/\s]+(\d{2,4})', text)
        if match:
            return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
        # ABR-2001 (Viejas)
        match = re.search(r'([A-Z]{3})[-/\s]+(\d{4})', text)
        if match:
            return f"{match.group(2)}-{match.group(1)}-01"
    except: pass
    return None

# --- DRIVERS POR MODELO ---

class Model_Driver:
    def extract(self, lines, text_block):
        return {}

class Driver_Electronica_2024(Model_Driver):
    """Para facturas con CUFE y código QR azul."""
    def extract(self, lines, text_block):
        data = {"MODELO": "ELECTRÓNICA (2024-25)"}
        for i, line in enumerate(lines):
            # En la electrónica, el total a pagar deuda está explícito
            if "TOTAL FACTURA A PAGAR" in line.upper():
                data['VALOR_TOTAL_DEUDA'] = clean_money(line.split('$')[-1])
            
            # El consumo del mes
            if "TOTAL FACTURA SERVICIOS DEL PERIODO" in line.upper():
                data['VALOR_CONSUMO_MES'] = clean_money(line.split('$')[-1])
            
            # Fecha y Factura
            if "FECHA DE EMISIÓN" in line.upper():
                data['FECHA'] = parse_date(line)
            if "FACTURA ELECTRÓNICA DE VENTA" in line.upper():
                # A veces el número está en la misma línea, a veces abajo
                parts = line.split(':')
                if len(parts) > 1: data['NUMERO_FACTURA'] = parts[1].strip()
        
        # Búsqueda de respaldo si falló la línea por línea
        if 'VALOR_TOTAL_DEUDA' not in data:
             m = re.search(r'TOTAL FACTURA A PAGAR\s*\$?([\d\.,]+)', text_block)
             if m: data['VALOR_TOTAL_DEUDA'] = clean_money(m.group(1))

        return data

class Driver_Legacy_2017_2020(Model_Driver):
    """Para facturas viejas blanco y negro con código de barras lineal."""
    def extract(self, lines, text_block):
        data = {"MODELO": "LEGACY (2017-2020)"}
        
        # En estas facturas, el "Total a Pagar" a veces tiene puntos suspensivos
        # Ejemplo: "Total a Pagar ........................ $ 450.000"
        
        for line in lines:
            line_upper = line.upper()
            
            # Valor (El más crítico)
            if "TOTAL A PAGAR" in line_upper and "PERIODO" not in line_upper:
                # Estrategia: Partir por espacios y tomar el último elemento que parezca dinero
                parts = line.split()
                # Buscamos desde el final hacia atrás
                for part in reversed(parts):
                    val = clean_money(part)
                    if val > 100: # Filtro de ruido (evitar que tome un '1')
                        data['VALOR_TOTAL_DEUDA'] = val
                        data['VALOR_CONSUMO_MES'] = val
                        break
            
            # Factura
            if "FACTURA DE SERVICIOS NO" in line_upper or "FACTURA DE SERVICIO NO" in line_upper:
                # Extraer solo dígitos de la línea
                nums = re.findall(r'\d+', line)
                if nums: data['NUMERO_FACTURA'] = nums[-1] # El último número suele ser la factura
                
            # Fecha
            if "FECHA DE EMISIÓN" in line_upper:
                data['FECHA'] = parse_date(line)

        # Fallback para fecha: buscar patrón MMM-YY si no se encontró arriba
        if 'FECHA' not in data:
            m = re.search(r'([A-Z][a-z]{2}\s\d{2}-\d{2})', text_block) # Ej: Mar 20-17
            if m: data['FECHA'] = m.group(1)

        return data

class Driver_Retro_2001(Model_Driver):
    """Para escaneos muy viejos."""
    def extract(self, lines, text_block):
        data = {"MODELO": "RETRO (2000s)"}
        # Aquí el OCR es sucio, confiamos más en regex sobre el bloque entero
        
        # Fecha tipo OCT-2001
        m_fecha = re.search(r'([A-Z]{3}[-/\s]\d{4})', text_block)
        if m_fecha: data['FECHA'] = m_fecha.group(1)
        
        # Valor
        # Buscamos patrones de dinero grandes
        precios = re.findall(r'\$\s?([\d\.,]{4,})', text_block)
        if precios:
            # En facturas viejas, el total solía ser el número más grande al final
            vals = [clean_money(p) for p in precios]
            data['VALOR_TOTAL_DEUDA'] = max(vals) if vals else 0
            data['VALOR_CONSUMO_MES'] = data['VALOR_TOTAL_DEUDA']
            
        return data

class Driver_Estado_Cuenta(Model_Driver):
    def extract(self, lines, text_block):
        data = {"MODELO": "ESTADO DE CUENTA", "NUMERO_FACTURA": "RESUMEN"}
        # El total suele estar al final de la tabla
        for line in reversed(lines): # Leemos de abajo hacia arriba
            if "TOTAL" in line.upper():
                val = clean_money(line)
                if val > 0:
                    data['VALOR_TOTAL_DEUDA'] = val
                    break
        return data

# --- CEREBRO PRINCIPAL ---
def analyze_invoice(file_obj, filename):
    try:
        text_block = ""
        lines = []
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                # Extraer texto preservando lineas
                page_text = page.extract_text()
                if page_text:
                    text_block += page_text + "\n"
                    lines.extend(page_text.split('\n'))
    except Exception as e:
        return {"ARCHIVO": filename, "ERROR": str(e)}

    # 1. DETECTAR EL DRIVER ADECUADO (La "Firma")
    driver = None
    upper_block = text_block.upper()

    if "ESTADO DE CUENTA" in upper_block:
        driver = Driver_Estado_Cuenta()
    elif "CUFE:" in upper_block or "FACTURA ELECTRÓNICA" in upper_block:
        driver = Driver_Electronica_2024()
    elif "TRIPLEAPP" in upper_block or "SERVICIOS DEL PERIODO" in upper_block:
        driver = Driver_Electronica_2024() # Estructura similar a la moderna (2023)
    elif re.search(r'[A-Z]{3}-\d{4}', upper_block): # Detecta FEB-2002
        driver = Driver_Retro_2001()
    else:
        # Por defecto asumimos Legacy (2017-2020) si no es nada de lo anterior
        driver = Driver_Legacy_2017_2020()

    # 2. EJECUTAR EXTRACCIÓN
    data = driver.extract(lines, text_block)
    
    # 3. DATOS COMUNES (Póliza suele estar igual en todas)
    poliza_m = re.search(r'PÓLIZA[:\s]*(\d+)', text_block, re.IGNORECASE)
    data['POLIZA'] = poliza_m.group(1) if poliza_m else None
    
    data['ARCHIVO'] = filename
    
    # Rellenar ceros si falta algo
    if 'VALOR_TOTAL_DEUDA' not in data: data['VALOR_TOTAL_DEUDA'] = 0.0
    if 'VALOR_CONSUMO_MES' not in data: data['VALOR_CONSUMO_MES'] = 0.0
    
    # Buscar Alumbrado e Intereses (Global)
    alum = re.search(r'Impuesto Alumbrado Público BQ.*?\$?([\d\.,]+)', text_block)
    data['ALUMBRADO'] = clean_money(alum.group(1)) if alum else 0.0
    
    ints = re.search(r'Intereses de Mora.*?\$?([\d\.,]+)', text_block)
    data['INTERESES'] = clean_money(ints.group(1)) if ints else 0.0

    return data

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube tus PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("Analizar Estructura"):
        results = []
        bar = st.progress(0)
        for i, f in enumerate(uploaded_files):
            res = analyze_invoice(f, f.name)
            results.append(res)
            bar.progress((i+1)/len(uploaded_files))
            
        df = pd.DataFrame(results)
        
        # Ordenar
        cols = ['ARCHIVO', 'MODELO', 'FECHA', 'NUMERO_FACTURA', 'VALOR_CONSUMO_MES', 'VALOR_TOTAL_DEUDA', 'ALUMBRADO', 'INTERESES', 'POLIZA']
        for c in cols: 
            if c not in df.columns: df[c] = None
        df = df[cols]
        
        st.dataframe(df)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("Descargar Excel", output.getvalue(), "Reporte_Estructural.xlsx")
