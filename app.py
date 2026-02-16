import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Analizador Triple A - Pro", page_icon="💧", layout="wide")

st.title("💧 Analizador de Facturas Triple A - La Mondá")
st.markdown("""
Sube tus facturas (PDF) viejas, nuevas, estados de cuenta... ¡lo que sea! 
Este sistema identifica el modelo y te saca el Excel masticadito.
""")

# --- CLASE MAESTRA ---
class TripleA_Master_Parser:
    def __init__(self):
        self.meses_map = {
            'ENE': '01', 'FEB': '02', 'MAR': '03', 'ABR': '04', 'MAY': '05', 'JUN': '06',
            'JUL': '07', 'AGO': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DIC': '12',
            'ENERO': '01', 'FEBRERO': '02', 'MARZO': '03', 'ABRIL': '04', 'MAYO': '05', 'JUNIO': '06',
            'JULIO': '07', 'AGOSTO': '08', 'SEPTIEMBRE': '09', 'OCTUBRE': '10', 'NOVIEMBRE': '11', 'DICIEMBRE': '12'
        }

    def clean_money(self, val):
        if not val: return 0.0
        val = str(val).upper().replace('S', '5').replace('O', '0').replace('B', '8')
        clean = re.sub(r'[^\d,\.]', '', val)
        if ',' in clean and '.' in clean:
            clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean:
            if len(clean.split(',')[-1]) == 3: clean = clean.replace(',', '')
            else: clean = clean.replace(',', '.')
        elif '.' in clean:
             if len(clean.split('.')[-1]) == 3: clean = clean.replace('.', '')
        try: return float(clean)
        except: return 0.0

    def parse_retro_date(self, text):
        pattern = r'([A-Z]{3})[-/\s\.]+(\d{4})'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            mes_txt = match.group(1).upper()
            ano = match.group(2)
            mes_num = self.meses_map.get(mes_txt, '01')
            return f"{ano}-{mes_num}-01"
        return None

    def detect_format(self, text):
        upper_text = text.upper()
        if "ESTADO DE CUENTA" in upper_text or "SALDO DIFERIDO" in upper_text: return "ESTADO_CUENTA"
        if "FACTURA ELECTRÓNICA DE VENTA" in upper_text: return "MODERNO_ELECTRONICO"
        if "TOTAL FACTURA SERVICIOS DEL PERIODO" in upper_text: return "MODERNO_TRANSICION"
        if re.search(r'[A-Z]{3}-\d{4}', upper_text): return "RETRO_2000s"
        return "LEGACY_ESTANDAR"

    def extract_data(self, file_obj, filename):
        try:
            full_text = ""
            with pdfplumber.open(file_obj) as pdf:
                for page in pdf.pages:
                    full_text += page.extract_text() or "" + "\n"
        except Exception as e:
            return {"ARCHIVO": filename, "ERROR": f"PDF Dañado: {str(e)}"}

        modelo = self.detect_format(full_text)
        
        data = {
            "ARCHIVO": filename, "MODELO": modelo, "POLIZA": None, "FECHA": None,
            "VALOR_CONSUMO_MES": 0.0, "VALOR_TOTAL_DEUDA": 0.0,
            "VALOR_ALUMBRADO": 0.0, "VALOR_INTERES": 0.0, "NUMERO_FACTURA": None
        }

        # Extracción
        poliza_match = re.search(r'PÓLIZA[:\s]*(\d+)', full_text, re.IGNORECASE)
        if poliza_match: data['POLIZA'] = poliza_match.group(1)

        if modelo == "ESTADO_CUENTA":
            data['NUMERO_FACTURA'] = "RESUMEN_DEUDA"
            totales = re.findall(r'TOTAL[:\s]*\$?([\d\.,]+)', full_text, re.IGNORECASE)
            if totales: data['VALOR_TOTAL_DEUDA'] = self.clean_money(totales[-1])
            fecha_gen = re.search(r'Fecha[:\s]*(\d{2}/\d{2}/\d{4})', full_text)
            if fecha_gen: data['FECHA'] = fecha_gen.group(1)

        elif modelo == "RETRO_2000s":
            data['FECHA'] = self.parse_retro_date(full_text)
            total = re.search(r'(?:TOTAL A PAGAR|VALOR A PAGAR)[:\s]*\$?([\d\.,]+)', full_text, re.IGNORECASE)
            val = self.clean_money(total.group(1)) if total else 0.0
            data['VALOR_CONSUMO_MES'] = val
            data['VALOR_TOTAL_DEUDA'] = val
            fact = re.search(r'(?:Factura|Ref)[:\s\.]*(?:No\.?)?[:\s]*(\d{4,})', full_text, re.IGNORECASE)
            if fact: data['NUMERO_FACTURA'] = fact.group(1)

        elif modelo in ["MODERNO_ELECTRONICO", "MODERNO_TRANSICION"]:
            fact = re.search(r'(?:Factura electrónica de venta|No\. de factura)[:\s]*([A-Z0-9]+)', full_text, re.IGNORECASE)
            if fact: data['NUMERO_FACTURA'] = fact.group(1)
            fecha = re.search(r'Fecha de emisión[:\s]*([A-Za-z]+\s\d{1,2}[-]\d{2,4})', full_text, re.IGNORECASE)
            if fecha: data['FECHA'] = fecha.group(1)
            
            mes = re.search(r'TOTAL FACTURA SERVICIOS DEL PERIODO[:\s]*\$?([\d\.,]+)', full_text, re.IGNORECASE)
            if mes: data['VALOR_CONSUMO_MES'] = self.clean_money(mes.group(1))
            total = re.search(r'(?:TOTAL FACTURA A PAGAR|Total a Pagar)[:\s]*\$?([\d\.,]+)', full_text, re.IGNORECASE)
            if total: data['VALOR_TOTAL_DEUDA'] = self.clean_money(total.group(1))

        else: # Legacy
            fact = re.search(r'Factura de servicios? No\.[:\s]*(\d+)', full_text, re.IGNORECASE)
            if fact: data['NUMERO_FACTURA'] = fact.group(1)
            total = re.search(r'Total a Pagar[:\s]*\$?([\d\.,]+)', full_text, re.IGNORECASE)
            val = self.clean_money(total.group(1)) if total else 0.0
            data['VALOR_TOTAL_DEUDA'] = val
            data['VALOR_CONSUMO_MES'] = val
            fecha = re.search(r'Fecha de emisión[:\s]*([A-Za-z]+\s\d{1,2}[-]\d{2,4})', full_text, re.IGNORECASE)
            if fecha: data['FECHA'] = fecha.group(1)

        # Extras
        alum = re.findall(r'Impuesto Alumbrado Público BQ.*?\$?([\d\.,]+)', full_text, re.DOTALL)
        if alum: data['VALOR_ALUMBRADO'] = self.clean_money(alum[-1])
        ints = re.findall(r'Intereses de Mora.*?\$?([\d\.,]+)', full_text, re.DOTALL)
        if ints: data['VALOR_INTERES'] = self.clean_money(ints[-1])

        return data

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Arrastra aquí tus archivos PDF (Soporta múltiples)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🚀 Analizar {len(uploaded_files)} Facturas"):
        parser = TripleA_Master_Parser()
        resultados = []
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            res = parser.extract_data(file, file.name)
            resultados.append(res)
            progress_bar.progress((i + 1) / len(uploaded_files))
        
        df = pd.DataFrame(resultados)
        
        cols = ['ARCHIVO', 'MODELO', 'FECHA', 'NUMERO_FACTURA', 'VALOR_CONSUMO_MES', 
                'VALOR_ALUMBRADO', 'VALOR_INTERES', 'VALOR_TOTAL_DEUDA', 'POLIZA']
        for c in cols: 
            if c not in df.columns: df[c] = None
        df = df[cols]

        st.success("¡Coronamos! Aquí están los datos:")
        st.dataframe(df)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Datos')
        processed_data = output.getvalue()

        st.download_button(
            label="📥 Descargar Excel",
            data=processed_data,
            file_name="Reporte_TripleA_Web.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
