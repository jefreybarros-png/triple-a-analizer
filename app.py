import streamlit as st
import pdfplumber
import pandas as pd
import io
import re

st.set_page_config(page_title="Extractor Francotirador Triple A", page_icon="🎯", layout="wide")

st.title("🎯 Extractor Triple A - Método de Coordenadas (Francotirador)")
st.markdown("""
**Estrategia:** No lee el texto corrido. Busca la **ubicación exacta** de la etiqueta y recorta el área visual adyacente.
Este método es inmune a saltos de línea o desorden de texto.
""")

# --- HERRAMIENTAS DE LIMPIEZA ---
def clean_money(text):
    if not text: return 0.0
    text = str(text).upper().replace('S', '5').replace('O', '0').replace('B', '8').replace("'", "")
    # Solo números, puntos y comas
    matches = re.findall(r'[\d\.,]+', text)
    if not matches: return 0.0
    
    # Tomar el match más largo (evita números de página o items cortos)
    candidate = max(matches, key=len)
    
    # Lógica Colombia
    if ',' in candidate and '.' in candidate:
        candidate = candidate.replace('.', '').replace(',', '.')
    elif ',' in candidate:
        if len(candidate.split(',')[-1]) == 3: candidate = candidate.replace(',', '') 
        else: candidate = candidate.replace(',', '.') 
    elif '.' in candidate:
         if len(candidate.split('.')[-1]) == 3: candidate = candidate.replace('.', '')

    try: return float(candidate)
    except: return 0.0

def parse_date(text):
    if not text: return None
    # Busca patrones tipo: Abr 05-23 | Abril 2023 | 05/04/2023
    match = re.search(r'([A-Za-z]{3,})\s+(\d{1,2})[-/](\d{2,4})', text) # Abr 05-23
    if match: return f"{match.group(3)}-{match.group(1)}-{match.group(2)}"
    
    match2 = re.search(r'([A-Za-z]{3,})\s+(\d{4})', text) # Abril 2023
    if match2: return f"{match2.group(1)} {match2.group(2)}"
    
    return text.strip()

# --- MOTOR DE EXTRACCIÓN VISUAL (EL FRANCOTIRADOR) ---

def extract_visual_data(page, keywords, search_type="RIGHT", width_buffer=200, height_buffer=20):
    """
    Busca coordenadas de una keyword y extrae el texto en una zona relativa.
    search_type: "RIGHT" (Derecha), "BELOW" (Abajo).
    """
    # 1. Buscar la palabra clave en la página
    words = page.search(keywords, regex=True, case=False)
    
    if not words:
        return None

    # Tomamos la última ocurrencia (útil para totales que suelen estar al final)
    # O la primera si es encabezado. Depende del dato.
    target = words[0] 
    if "TOTAL" in keywords.upper() or "ALUMBRADO" in keywords.upper():
        target = words[-1] # Para valores monetarios, suelen estar abajo o a la derecha final

    # 2. Definir la caja de recorte (Bounding Box)
    # target tiene: x0, top, x1, bottom
    
    if search_type == "RIGHT":
        # Recortar desde donde termina la palabra hacia la derecha
        x0 = target['x1'] + 2 # Unos pixeles de margen
        top = target['top'] - 2 # Un poco más arriba para asegurar
        x1 = page.width # Hasta el final de la hoja (o x0 + width_buffer)
        bottom = target['bottom'] + 2 # Un poco más abajo
        
    elif search_type == "BELOW":
        # Recortar desde abajo de la palabra
        x0 = target['x0'] - 10 # Un poco a la izquierda para cubrir
        top = target['bottom']
        x1 = page.width # O un ancho fijo
        bottom = target['bottom'] + height_buffer # Solo bajar unos pixeles (ej: una linea)
    
    # 3. Recortar y extraer
    try:
        # crop((x0, top, x1, bottom))
        cropped_page = page.crop((x0, top, x1, bottom))
        text = cropped_page.extract_text()
        if text: return text.strip()
    except:
        pass # Si el crop se sale de la hoja
        
    return None

def analyze_pdf_sniper(file_obj, filename):
    data = {
        "ARCHIVO": filename,
        "FECHA PERIODO": None, "FECHA DE VENCIMIENTO": None, "NUMERO_FACTURA": None,
        "VALOR_FACTURA": 0.0, "VALOR_TOTAL_DEUDA": 0.0,
        "ALUMBRADO": 0.0, "INTERESES": 0.0,
        "POLIZA": None, "NOMBRE": None, "MODELO": "Desconocido"
    }

    try:
        with pdfplumber.open(file_obj) as pdf:
            page = pdf.pages[0] # Analizamos la primera página
            text_raw = page.extract_text() or ""
            upper_raw = text_raw.upper()

            # --- 1. IDENTIFICAR MODELO (Para saber dónde apuntar) ---
            if "CUFE" in upper_raw: data['MODELO'] = "ELECTRÓNICA"
            elif "PERIODO" in upper_raw and "TRIPLEAPP" in upper_raw: data['MODELO'] = "TRANSICION"
            elif re.search(r'[A-Z]{3}-\d{4}', upper_raw): data['MODELO'] = "RETRO"
            else: data['MODELO'] = "LEGACY"

            # --- 2. EXTRACCIÓN VISUAL (COORDENADAS) ---

            # == POLIZA (Universal) ==
            # Siempre está a la derecha de "PÓLIZA"
            raw_pol = extract_visual_data(page, r"PÓLIZA", "RIGHT")
            if raw_pol: data['POLIZA'] = re.sub(r'\D', '', raw_pol) # Solo números

            # == VALORES MONETARIOS ==
            
            # ALUMBRADO (Universal)
            # Busca "Alumbrado Público" y recorta a la derecha
            val_alum = extract_visual_data(page, r"Alumbrado P.blico", "RIGHT")
            data['ALUMBRADO'] = clean_money(val_alum)

            # INTERESES (Universal)
            val_int = extract_visual_data(page, r"Intereses de Mora", "RIGHT")
            data['INTERESES'] = clean_money(val_int)
            
            # == LÓGICA POR MODELO ==
            
            if data['MODELO'] == "ELECTRÓNICA":
                # En electrónica todo está a la DERECHA
                data['VALOR_FACTURA'] = clean_money(extract_visual_data(page, "TOTAL FACTURA SERVICIOS DEL PERIODO", "RIGHT"))
                data['VALOR_TOTAL_DEUDA'] = clean_money(extract_visual_data(page, "TOTAL FACTURA A PAGAR", "RIGHT"))
                data['FECHA PERIODO'] = parse_date(extract_visual_data(page, "Fecha de emisión", "RIGHT"))
                
                # Nombre está después de la etiqueta
                # Usamos regex normal para nombre en electrónica, es más seguro que crop
                m = re.search(r'Nombre del cliente:[:\s]*\n?([^\n]+)', text_raw)
                if m: data['NOMBRE'] = m.group(1).strip()
                
                # Factura
                m_fac = re.search(r'(?:Factura electrónica de venta|No\. de factura)[:\s]*([A-Z0-9]+)', text_raw)
                if m_fac: data['NUMERO_FACTURA'] = m_fac.group(1)

            elif data['MODELO'] == "LEGACY" or data['MODELO'] == "RETRO":
                # En las viejas, los datos están ABAJO
                
                # FECHA: Debajo de "Período facturado"
                data['FECHA PERIODO'] = parse_date(extract_visual_data(page, r"Per.odo facturado", "BELOW", height_buffer=25))
                
                # VENCIMIENTO: Debajo de "Pague hasta"
                data['FECHA DE VENCIMIENTO'] = parse_date(extract_visual_data(page, r"Pague hasta", "BELOW", height_buffer=25))
                
                # NOMBRE: Debajo de "Señor(a)"
                data['NOMBRE'] = extract_visual_data(page, r"Se.or\(a\)", "BELOW", height_buffer=25)
                
                # FACTURA: Debajo o lado
                # Primero intentamos abajo
                raw_fac = extract_visual_data(page, r"Factura de servicios No.", "BELOW", height_buffer=25)
                if raw_fac and any(c.isdigit() for c in raw_fac):
                     data['NUMERO_FACTURA'] = raw_fac.split()[0]
                else:
                     # Si falló, intentamos a la derecha (algunas legacy raras)
                     raw_fac = extract_visual_data(page, r"Factura de servicios No.", "RIGHT")
                     if raw_fac: data['NUMERO_FACTURA'] = raw_fac.split()[0]

                # VALOR TOTAL
                # En Legacy, está a la derecha de "Total a Pagar", pero lejos (puntos suspensivos)
                # search_type="RIGHT" funciona porque recorta todo hasta el borde de la hoja
                raw_total = extract_visual_data(page, r"Total a Pagar", "RIGHT")
                val = clean_money(raw_total)
                data['VALOR_FACTURA'] = val
                data['VALOR_TOTAL_DEUDA'] = val

            elif data['MODELO'] == "TRANSICION":
                # Híbrido 2023
                data['VALOR_FACTURA'] = clean_money(extract_visual_data(page, "TOTAL FACTURA SERVICIOS DEL PERIODO", "RIGHT"))
                data['VALOR_TOTAL_DEUDA'] = clean_money(extract_visual_data(page, "TOTAL FACTURA A PAGAR", "RIGHT"))
                data['FECHA PERIODO'] = parse_date(extract_visual_data(page, r"Periodo facturado", "RIGHT"))
                data['FECHA DE VENCIMIENTO'] = parse_date(extract_visual_data(page, r"Pague hasta", "RIGHT"))
                
                # Nombre debajo de Señor(a)
                data['NOMBRE'] = extract_visual_data(page, r"Se.or\(a\)", "BELOW", height_buffer=25)

            # --- LIMPIEZA FINAL ---
            if not data['NUMERO_FACTURA']:
                 # Intento desesperado: buscar cualquier patrón de factura
                 m = re.search(r'No\.\s*(\d{5,})', text_raw)
                 if m: data['NUMERO_FACTURA'] = m.group(1)

    except Exception as e:
        return {"ARCHIVO": filename, "ERROR": str(e)}

    return data

# --- INTERFAZ ---
uploaded_files = st.file_uploader("Arrastra tus PDFs aquí", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🎯 Disparar Extracción ({len(uploaded_files)})"):
        results = []
        bar = st.progress(0)
        
        for i, f in enumerate(uploaded_files):
            # Reset file pointer
            f.seek(0)
            res = analyze_pdf_sniper(f, f.name)
            results.append(res)
            bar.progress((i+1)/len(uploaded_files))
            
        df = pd.DataFrame(results)
        
        cols = [
            'ARCHIVO', 'MODELO',
            'FECHA PERIODO', 'FECHA DE VENCIMIENTO', 
            'NUMERO_FACTURA', 'NOMBRE',
            'VALOR_FACTURA', 'VALOR_TOTAL_DEUDA', 
            'ALUMBRADO', 'INTERESES', 'POLIZA'
        ]
        for c in cols:
            if c not in df.columns: df[c] = None
            
        st.success("¡Extracción por Coordenadas completada!")
        st.dataframe(df[cols])
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df[cols].to_excel(writer, index=False)
        st.download_button("Descargar Excel", buffer.getvalue(), "Reporte_Francotirador.xlsx")
