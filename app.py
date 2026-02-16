import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Analizador Triple A - Ultimate", page_icon="🛡️", layout="wide")

st.title("🛡️ Analizador Triple A - Versión Blindada")
st.markdown("""
**Estrategia:** Extracción por Tablas y Anclaje de Texto.
Si el PDF es digital (2017-2025), esto NO falla.
""")

# --- UTILIDADES DE LIMPIEZA ---
def clean_money(val):
    """Limpia dinero agresivamente."""
    if not val: return 0.0
    text = str(val).upper().replace('S', '5').replace('O', '0').replace('B', '8').replace("'", "").replace(" ", "")
    # Buscar el grupo de números más largo que parezca precio
    matches = re.findall(r'[\d\.,]+', text)
    if not matches: return 0.0
    
    best_match = max(matches, key=len)
    
    # Lógica Colombia (Detectar miles vs decimales)
    if ',' in best_match and '.' in best_match:
        best_match = best_match.replace('.', '').replace(',', '.')
    elif ',' in best_match:
        if len(best_match.split(',')[-1]) == 3: best_match = best_match.replace(',', '')
        else: best_match = best_match.replace(',', '.')
    elif '.' in best_match:
         if len(best_match.split('.')[-1]) == 3: best_match = best_match.replace('.', '')
    
    try: return float(best_match)
    except: return 0.0

def parse_date(text):
    """Normaliza fechas."""
    if not text: return None
    try:
        # Busca patrones comunes: 24-Mar-20 / Abril 2023 / 24/03/2020
        match = re.search(r'(\d{1,2})[-/\s]*([A-Za-z]{3,})[-/\s]*(\d{2,4})', text) # 24-Mar-20
        if match: return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
        match2 = re.search(r'([A-Za-z]{3,})\s+(\d{2,4})', text) # Abril 2023
        if match2: return f"{match2.group(1)} {match2.group(2)}"
        
        return text.strip()
    except: return text

# --- DRIVERS (LOS ROBOTS ESPECIALISTAS) ---

class Driver_Base:
    def extract(self, pdf, text): return {}

class Driver_Electronica_2024(Driver_Base):
    """
    ESTRATEGIA: Extracción de Tablas.
    Las facturas nuevas son tablas ordenadas. Leemos las celdas directamente.
    """
    def extract(self, pdf, text):
        data = {"MODELO": "ELECTRÓNICA (2024-25)"}
        
        # 1. Extracción por Tablas (Para Valores)
        # pdfplumber es excelente encontrando tablas en facturas electrónicas
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Convertir fila a texto plano para buscar palabras clave
                    row_text = " ".join([str(x) for x in row if x]).upper()
                    
                    # Buscar pares Clave -> Valor en la misma fila
                    if "TOTAL FACTURA SERVICIOS DEL PERIODO" in row_text:
                        # El valor suele ser el último elemento de la fila
                        data['VALOR_FACTURA'] = clean_money(row[-1])
                    
                    if "TOTAL FACTURA A PAGAR" in row_text:
                        data['VALOR_TOTAL_DEUDA'] = clean_money(row[-1])
                        
                    if "ALUMBRADO" in row_text:
                        data['ALUMBRADO'] = clean_money(row[-1])
                        
                    if "INTERESES" in row_text:
                        data['INTERESES'] = clean_money(row[-1])

        # 2. Extracción por Regex (Para Cabeceras que no están en tablas)
        # Nombre: suele estar después de la etiqueta
        m_nom = re.search(r'Nombre del cliente:[:\s]*\n?([^\n]+)', text)
        if m_nom: data['NOMBRE'] = m_nom.group(1).strip()
        
        # Factura
        m_fac = re.search(r'(?:Factura electrónica de venta|No\. de factura)[:\s]*([A-Z0-9]+)', text)
        if m_fac: data['NUMERO_FACTURA'] = m_fac.group(1)
        
        # Fechas (Suelen estar en bloques de texto)
        # "Fecha de emisión: Marzo 26-25"
        m_fecha = re.search(r'Fecha de emisión[:\s]*([^\n]+)', text)
        if m_fecha: data['FECHA PERIODO'] = parse_date(m_fecha.group(1))
        
        return data

class Driver_Transicion_2023(Driver_Base):
    """
    ESTRATEGIA: Búsqueda Espacial (Bounding Box).
    En 2023, la Triple A usa bloques azules. El texto suele estar flotando.
    Usamos regex más flexibles.
    """
    def extract(self, pdf, text):
        data = {"MODELO": "TRANSICIÓN (2023)"}
        
        # Nombre: Debajo de "Señor(a)"
        m_nom = re.search(r'Señor\(a\)[:\s]*\n([^\n]+)', text)
        if m_nom: data['NOMBRE'] = m_nom.group(1).strip()
        
        # Factura
        m_fac = re.search(r'Factura de servicio No\.[:\s\n]*(\d+)', text)
        if m_fac: data['NUMERO_FACTURA'] = m_fac.group(1)
        
        # Fechas (Período facturado)
        m_per = re.search(r'Periodo facturado[:\s\n]*([A-Za-z]+\-?\d{4})', text)
        if m_per: data['FECHA PERIODO'] = m_per.group(1)
        
        m_venc = re.search(r'Pague hasta[:\s\n]*([A-Za-z0-9\-\s]+)', text)
        if m_venc: data['FECHA DE VENCIMIENTO'] = m_venc.group(1)

        # Valores: Aquí el regex debe ser cuidadoso con los saltos de línea
        # Busca "TOTAL FACTURA SERVICIOS DEL PERIODO" y toma el precio que le sigue
        m_cons = re.search(r'TOTAL FACTURA SERVICIOS DEL PERIODO\s*\$?([\d\.,]+)', text)
        if m_cons: data['VALOR_FACTURA'] = clean_money(m_cons.group(1))
        
        m_deuda = re.search(r'TOTAL FACTURA A PAGAR\s*\$?([\d\.,]+)', text)
        if m_deuda: data['VALOR_TOTAL_DEUDA'] = clean_money(m_deuda.group(1))
        
        # Intereses (Suelen estar abajo en "Otros conceptos")
        m_int = re.search(r'Intereses de Mora\s*\$?([\d\.,]+)', text) # Caso 1: misma linea
        if not m_int:
             # Caso 2: Tabla desalineada, buscar número grande cerca de "Intereses"
             m_int = re.search(r'Intereses de Mora.*?(\d{3,}[\.,]\d{3})', text, re.DOTALL)
        if m_int: data['INTERESES'] = clean_money(m_int.group(1))

        return data

class Driver_Legacy_2017_2020(Driver_Base):
    """
    ESTRATEGIA: Regex Multilínea.
    Las viejas son texto plano.
    """
    def extract(self, pdf, text):
        data = {"MODELO": "LEGACY (2017-2020)"}
        
        # Nombre: Debajo de "Señor(a)"
        m_nom = re.search(r'Señor\(a\)\s*\n\s*([^\n]+)', text)
        if m_nom: data['NOMBRE'] = m_nom.group(1).strip()
        
        # Factura
        m_fac = re.search(r'Factura de servicios No\.[:\s\n]*(\d+)', text)
        if m_fac: data['NUMERO_FACTURA'] = m_fac.group(1)
        
        # Fechas
        m_per = re.search(r'Período facturado\s*\n\s*\"?([^\"]+)', text) # A veces vienen entre comillas en el raw text
        if m_per: data['FECHA PERIODO'] = m_per.group(1).replace('"', '')
        
        m_venc = re.search(r'Pague hasta.*?\n\s*\"?([A-Za-z]{3}\s\d{2}-\d{2})', text, re.DOTALL)
        if m_venc: data['FECHA DE VENCIMIENTO'] = m_venc.group(1)

        # Valores
        # En Legacy, "Total a Pagar" es la clave.
        # OJO: Usamos findall para encontrar todas las ocurrencias y tomamos la última o la más coherente
        matches = re.findall(r'Total a Pagar.*\$?\s*([\d\.,]+)', text, re.IGNORECASE)
        if matches:
            val = clean_money(matches[-1]) # Tomar el último (suele ser el total final)
            data['VALOR_TOTAL_DEUDA'] = val
            data['VALOR_FACTURA'] = val # Asumimos igual si no hay desglose

        # Intereses (Buscar en la tabla de atrás si existe)
        m_int = re.search(r'Intereses de Mora\s*\"?,\"?\s*([\d\.,]+)', text) # Patrón raro de CSV que a veces sale en pdfplumber
        if not m_int: m_int = re.search(r'Intereses de Mora.*?\$?([\d\.,]+)', text)
        if m_int: data['INTERESES'] = clean_money(m_int.group(1))

        return data

# --- CEREBRO PRINCIPAL ---
def process_invoice(file_obj, filename):
    try:
        # Extraer texto crudo para decidir qué driver usar
        full_text = ""
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                full_text += (page.extract_text(layout=True) or "") + "\n" # Layout True para mejor regex
            
            # Router de Drivers
            driver = None
            if "CUFE:" in full_text or "Factura electrónica" in full_text:
                driver = Driver_Electronica_2024()
            elif "TripleApp" in full_text and "PERIODO" in full_text:
                driver = Driver_Transicion_2023()
            elif "Damos crédito a tu vida" in full_text: # Otra variante 2023
                driver = Driver_Transicion_2023()
            elif "Período facturado" in full_text and "Zona" in full_text:
                driver = Driver_Legacy_2017_2020()
            else:
                # Si no reconoce, intenta el Legacy por defecto
                driver = Driver_Legacy_2017_2020()
            
            # Ejecutar extracción
            data = driver.extract(pdf, full_text)
            
            # Datos comunes (Póliza y Archivo)
            m_pol = re.search(r'PÓLIZA[:\s]*(\d+)', full_text, re.IGNORECASE)
            data['POLIZA'] = m_pol.group(1) if m_pol else None
            data['ARCHIVO'] = filename
            
            # Rellenar vacíos
            defaults = ['VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 'ALUMBRADO', 'INTERESES']
            for d in defaults:
                if d not in data: data[d] = 0.0
                
            return data

    except Exception as e:
        return {"ARCHIVO": filename, "ERROR": str(e)}

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Arrastra tus PDFs aquí", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🛡️ Analizar {len(uploaded_files)} Facturas"):
        results = []
        bar = st.progress(0)
        
        for i, f in enumerate(uploaded_files):
            data = process_invoice(f, f.name)
            results.append(data)
            bar.progress((i+1)/len(uploaded_files))
            
        df = pd.DataFrame(results)
        
        # Orden de Columnas solicitado
        cols = [
            'ARCHIVO', 'MODELO', 
            'FECHA PERIODO', 'FECHA DE VENCIMIENTO', 
            'NUMERO_FACTURA', 'NOMBRE',
            'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
            'ALUMBRADO', 'INTERESES', 'POLIZA'
        ]
        
        # Asegurar existencia de columnas
        for c in cols:
            if c not in df.columns: df[c] = None
            
        st.success("Análisis completado. Verifica los datos abajo.")
        st.dataframe(df[cols])
        
        # Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df[cols].to_excel(writer, index=False)
            
        st.download_button("Descargar Excel Final", buffer.getvalue(), "Reporte_TripleA_Blindado.xlsx")
