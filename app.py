import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Extractor Triple A - Master Map", page_icon="🗺️", layout="wide")

st.title("🗺️ Extractor Triple A - Mapeo Estricto por Modelo")
st.markdown("""
**Estrategia:** Identificación de ADN del PDF + Extracción por Coordenadas Relativas.
Diseñado para replicar exactamente tu Excel de referencia.
""")

# --- HERRAMIENTAS DE LIMPIEZA (EL CINCEL) ---
def clean_money(val):
    """Convierte cualquier texto sucio de dinero a Float."""
    if not val: return 0.0
    # Limpieza OCR agresiva
    text = str(val).upper().replace('S', '5').replace('O', '0').replace('B', '8').replace("'", "").replace(" ", "")
    text = text.replace("$", "")
    
    # Buscar el número más coherente
    matches = re.findall(r'[\d\.,]+', text)
    if not matches: return 0.0
    
    candidate = max(matches, key=len)
    
    # Decisión Regional (Colombia):
    # Si tiene punto y coma (1.200,50), punto es mil.
    if ',' in candidate and '.' in candidate:
        candidate = candidate.replace('.', '').replace(',', '.')
    # Si solo tiene coma (100,000 o 100,00)
    elif ',' in candidate:
        parts = candidate.split(',')
        if len(parts[-1]) == 3: candidate = candidate.replace(',', '') # Miles
        else: candidate = candidate.replace(',', '.') # Decimal
    # Si solo tiene punto (100.000)
    elif '.' in candidate:
         if len(candidate.split('.')[-1]) == 3: candidate = candidate.replace('.', '')

    try: return float(candidate)
    except: return 0.0

def clean_text(text):
    """Limpia saltos de linea y espacios extra."""
    if not text: return None
    return text.replace('\n', ' ').strip()

def parse_date(text):
    """Normalizador de Fechas Triple A."""
    if not text: return None
    text = text.strip()
    # Patrón: Abr 05-23
    m1 = re.search(r'([A-Za-z]{3})\s+(\d{1,2})[-/](\d{2})', text)
    if m1: return f"{m1.group(3)}-{m1.group(1)}-{m1.group(2)}" # YY-MM-DD (Excel friendly)
    
    # Patrón: Abril 2023
    m2 = re.search(r'([A-Za-z]+)\s+(\d{4})', text)
    if m2: return f"{m2.group(1)} {m2.group(2)}"
    
    return text

# --- LOS MAPAS (CLASES POR MODELO) ---

class InvoiceModel:
    """Clase Padre que define la estructura del reporte."""
    def extract(self, pdf, text_layout):
        return {
            "FECHA PERIODO": None,
            "FECHA DE VENCIMIENTO": None,
            "NUMERO_FACTURA": None,
            "VALOR_FACTURA": 0.0,
            "VALOR_TOTAL_DEUDA": 0.0,
            "ALUMBRADO": 0.0,
            "INTERESES": 0.0,
            "POLIZA": None,
            "NOMBRE": None
        }

class Model_Electronica_2024(InvoiceModel):
    """
    MAPA 2024-2025:
    - Se basa en TABLAS (Grid).
    - El nombre está etiquetado con 'Nombre del cliente:'.
    - Los valores están en filas específicas de la tabla de resumen.
    """
    def extract(self, pdf, text_layout):
        data = super().extract(pdf, text_layout)
        data['MODELO'] = "ELECTRÓNICA (2024-25)"
        
        # 1. Extracción Estricta por Tablas
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Aplanar la fila para buscar palabras clave
                    row_str = " ".join([str(c) for c in row if c]).upper()
                    
                    # MAPEO DE VALORES EN TABLA
                    if "TOTAL FACTURA SERVICIOS DEL PERIODO" in row_str:
                        data['VALOR_FACTURA'] = clean_money(row[-1]) # Última columna
                    
                    if "TOTAL FACTURA A PAGAR" in row_str:
                        data['VALOR_TOTAL_DEUDA'] = clean_money(row[-1])
                        
                    if "ALUMBRADO" in row_str:
                        data['ALUMBRADO'] = clean_money(row[-1])
                        
                    if "INTERESES" in row_str:
                        # A veces intereses está en una celda intermedia
                        vals = [clean_money(c) for c in row if clean_money(c) > 0]
                        if vals: data['INTERESES'] = vals[-1]

        # 2. Extracción por Anclaje de Texto (Lo que no está en tablas)
        lines = text_layout.split('\n')
        for i, line in enumerate(lines):
            upper = line.upper()
            
            # NOMBRE: Está a la derecha de la etiqueta
            if "NOMBRE DEL CLIENTE:" in upper:
                parts = line.split(":")
                if len(parts) > 1: data['NOMBRE'] = parts[1].strip()
                # Si está vacío, mirar la línea siguiente (a veces pasa)
                if not data['NOMBRE'] and i+1 < len(lines):
                    data['NOMBRE'] = lines[i+1].strip()

            # FACTURA
            if "FACTURA ELECTRÓNICA DE VENTA" in upper or "NO. DE FACTURA" in upper:
                m = re.search(r'([A-Z0-9]+)$', line.strip())
                if m: data['NUMERO_FACTURA'] = m.group(1)
            
            # FECHAS
            if "FECHA DE EMISIÓN" in upper:
                data['FECHA PERIODO'] = parse_date(line.split(":")[-1])
            
            if "PAGUE HASTA" in upper: # A veces aparece, a veces no en la electrónica
                data['FECHA DE VENCIMIENTO'] = parse_date(line.split(":")[-1])

        return data

class Model_Transicion_2023(InvoiceModel):
    """
    MAPA 2023 (Azul/TripleApp):
    - Estructura flotante.
    - Datos a la DERECHA de la etiqueta.
    """
    def extract(self, pdf, text_layout):
        data = super().extract(pdf, text_layout)
        data['MODELO'] = "TRANSICIÓN (2023)"
        
        lines = text_layout.split('\n')
        
        # Banderas para bloques de texto
        en_bloque_conceptos = False
        
        for i, line in enumerate(lines):
            upper = line.upper()
            
            # ANCLAJE: Derecha
            if "PERIODO FACTURADO" in upper:
                # En 2023 está debajo o al lado. Probamos regex.
                m = re.search(r'Periodo facturado\s*([A-Za-z]+\-?\d{4})', line, re.IGNORECASE)
                if m: data['FECHA PERIODO'] = m.group(1)
                else: 
                     # Si no está al lado, miramos abajo
                     if i+1 < len(lines): data['FECHA PERIODO'] = lines[i+1].strip()

            if "PAGUE HASTA" in upper:
                data['FECHA DE VENCIMIENTO'] = line.split("hasta")[-1].strip()
                
            if "FACTURA DE SERVICIO NO" in upper:
                m = re.search(r'No\.\s*(\d+)', line)
                if m: data['NUMERO_FACTURA'] = m.group(1)

            # VALORES CON ETIQUETA EXACTA
            if "TOTAL FACTURA SERVICIOS DEL PERIODO" in upper:
                data['VALOR_FACTURA'] = clean_money(line.split('$')[-1])
            
            if "TOTAL FACTURA A PAGAR" in upper:
                data['VALOR_TOTAL_DEUDA'] = clean_money(line.split('$')[-1])
            
            # INTERESES (Suelen estar en una tabla difícil)
            if "INTERESES DE MORA" in upper:
                val = clean_money(line.split()[-1])
                data['INTERESES'] = val

            # NOMBRE (Ancla especial 2023)
            if "SEÑOR(A)" in upper:
                if i+1 < len(lines): data['NOMBRE'] = lines[i+1].strip()

        return data

class Model_Legacy_2017_2020(InvoiceModel):
    """
    MAPA LEGACY (La Vieja Guardia):
    - Estructura Vertical (Etiqueta ARRIBA, Valor ABAJO).
    - El "Total a Pagar" tiene puntos suspensivos.
    """
    def extract(self, pdf, text_layout):
        data = super().extract(pdf, text_layout)
        data['MODELO'] = "LEGACY (2017-2020)"
        
        lines = text_layout.split('\n')
        
        for i, line in enumerate(lines):
            upper = line.upper()
            
            # ANCLAJE VERTICAL (Dato en línea i+1)
            if "PERÍODO FACTURADO" in upper:
                if i+1 < len(lines): data['FECHA PERIODO'] = lines[i+1].strip()
            
            if "FECHA DE EMISIÓN" in upper:
                # A veces está al lado en legacy tardío, a veces abajo.
                # Priorizamos abajo si la linea actual termina en "emisión"
                if line.strip().endswith("emisión") and i+1 < len(lines):
                    pass # Fecha está abajo
                else:
                    pass # Fecha está al lado
            
            if "PAGUE HASTA" in upper:
                 if i+1 < len(lines): data['FECHA DE VENCIMIENTO'] = lines[i+1].strip()

            if "SEÑOR(A)" in upper:
                 if i+1 < len(lines): data['NOMBRE'] = lines[i+1].strip()

            if "FACTURA DE SERVICIOS NO" in upper:
                 if i+1 < len(lines): data['NUMERO_FACTURA'] = lines[i+1].strip()

            # ANCLAJE HORIZONTAL CON PUNTOS
            # "Total a Pagar ........... $ 400.000"
            if "TOTAL A PAGAR" in upper and "PERIODO" not in upper:
                # Partimos por espacios y tomamos el último valor numérico
                parts = line.split()
                for p in reversed(parts):
                    v = clean_money(p)
                    if v > 100:
                        data['VALOR_TOTAL_DEUDA'] = v
                        data['VALOR_FACTURA'] = v # En legacy no distinguen bien consumo vs deuda en resumen
                        break
            
            if "INTERESES DE MORA" in upper:
                # En legacy suelen estar tabulados con comas
                # Buscamos el último numero de la línea
                v = clean_money(line.split()[-1])
                data['INTERESES'] = v

        return data

class Model_Retro_2001(InvoiceModel):
    """
    MAPA RETRO (Pre-Digital):
    - OCR puede fallar.
    - Estructura muy vertical.
    """
    def extract(self, pdf, text_layout):
        data = super().extract(pdf, text_layout)
        data['MODELO'] = "RETRO (2001)"
        
        # Regex global porque la estructura de líneas se rompe fácil en escaneos
        m_fecha = re.search(r'([A-Z]{3,}[-/\s]\d{4})', text_layout.upper())
        if m_fecha: data['FECHA PERIODO'] = m_fecha.group(1)
        
        # El valor total suele ser el número más grande al final
        precios = re.findall(r'\$\s?([\d\.,]{4,})', text_layout)
        if precios:
            vals = [clean_money(p) for p in precios]
            top_val = max(vals)
            data['VALOR_TOTAL_DEUDA'] = top_val
            data['VALOR_FACTURA'] = top_val
            
        return data


# --- CEREBRO CENTRAL (EL REPARTIDOR) ---

def identify_and_extract(file_obj, filename):
    # 1. Leer PDF completo con Layout
    try:
        text_layout = ""
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                text_layout += (page.extract_text(layout=True) or "") + "\n"
                
            # Clonamos el objeto pdf para pasarlo a los drivers que usan tablas
            # (pdfplumber requiere el objeto abierto)
            
            # 2. IDENTIFICACIÓN DE ADN
            upper_text = text_layout.upper()
            driver = None
            
            if "CUFE:" in upper_text or "FACTURA ELECTRÓNICA" in upper_text:
                driver = Model_Electronica_2024()
            elif "TRIPLEAPP" in upper_text or "DAMOS CRÉDITO" in upper_text:
                driver = Model_Transicion_2023()
            elif re.search(r'[A-Z]{3}-\d{4}', upper_text): # Detecta FEB-2002
                driver = Model_Retro_2001()
            elif "TOTAL A PAGAR" in upper_text and "PERÍODO FACTURADO" in upper_text:
                driver = Model_Legacy_2017_2020()
            else:
                driver = Model_Legacy_2017_2020() # Default

            # 3. EJECUCIÓN DEL MAPA
            data = driver.extract(pdf, text_layout)
            
            # 4. DATOS UNIVERSALES (Póliza siempre está igual)
            m_pol = re.search(r'PÓLIZA[:\s\.]*(\d+)', upper_text)
            if m_pol: data['POLIZA'] = m_pol.group(1)
            
            data['ARCHIVO'] = filename
            
            return data

    except Exception as e:
        return {"ARCHIVO": filename, "ERROR": str(e)}

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Sube tus Facturas (PDF)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🗺️ Mapear {len(uploaded_files)} Facturas"):
        results = []
        bar = st.progress(0)
        
        for i, f in enumerate(uploaded_files):
            # Reiniciamos el puntero del archivo por si acaso
            f.seek(0)
            res = identify_and_extract(f, f.name)
            results.append(res)
            bar.progress((i+1)/len(uploaded_files))
            
        df = pd.DataFrame(results)
        
        # Columnas solicitadas
        cols = [
            'ARCHIVO', 'MODELO',
            'FECHA PERIODO', 'FECHA DE VENCIMIENTO', 
            'NUMERO_FACTURA', 'NOMBRE',
            'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
            'ALUMBRADO', 'INTERESES', 'POLIZA'
        ]
        
        # Garantizar columnas
        for c in cols:
            if c not in df.columns: df[c] = None
            
        st.success("¡Mapeo Completado!")
        st.dataframe(df[cols])
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df[cols].to_excel(writer, index=False)
            
        st.download_button("Descargar Excel Final", buffer.getvalue(), "Reporte_TripleA_Mapeado.xlsx")
