import pdfplumber
import sys
import os

def diagnosticar_pdf(ruta_archivo):
    print(f"\n{'='*60}")
    print(f"🔍 DIAGNÓSTICO ESTRUCTURAL: {os.path.basename(ruta_archivo)}")
    print(f"{'='*60}")
    
    try:
        with pdfplumber.open(ruta_archivo) as pdf:
            if not pdf.pages:
                print("❌ ERROR: El PDF no tiene páginas.")
                return

            pagina = pdf.pages[0] # Analizamos la primera página (donde suele estar todo)
            
            # 1. Extracción Cruda con Layout
            texto_layout = pagina.extract_text(layout=True)
            texto_simple = pagina.extract_text(layout=False)
            
            print("\n[1] ¿TIENE TEXTO DIGITAL?")
            if not texto_layout or len(texto_layout) < 50:
                print("⚠️  ¡ALERTA! Parece ser una IMAGEN o ESCANEO. ")
                print("    El programa no ve letras, ve una foto. Necesitas OCR.")
                return
            else:
                print(f"✅ Sí, detecté {len(texto_layout)} caracteres de texto digital.")

            print("\n[2] RADIOGRAFÍA VISUAL (Primeras 20 líneas tal cual las ve el código):")
            print("-" * 60)
            lineas = texto_layout.split('\n')
            for i, linea in enumerate(lineas[:20]):
                print(f"L{i+1:02d}: {linea}")
            print("-" * 60)
            
            print("\n[3] BÚSQUEDA DE PALABRAS CLAVE (Ubicación exacta):")
            claves = ["TOTAL", "PAGAR", "FACTURA", "POLIZA", "FECHA", "PERIODO", "CUFE"]
            encontradas = []
            
            for i, linea in enumerate(lineas):
                linea_upper = linea.upper()
                for clave in claves:
                    if clave in linea_upper:
                        # Resaltamos la palabra clave
                        texto_resaltado = linea.replace(clave, f"[{clave}]")
                        # Buscamos si hay números en esa misma línea
                        tiene_numeros = any(c.isdigit() for c in linea)
                        num_status = "✅ Tiene Números" if tiene_numeros else "⚠️ Solo Texto"
                        
                        print(f"📍 Línea {i+1:03d} | {clave.ljust(10)} | {num_status} -> {texto_resaltado.strip()}")
                        encontradas.append(clave)

            if not encontradas:
                print("❌ No encontré ninguna palabra clave. El formato es muy raro o está como imagen.")
                
            print("\n[4] CONCLUSIÓN PRELIMINAR:")
            if "CUFE" in texto_simple:
                print("👉 Parece FACTURA ELECTRÓNICA (2024-2025).")
            elif "PERIODO" in texto_simple.upper():
                print("👉 Parece FACTURA MODERNA (2023).")
            elif "TOTAL A PAGAR" in texto_simple.upper():
                print("👉 Parece FACTURA LEGACY (2017-2020).")
            else:
                print("👉 Formato DESCONOCIDO o muy antiguo (2001).")

    except Exception as e:
        print(f"❌ Error fatal leyendo el archivo: {e}")

if __name__ == "__main__":
    # Modo de uso: arrastra el archivo o ponlo en la lista
    if len(sys.argv) > 1:
        for archivo in sys.argv[1:]:
            diagnosticar_pdf(archivo)
    else:
        # SI LO CORRES SIN ARGUMENTOS, MODIFICA ESTA LÍNEA CON TU ARCHIVO DE PRUEBA
        archivo_prueba = "abril2020.pdf"  # <--- CAMBIA ESTO POR TU ARCHIVO
        if os.path.exists(archivo_prueba):
            diagnosticar_pdf(archivo_prueba)
        else:
            print("⚠️ Arrastra un PDF sobre este script o edita la variable 'archivo_prueba'.")
