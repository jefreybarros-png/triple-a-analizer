import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Analizador Triple A - Nivel Pro", page_icon="💧", layout="wide")

st.title("💧 Analizador de Facturas Triple A - Edición 'Bien Fina'")
st.markdown("Extracción de precisión quirúrgica para todos los formatos (2001-2025).")

class TripleA_Sniper:
    def __init__(self):
        # Mapeo de meses para normalizar fechas
        self.meses = {
            'ENE': '01', 'FEB': '02', 'MAR': '03', 'ABR': '04', 'MAY': '05', 'JUN': '06',
            'JUL': '07', 'AGO': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DIC': '12',
            'ENERO': '01', 'FEBRERO': '02', 'MARZO': '03', 'ABRIL': '04', 'MAYO': '05', 'JUNIO': '06',
            'JULIO': '07', 'AGOSTO': '08', 'SEPTIEMBRE': '09', 'OCTUBRE': '10', 'NOVIEMBRE': '11', 'DICIEMBRE': '12'
        }

    def clean_money(self, val):
        """Limpia formatos de moneda colombianos (viejos y nuevos)."""
        if not val: return 0.0
        # Corrección de OCR común en escaneos viejos
        val = str(val).upper().replace('S', '5').replace('O', '0').replace('B', '8')
        # Dejar solo números, puntos y comas
        clean = re.sub(r'[^\d,\.]', '', val)
        
        # Lógica de decisión decimal/miles
        if ',' in clean and '.' in clean: # Caso: 1.500,00
            clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean: 
            # Si hay 3 dígitos al final (100,000) es miles
            if len(clean.split(',')[-1]) == 3: clean = clean.replace(',', '')
            else: clean = clean.replace(',', '.') # Es decimal
        elif '.' in clean:
             # Si hay 3 dígitos al final (100.000) es miles
             if len(clean.split('.')[-1]) == 3: clean = clean.replace('.', '')
             
        try: return float(clean)
        except: return 0.0

    def parse_date(self, text):
        """Normaliza fechas variadas a YYYY-MM-DD."""
        try:
            # Patrón 1: Ene 24-23 o Ene 24/23
            match = re.search(r'([A-Z]{3,})\s*(\d{1,2})[-/](\d{2,4})', text, re.IGNORECASE)
            if match:
                mes = self.meses.get(match.group(1).upper()[:3], '01')
                dia = match.group(2).zfill(2)
                ano = match.group(3)
                if len(ano) == 2: ano = f"20{ano}"
                return f"{ano}-{mes}-{dia}"
            
            # Patrón 2: 24/04/2023
            match = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})', text)
            if match:
                return f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
            
            # Patrón 3 (Viejas): OCT-2001
            match = re.search(r'([A-Z]{3,})[-/\s](\d{4})', text, re.IGNORECASE)
            if match:
                mes = self.meses.get(match.group(1).upper()[:3], '01')
                return f"{match.group(2)}-{mes}-01"
                
            return None
        except: return None

    def extract_value_context(self, text, keywords):
        """Busca una palabra clave y extrae el dinero que esté CERCA (arriba, abajo o al lado)."""
        # Buscamos la palabra clave
        match = re.search(rf"({keywords})", text, re.IGNORECASE)
        if not match: return 0.0
        
        # Tomamos un "recorte" del texto alrededor de la palabra encontrada
        start = match.start()
        # Miramos 100 caracteres adelante
        snippet = text[start:start+150]
        
        # Buscamos patrones de dinero en ese recorte
        # El regex busca: $ opcional, digitos, puntos/comas, digitos
        money_match = re.search(r'\$\s?([\d\.,]+)', snippet)
        if money_match:
            return self.clean_money(money_match.group(1))
        
        # Si no tiene signo peso, buscamos número "suelto" grande
        nums = re.findall(r'([\d\.,]{4,})', snippet) # Al menos 4 dígitos para evitar fechas o códigos cortos
        if nums:
            return self.clean_money(nums[0])
            
        return 0.0

    def get_line_value(self, text, keyword):
        """Busca una línea específica (ej: Alumbrado) y saca el valor final."""
        lines = text.split('\n')
        for line in lines:
            if keyword.upper() in line.upper():
                # Extraer todos los valores numéricos de la línea
                vals = re.findall(r'([\d\.,]+)', line)
                # Filtramos valores muy pequeños (a veces agarran el porcentaje 1.5%)
                valid_vals = [v for v in vals if self.clean_money(v) > 50]
                if valid_vals:
                    # Usualmente el valor a pagar es el último de la línea
                    return self.clean_money(valid_vals[-1])
        return 0.0

    def analyze_pdf(self, file_obj, filename):
        try:
            text = ""
            with pdfplumber.open(file_obj) as pdf:
                for page in pdf.pages:
                    # layout=True es CLAVE para mantener tablas alineadas
                    text += (page.extract_text(layout=True) or "") + "\n"
        except Exception as e:
            return {"ARCHIVO": filename, "ERROR": str(e)}

        data = {
            "ARCHIVO": filename, 
            "POLIZA": None, 
            "NUMERO_FACTURA": None, 
            "FECHA": None,
            "VALOR_MES": 0.0, 
            "VALOR_TOTAL_DEUDA": 0.0,
            "VALOR_ALUMBRADO": 0.0, 
            "VALOR_INTERES": 0.0,
            "TIPO_DETECTADO": "Desconocido"
        }

        # 1. PÓLIZA (Casi siempre es estándar)
        poliza = re.search(r'PÓLIZA[:\s]*(\d+)', text, re.IGNORECASE)
        if poliza: data['POLIZA'] = poliza.group(1)

        # 2. IDENTIFICAR FORMATO Y EXTRAER VALORES
        upper_text = text.upper()
        
        if "ESTADO DE CUENTA" in upper_text:
            data['TIPO_DETECTADO'] = "ESTADO DE CUENTA"
            data['NUMERO_FACTURA'] = "RESUMEN"
            data['VALOR_TOTAL_DEUDA'] = self.extract_value_context(text, "TOTAL")
            data['FECHA'] = self.parse_date(text) # Intenta buscar cualquier fecha

        elif "FACTURA ELECTRÓNICA" in upper_text or "CUFE:" in upper_text:
            data['TIPO_DETECTADO'] = "ELECTRÓNICA (2024-25)"
            
            # Factura
            fac = re.search(r'(?:Factura electrónica de venta|No\.|Número)[:\s]*([A-Z0-9]+)', text, re.IGNORECASE)
            if fac: data['NUMERO_FACTURA'] = fac.group(1)
            
            # Fecha
            fecha_match = re.search(r'Fecha de emisión[:\s]*([A-Za-z0-9\s-]+)', text, re.IGNORECASE)
            if fecha_match: data['FECHA'] = self.parse_date(fecha_match.group(1))

            # Valores (Aquí la precisión es clave)
            # Consumo Mes: Busca explícitamente "Servicios del Periodo"
            data['VALOR_MES'] = self.extract_value_context(text, "TOTAL FACTURA SERVICIOS DEL PERIODO")
            # Deuda Total: Busca "Total a Pagar"
            data['VALOR_TOTAL_DEUDA'] = self.extract_value_context(text, "TOTAL FACTURA A PAGAR")

        elif "TOTAL FACTURA SERVICIOS DEL PERIODO" in upper_text:
            data['TIPO_DETECTADO'] = "TRANSICIÓN (2023)"
            # Mismo patrón que la electrónica
            fac = re.search(r'Factura de servicio No\.[:\s]*(\d+)', text, re.IGNORECASE)
            if fac: data['NUMERO_FACTURA'] = fac.group(1)
            
            data['VALOR_MES'] = self.extract_value_context(text, "TOTAL FACTURA SERVICIOS DEL PERIODO")
            data['VALOR_TOTAL_DEUDA'] = self.extract_value_context(text, "Total a Pagar")
            # Fecha (A veces está arriba a la derecha)
            fecha_match = re.search(r'Fecha de emisión[:\s]*([A-Za-z0-9\s-]+)', text, re.IGNORECASE)
            if fecha_match: data['FECHA'] = self.parse_date(fecha_match.group(1))

        else: # FORMATO LEGACY (2017-2020) y VIEJOS
            data['TIPO_DETECTADO'] = "LEGACY / VIEJO"
            
            # Factura
            fac = re.search(r'(?:Factura|Ref)[:\s\.]*(?:No\.?)?[:\s]*(\d+)', text, re.IGNORECASE)
            if fac: data['NUMERO_FACTURA'] = fac.group(1)
            
            # Valores (En legacy solo hay un Total relevante)
            val = self.extract_value_context(text, "Total a Pagar")
            if val == 0: val = self.extract_value_context(text, "VALOR A PAGAR") # Para 2001
            
            data['VALOR_MES'] = val
            data['VALOR_TOTAL_DEUDA'] = val # Asumimos igual
            
            # Fecha (Buscar patrones MMM-AAAA o DD/MM/AAAA)
            data['FECHA'] = self.parse_date(text)

        # 3. EXTRACCION ESPECÍFICA (Línea por línea)
        data['VALOR_ALUMBRADO'] = self.get_line_value(text, "Alumbrado Público")
        data['VALOR_INTERES'] = self.get_line_value(text, "Intereses de Mora")
        
        # Limpieza final: Si el Alumbrado es igual al total (error raro), poner 0
        if data['VALOR_ALUMBRADO'] == data['VALOR_TOTAL_DEUDA']: data['VALOR_ALUMBRADO'] = 0

        return data

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Arrastra aquí tus facturas PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🔎 Analizar {len(uploaded_files)} Archivos"):
        sniper = TripleA_Sniper()
        results = []
        bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            res = sniper.analyze_pdf(file, file.name)
            results.append(res)
            bar.progress((i+1)/len(uploaded_files))
            
        df = pd.DataFrame(results)
        
        # Ordenar columnas lógicamente
        cols = ['ARCHIVO', 'TIPO_DETECTADO', 'FECHA', 'NUMERO_FACTURA', 
                'VALOR_MES', 'VALOR_ALUMBRADO', 'VALOR_INTERES', 'VALOR_TOTAL_DEUDA', 'POLIZA']
        
        # Rellenar columnas faltantes
        for c in cols: 
            if c not in df.columns: df[c] = None
        df = df[cols]

        st.success("¡Análisis Terminado!")
        st.dataframe(df)
        
        # Exportar
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button("📥 Descargar Excel", output.getvalue(), "Reporte_TripleA_Fino.xlsx")
